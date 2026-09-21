import asyncio
import contextlib
import json
import os


class AppError(Exception):
    pass


class BusyError(AppError):
    pass


def deny_response(method, request_id):
    if method in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
        result = {'decision': 'cancel'}
    elif method in ('execCommandApproval', 'applyPatchApproval'):
        result = {'decision': 'abort'}
    elif method == 'item/permissions/requestApproval':
        result = {'permissions': {}, 'scope': 'turn'}
    elif method == 'mcpServer/elicitation/request':
        result = {'action': 'decline'}
    elif method == 'item/tool/requestUserInput':
        result = {'answers': {}}
    else:
        return {'id': request_id, 'error': {'code': -32601, 'message': 'Remote server request refused'}}
    return {'id': request_id, 'result': result}


class AppServer:
    def __init__(self, command, home='', timeout=30, spawn=None):
        self.command, self.home, self.timeout = command, home, timeout
        self.spawn = spawn or asyncio.create_subprocess_exec
        self.process = None
        self.reader = self.stderr = None
        self.pending = {}
        self.runs = {}
        self.sequence = 0
        self.write_lock = asyncio.Lock()
        self.start_lock = asyncio.Lock()
        self.generation = 0

    async def start(self):
        async with self.start_lock:
            if self.process and self.process.returncode is None and self.reader and not self.reader.done():
                return
            if self.process:
                await self.close()
            env = os.environ.copy()
            if self.home:
                env['CODEX_HOME'] = self.home
            # Never inherit an unsafe permission profile as the process default.
            self.process = await self.spawn(self.command, 'app-server',
                '-c', 'approval_policy="never"', '-c', 'sandbox_mode="workspace-write"',
                '-c', 'sandbox_workspace_write.network_access=false',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=env, limit=8*1024*1024)
            self.generation += 1
            self.reader = asyncio.create_task(self._read())
            self.stderr = asyncio.create_task(self._drain_stderr())
            try:
                await self._call('initialize', {'clientInfo': {'name': 'codex_remote_bridge', 'version': '0.1.0'}})
                await self._write({'method': 'initialized', 'params': {}})
            except BaseException:
                await self.close()
                raise

    async def _drain_stderr(self):
        while await self.process.stderr.read(4096):
            pass  # Raw diagnostics can contain secrets and local paths.

    async def _write(self, obj):
        async with self.write_lock:
            if not self.process or self.process.returncode is not None:
                raise AppError('Codex unavailable')
            self.process.stdin.write((json.dumps(obj, ensure_ascii=False)+'\n').encode())
            await self.process.stdin.drain()

    async def _call(self, method, params):
        self.sequence += 1
        rid = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[rid] = future
        try:
            await self._write({'id': rid, 'method': method, 'params': params})
            return await asyncio.wait_for(future, self.timeout)
        except (asyncio.TimeoutError, BrokenPipeError, ConnectionError):
            await self.close()
            raise AppError('Codex request outcome unknown; do not retry automatically') from None
        finally:
            self.pending.pop(rid, None)

    def _fail(self):
        for future in self.pending.values():
            if not future.done():
                future.set_exception(AppError('Codex disconnected'))
        for run in self.runs.values():
            if not run['done'].done():
                run['done'].set_exception(AppError('Turn outcome unknown; inspect locally'))

    async def _read(self):
        try:
            while True:
                raw = await self.process.stdout.readline()
                if not raw:
                    break
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError()
                if 'method' in obj:
                    if 'id' in obj:
                        await self._write(deny_response(obj['method'], obj['id']))
                        # These requests can lack a thread ID: fail closed for all owned work.
                        for run in self.runs.values():
                            run['denied'] = True
                        if self.process.returncode is None:
                            self.process.terminate()
                        break
                    self._event(obj['method'], obj.get('params', {}))
                elif 'id' in obj:
                    future = self.pending.get(obj['id'])
                    if future and not future.done():
                        if 'error' in obj:
                            message = str(obj['error'].get('message', ''))
                            cls = BusyError if 'active writer' in message or 'already running' in message else AppError
                            future.set_exception(cls('Thread owned by another client' if cls is BusyError else 'Codex request refused'))
                        elif 'result' in obj:
                            future.set_result(obj['result'])
                        else:
                            raise ValueError()
        except Exception:
            if self.process and self.process.returncode is None:
                self.process.terminate()
        finally:
            self._fail()

    def _event(self, method, params):
        tid = params.get('threadId')
        run = self.runs.get(tid)
        if not run:
            return
        event_turn = params.get('turnId') or params.get('turn', {}).get('id')
        if method == 'turn/started' and not run['id']:
            run['id'] = event_turn
        if not event_turn or (run['id'] and event_turn != run['id']):
            return
        if not run['id']:
            run['id'] = event_turn  # Notifications can precede turn/start response.
        if method == 'item/completed':
            item = params.get('item', {})
            if item.get('type') == 'agentMessage' and item.get('phase') != 'commentary':
                run['text'] = str(item.get('text', ''))[:64000]
        if method == 'turn/completed' and not run['done'].done():
            turn = params.get('turn', {})
            for item in turn.get('items', []):
                if item.get('type') == 'agentMessage' and item.get('phase') != 'commentary':
                    run['text'] = str(item.get('text', ''))[:64000]
            run['done'].set_result({'status': turn.get('status', 'failed'), 'text': run['text'], 'denied': run['denied']})

    async def thread_list(self, cursor=None):
        return await self._call('thread/list', {'limit': 100, 'cursor': cursor, 'sortKey': 'updated_at'})

    async def thread_read(self, tid, include_turns=False):
        return (await self._call('thread/read', {'threadId': tid, 'includeTurns': include_turns}))['thread']

    async def coordinator_start(self, cwd, instructions):
        return (await self._call('thread/start', {'cwd': str(cwd), 'approvalPolicy': 'never',
            'approvalsReviewer': 'user', 'sandbox': 'read-only', 'ephemeral': False,
            'baseInstructions': instructions, 'developerInstructions': instructions}))['thread']

    async def coordinator_name(self, tid):
        await self._call('thread/name/set', {'threadId': tid, 'name': '钉钉机器人'})

    async def thread_resume(self, tid, coordinator=False):
        return (await self._call('thread/resume', {'threadId': tid, 'approvalPolicy': 'never',
            'approvalsReviewer': 'user', 'excludeTurns': True,
            'sandbox': 'read-only' if coordinator else 'workspace-write', 'config': {'sandbox_workspace_write.writable_roots': [],
            'sandbox_workspace_write.network_access': False}}))['thread']

    async def turn_start(self, tid, text, cwd, output_schema=None):
        if tid in self.runs:
            raise BusyError('Thread busy')
        done = asyncio.get_running_loop().create_future()
        # Mark exceptions consumed even if startup fails before caller can await done.
        done.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        run = {'id': None, 'done': done, 'text': '', 'denied': False, 'generation': self.generation}
        self.runs[tid] = run
        try:
            params = {'threadId': tid, 'input': [{'type': 'text', 'text': text}],
                'cwd': str(cwd), 'approvalPolicy': 'never', 'approvalsReviewer': 'user', 'sandboxPolicy': {'type': 'workspaceWrite',
                'writableRoots': [str(cwd)], 'networkAccess': False, 'excludeTmpdirEnvVar': True, 'excludeSlashTmp': True}}
            if output_schema is not None:
                params.update(outputSchema=output_schema, sandboxPolicy={'type': 'readOnly'}, effort='low')
            result = await self._call('turn/start', params)
            turn_id = result['turn']['id']
            if run['id'] and run['id'] != turn_id:
                await self.close()
                raise AppError('Turn ownership mismatch')
            run['id'] = turn_id
            return turn_id, done
        except BaseException:
            self.runs.pop(tid, None)
            raise

    async def turn_interrupt(self, tid, turn_id):
        run = self.runs.get(tid)
        if not run or run['id'] != turn_id or run['done'].done() or run['generation'] != self.generation:
            raise AppError('No owned active turn')
        return await self._call('turn/interrupt', {'threadId': tid, 'turnId': turn_id})

    def release(self, tid):
        self.runs.pop(tid, None)

    async def close(self):
        proc = self.process
        if proc and proc.returncode is None:
            proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), 3)
            except asyncio.TimeoutError:
                proc.terminate()
                await proc.wait()
        self._fail()
        for task in (self.reader, self.stderr):
            if task and task is not asyncio.current_task():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self.process = None
