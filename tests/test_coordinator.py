import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_bridge.coordinator import Coordinator, SCHEMA, parse_action, dispatch_authorized
from codex_bridge.config import Config
from codex_bridge.router import InboundMessage
from codex_bridge.state import State
from channels.dingtalk import DingTalk


class ActionTests(unittest.TestCase):
    def test_no_generic_rpc_or_generated_instruction(self):
        for value in ({'method':'command/exec'}, {'action':'shell','target':'','instruction':'','reply':''}):
            with self.assertRaises(ValueError): parse_action(json.dumps(value))
        self.assertFalse(dispatch_authorized('请在安全任务执行检查', '安全任务', '删除文件', ['安全任务']))

    def test_explicit_unique_task_and_verbatim_instruction(self):
        text = '请在「安全任务」任务中执行：检查测试。'
        self.assertTrue(dispatch_authorized(text, '安全任务', '检查测试。', ['安全任务']))
        self.assertTrue(dispatch_authorized('请在安全任务执行：不要修改文件，只报告状态。', '安全任务', '不要修改文件，只报告状态。', ['安全任务']))
        self.assertFalse(dispatch_authorized(text, '安全任务', '检查测试。', ['安全任务','安全任务']))
        self.assertFalse(dispatch_authorized(text, '其他任务', '检查测试。', ['其他任务']))

    def test_queries_hypotheticals_and_negative_requests_cannot_dispatch(self):
        for text in ('刚刚安全任务结果是什么', '帮我看看安全任务进展', '不要让安全任务执行检查',
                     '如果请在安全任务执行检查会怎样', '比如请在安全任务执行检查', '安全任务完成了吗'):
            self.assertFalse(dispatch_authorized(text, '安全任务', '安全任务', ['安全任务']))


