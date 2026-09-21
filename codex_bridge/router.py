import asyncio
import time
from dataclasses import dataclass

from .app_server import AppError, BusyError
from .security import allowed_path, safe_text


@dataclass(frozen=True)
class InboundMessage:
    channel: str
    message_id: str
    sender_id: str
    conversation_id: str
    conversation_type: str
    text: str


HELP = ('/threads [页码] — 列出允许的已有任务\n/use <序号> — 绑定当前列表中的任务\n'
        '/current — 查看绑定\n/unbind — 解除绑定\n/stop — 停止本 Bridge 启动的 Turn\n'
        '/help — 帮助\n绑定后发送普通文字即可续接。Desktop 占用的任务无法接管。')


class Router:
    def __init__(self, config, state, app):
        self.config, self.state, self.app = config, state, app
        self.snapshots = {}
        self.locks = {}
        self.active = {}
        self.tasks = set()
        self.closing = False

    def authorized(self, msg):
        return (msg.channel == 'dingtalk' and msg.sender_id in self.config.users
                and msg.conversation_type == 'private'
                and bool(msg.message_id) and bool(msg.conversation_id)
                and len(msg.message_id) <= 512 and len(msg.conversation_id) <= 512
                and (not self.config.conversations or msg.conversation_id in self.config.conversations))

    def path_for(self, thread):
        resolver = getattr(self.app, 'path_for', None)
        return resolver(thread) if resolver else allowed_path(thread.get('cwd'), self.config.roots)

    def render(self, text):
        secrets = (self.config.client_id, self.config.client_secret, *self.config.users,
                   *self.config.conversations, *(str(p) for p in self.config.roots),
                   *(value for remote in getattr(self.config, 'remotes', ()) for value in (remote.host,remote.home,remote.command,*remote.roots)))
        return safe_text(text, self.config.max_output, secrets)

    async def handle(self, msg, send):
        if self.closing or not self.authorized(msg):
            return
        async def reply(text):
            await send(self.render(text))
        try:
            if not self.state.reserve(msg.channel, msg.message_id):
                return
            print('Authorized message reserved.', flush=True)
            text = msg.text.strip()
            if not text or len(text) > self.config.max_input:
                await reply('消息为空或超过长度限制。'); return
            key = (msg.channel, msg.conversation_id)
            if text.startswith('/'):
                await self.command(key, text, reply)
            else:
                await self.begin(key, text, reply)
        except BusyError:
            await reply('任务仍被 Desktop 或其他客户端占用。请等待其释放；Bridge 不会接管或提权。')
        except (AppError, OSError, ValueError, KeyError, RuntimeError):
            await reply('请求未完成，请在本机查看状态。若已开始 Turn，请勿自动重复发送。')

    async def checked(self, tid):
        thread = await self.app.thread_read(tid)
        path = self.path_for(thread)
        if not path:
            raise AppError('Thread outside allowed roots')
        status = thread.get('status', {}).get('type')
        if status not in ('idle', 'notLoaded', 'active'):
            raise AppError('Unavailable thread status')
        return thread, path

    async def command(self, key, text, reply):
        parts = text.split()
        cmd = parts[0].lower()
        if cmd == '/help' and len(parts) == 1:
            await reply(HELP); return
        if cmd == '/unbind' and len(parts) == 1:
            self.state.unbind(*key)
            await reply('绑定已解除；不会中断正在运行的 Turn。'); return
        if cmd == '/stop' and len(parts) == 1:
            tid = self.state.get(*key)
            owned = self.active.get(tid)
            if not owned or owned['key'] != key or not owned.get('turn_id'):
                await reply('没有本会话通过 Bridge 启动并持有的活动 Turn。'); return
            await self.app.turn_interrupt(tid, owned['turn_id'])
            await reply('已请求停止。'); return
        if cmd not in ('/threads', '/use', '/current'):
            await reply('未知命令或参数错误，请发送 /help。'); return
        if (cmd == '/current' and len(parts) != 1) or (cmd == '/use' and (len(parts) != 2 or not parts[1].isascii() or not parts[1].isdigit())):
            await reply('参数错误，请发送 /help。'); return
        await self.app.start()
        if cmd == '/threads':
            if len(parts) > 2 or (len(parts) == 2 and (not parts[1].isascii() or not parts[1].isdigit() or int(parts[1]) < 1)):
                await reply('用法：/threads 或 /threads 2'); return
            page = int(parts[1]) if len(parts) == 2 else 1
            snapshot = self.snapshots.get(key)
            if page == 1:
                entries, cursor, cursors, ids = [], None, set(), set()
                # Bound memory/API work. Never expose non-allowlisted metadata.
                for _ in range(100):
                    result = await self.app.thread_list(cursor)
                    for thread in result.get('data', []):
                        path = self.path_for(thread)
                        if path and thread.get('id') and thread['id'] not in ids:
                            ids.add(thread['id'])
                            label = self.render(thread.get('name') or '未命名任务')[:60]
                            entries.append((thread['id'], (thread.get('host','local') + ':' + path.name), label))
                    cursor = result.get('nextCursor')
                    if not cursor:
                        break
                    if cursor in cursors:
                        raise AppError('Repeated pagination cursor')
                    cursors.add(cursor)
                else:
                    raise AppError('Too many threads to safely enumerate')
                self.snapshots = {k:v for k,v in self.snapshots.items() if v[0] > time.monotonic()}
                if len(self.snapshots) >= 100:
                    self.snapshots.pop(next(iter(self.snapshots)))
                snapshot = (time.monotonic()+300, entries)
                self.snapshots[key] = snapshot
            if not snapshot or snapshot[0] <= time.monotonic():
                await reply('列表已过期，请先发送 /threads。'); return
            entries = snapshot[1]
            rows = entries[(page-1)*10:page*10]
            if not rows:
                await reply('此页没有允许访问的任务。请检查本机项目目录白名单。'); return
            lines = [f'{i}. [{alias}] {name}' for i, (_,alias,name) in enumerate(rows, (page-1)*10+1)]
            await reply('\n'.join(lines)+f'\n第 {page}/{(len(entries)+9)//10} 页；/use 序号 绑定；/threads 页码 翻页。\n列表不代表 Desktop 已释放占用。')
        elif cmd == '/use':
            snapshot = self.snapshots.get(key)
            index = int(parts[1])-1
            if not snapshot or snapshot[0] <= time.monotonic() or not 0 <= index < len(snapshot[1]):
                await reply('序号无效或列表过期，请先发送 /threads。'); return
            tid = snapshot[1][index][0]
            thread, path = await self.checked(tid)
            if thread['status']['type'] == 'active':
                raise BusyError()
            self.state.bind(*key, tid)
            await reply(f'已绑定 {path.name}。发送文字续接；实际执行前会检查 writer 占用。')
        else:
            tid = self.state.get(*key)
            if not tid:
                await reply('尚未绑定，请发送 /threads。'); return
            thread, path = await self.checked(tid)
            status = 'Bridge 正在执行' if tid in self.active else '待执行时检查 Desktop 占用'
            await reply(f'当前项目：{path.name}\n状态：{status}')

    async def begin(self, key, text, reply):
        tid = self.state.get(*key)
        if not tid:
            await reply('尚未绑定，请先发送 /threads，再发送 /use 序号。'); return
        if tid not in self.locks:
            self.locks = {k:v for k,v in self.locks.items() if v.locked()}
            if len(self.locks) >= 32:
                raise BusyError()
            self.locks[tid] = asyncio.Lock()
        lock = self.locks[tid]
        if lock.locked():
            await reply('任务忙碌，请等待完成；不会排队或插入指令。'); return
        await lock.acquire()
        transferred = False
        try:
            await self.app.start()
            thread, path = await self.checked(tid)
            if thread['status']['type'] == 'active':
                raise BusyError()
            resumed = await self.app.thread_resume(tid)  # Server's writer lock is authoritative.
            resumed_path = self.path_for(resumed)
            if resumed_path != path or resumed.get('status', {}).get('type') != 'idle':
                raise AppError('Resume did not produce the expected idle workspace')
            turn_id, done = await self.app.turn_start(tid, text, path)
            self.active[tid] = {'turn_id': turn_id, 'key': key}
            print('Bridge-owned turn started.', flush=True)
            task = asyncio.create_task(self.finish(tid, done, reply, lock))
            self.tasks.add(task)
            def finished(future):
                self.tasks.discard(future)
                if not future.cancelled() and future.exception():
                    print('Final delivery failed; no automatic resend.', flush=True)
            task.add_done_callback(finished)
            transferred = True
            await reply(f'已开始 · {path.name}')
        finally:
            if not transferred:
                lock.release()

    async def finish(self, tid, done, reply, lock):
        try:
            result = await asyncio.wait_for(asyncio.shield(done), 900)
            print('Bridge-owned turn completed.', flush=True)
            if result.get('denied'):
                message = '远程审批已拒绝，请在本机处理。'
            elif result['status'] == 'completed':
                message = '已完成\n'+(result['text'] or '任务结束，没有可返回的最终文字。')
            elif result['status'] == 'interrupted':
                message = '任务已中断。'
            else:
                message = '任务失败，请在本机查看详情。'
            await reply(message)
        except asyncio.TimeoutError:
            record = self.active.get(tid)
            if record:
                try:
                    await self.app.turn_interrupt(tid, record['turn_id'])
                except AppError:
                    pass
            await self.app.close()
            await reply('等待超时，已停止本 Bridge 进程；请在本机确认结果，勿重复提交。')
        except AppError:
            run = self.app.runs.get(tid, {})
            await reply('远程审批或工具请求已拒绝，请在本机处理。' if run.get('denied') else 'Codex 连接中断，结果未知，请在本机确认。')
        except (OSError, RuntimeError, ValueError):
            pass  # Do not retry a channel send that may already have succeeded.
        finally:
            self.active.pop(tid, None)
            self.app.release(tid)
            lock.release()

    async def close(self):
        self.closing = True
        for tid, record in list(self.active.items()):
            try:
                await self.app.turn_interrupt(tid, record['turn_id'])
            except AppError:
                pass
        await self.app.close()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