class AssistantFake:
    def __init__(self, root):
        self.root = root
        self.created = 0
        self.started = []
        self.responses = []
        self.target_done = None
        self.runs = {}
        self.target_status = 'idle'

    async def start(self): pass
    async def coordinator_start(self, cwd, instructions):
        self.created += 1
        return {'id':'assistant','cwd':str(self.root),'status':{'type':'idle'}}
    async def coordinator_name(self, tid): pass
    async def thread_list(self, cursor=None):
        return {'data':[{'id':'target','name':'安全任务','cwd':str(self.root)},
                        {'id':'outside','name':'不可见','cwd':str(self.root.parent/'other')}]}
    async def thread_read(self, tid, include_turns=False):
        return {'id':tid,'cwd':str(self.root),'status':{'type':self.target_status if tid == 'target' else 'idle'},
                'turns':[{'status':'completed','items':[{'type':'agentMessage','text':'此前测试通过'},
                                                       {'type':'commandExecution','text':'TOOL_SECRET'}]}]}
    async def thread_resume(self, tid, coordinator=False): return await self.thread_read(tid)
    async def turn_start(self, tid, text, cwd, output_schema=None):
        self.started.append((tid,text,output_schema))
        done = asyncio.get_running_loop().create_future()
        if tid == 'assistant':
            done.set_result({'status':'completed','text':json.dumps(self.responses.pop(0)), 'denied':False})
        else:
            self.target_done = done
        return 'turn-'+str(len(self.started)), done
    def release(self, tid): pass
    async def turn_interrupt(self, tid, turn):
        if self.target_done and not self.target_done.done():
            self.target_done.set_result({'status':'interrupted','text':''})
    async def close(self):
        await self.turn_interrupt('', '')


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.state = State(self.root/'state.db')
        self.config = Config('client','secret',frozenset({'user'}),frozenset(),(self.root,),'fake',self.root/'state.db')
        self.app = AssistantFake(self.root)
        self.router = Coordinator(self.config,self.state,self.app)
        self.replies = []
    async def asyncTearDown(self):
        await self.router.close()
        self.state.close()
        self.tmp.cleanup()
    async def send(self, value): self.replies.append(value)
    def msg(self, text, mid='m', sender='user'):
        return InboundMessage('dingtalk',mid,sender,'conversation','private',text)
    async def settle(self):
        for _ in range(30):
            await asyncio.sleep(0)
            if not self.router.dialogs: break
    def reply_action(self): return dict(action='reply',target='',instruction='',reply='此前测试通过')

    async def test_auto_create_reuse_and_safe_history(self):
        self.app.responses = [self.reply_action(),self.reply_action()]
        await self.router.handle(self.msg('今天主要有哪些任务'), self.send)
        await self.settle()
        await self.router.handle(self.msg('刚刚结果呢','m2'), self.send)
        await self.settle()
        self.assertEqual(self.app.created,1)
        self.assertEqual([x[0] for x in self.app.started],['assistant','assistant'])
        self.assertNotIn('TOOL_SECRET',self.app.started[0][1])
        self.assertNotIn('不可见',self.app.started[0][1])
        self.assertEqual(self.app.started[0][2],SCHEMA)
        self.assertEqual(self.state.coordinator(('dingtalk','conversation')),('user','assistant'))

    async def test_duplicate_and_unauthorized_do_not_create_tasks(self):
        self.app.responses = [self.reply_action()]
        await self.router.handle(self.msg('你好',sender='stranger'), self.send)
        self.assertEqual(self.app.created,0)
        await asyncio.gather(self.router.handle(self.msg('你好'),self.send),self.router.handle(self.msg('你好'),self.send))
        await self.settle()
        self.assertEqual(len(self.app.started),1)

    async def test_query_model_cannot_invent_dispatch(self):
        self.app.responses = [dict(action='dispatch',target='T1',instruction='安全任务',reply='')]
        await self.router.handle(self.msg('安全任务结果是什么'),self.send)
        await self.settle()
        self.assertEqual(len(self.app.started),1)
        self.assertIsNone(self.app.target_done)

    async def test_dispatch_and_completion_notification(self):
        self.app.responses = [dict(action='dispatch',target='T1',instruction='检查测试。',reply='')]
        await self.router.handle(self.msg('请在「安全任务」任务中执行：检查测试。'),self.send)
        await self.settle()
        self.assertEqual(self.app.started[-1][:2],('target','检查测试。'))
        self.assertIn('派发',self.replies[-1])
        self.app.target_done.set_result({'status':'completed','text':'检查通过'})
        await asyncio.gather(*self.router.tasks)
        self.assertIn('安全任务',self.replies[-1])
        self.assertIn('检查通过',self.replies[-1])
        self.assertEqual(self.state.recent_dispatches(('dingtalk','conversation'))[0]['status'],'completed_notified')

    async def test_foreign_active_task_not_started(self):
        self.app.target_status='active'
        self.app.responses=[dict(action='dispatch',target='T1',instruction='检查',reply='')]
        await self.router.handle(self.msg('请在安全任务执行检查'),self.send)
        await self.settle()
        self.assertIsNone(self.app.target_done)

    async def test_restart_preserves_coordinator_and_does_not_retry_unknown_work(self):
        key=('dingtalk','conversation')
        self.state.set_coordinator(key,'user','assistant')
        identity=self.state.dispatch(key,'target')
        self.state.update_dispatch(identity,'running','turn-id')
        self.state.close()
        self.state=State(self.root/'state.db')
        self.router.state=self.state
        self.assertEqual(self.state.coordinator(key),('user','assistant'))
        self.assertEqual(self.state.recent_dispatches(key)[0]['status'],'unknown')
        self.assertEqual(self.app.started,[])

    async def test_oto_notification_uses_allowlist_and_reports_rate_limit(self):
        channel=DingTalk(self.config,self.router)
        calls=[]
        def fake_post(url, body, headers=None):
            calls.append((url,body,headers))
            if 'accessToken' in url: return {'accessToken':'private-token','expireIn':7200}
            return {'processQueryKey':'delivery','invalidStaffIdList':[]}
        with patch('channels.dingtalk.post',fake_post):
            with self.assertRaises(RuntimeError): await channel.send_private('stranger','text')
            self.assertEqual(calls,[])
            await channel.send_private('user','完成')
            await channel.send_private('user','完成2')
            self.assertEqual(len(calls),3)
            self.assertEqual(calls[-1][1]['userIds'],['user'])
        with patch('channels.dingtalk.post',return_value={'processQueryKey':'x','flowControlledStaffIdList':['user']}):
            with self.assertRaises(RuntimeError): await channel.send_private('user','完成')
