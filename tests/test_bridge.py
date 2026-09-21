import asyncio
import json
import os
import socket
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codex_bridge.app_server import AppServer, AppError, BusyError, deny_response
from codex_bridge.config import Config, ConfigError, load_env
from codex_bridge.router import Router, InboundMessage
from codex_bridge.security import allowed_path, lexical_inside, safe_text
from codex_bridge.state import State
from channels.dingtalk import normalize


def setUpModule():
    global block_connect
    original = socket.socket.connect
    def offline_connect(sock, address):
        # Windows asyncio creates its internal socketpair over loopback.
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return original(sock, address)
        raise AssertionError('Offline tests forbid external network')
    block_connect = patch.object(socket.socket, 'connect', offline_connect)
    block_connect.start()


def tearDownModule():
    block_connect.stop()


class SecurityTests(unittest.TestCase):
    def test_windows_paths(self):
        self.assertTrue(lexical_inside('C:/Work/repo', 'c:/work', True))
        for value in ('C:/Work2', 'C:Work', 'D:/Work', 'C:/Work/../outside'):
            self.assertFalse(lexical_inside(value, 'C:/Work', True))
        self.assertTrue(lexical_inside('//server/share/repo', '//server/share', True))
        self.assertFalse(lexical_inside('//server/share2/repo', '//server/share', True))

    def test_posix_paths(self):
        self.assertTrue(lexical_inside('/work/repo', '/work'))
        self.assertFalse(lexical_inside('/work2', '/work'))
        self.assertFalse(lexical_inside('../work', '/work'))

    def test_real_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root/'repo'; repo.mkdir()
            self.assertEqual(allowed_path(str(repo), (root,)), repo.resolve())
            for p in ('relative', str(root/'missing'), str(root/'..'/'escape'), None):
                self.assertIsNone(allowed_path(p, (root,)))

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'allowed'; root.mkdir()
            outside = Path(tmp)/'outside'; outside.mkdir()
            try:
                (root/'link').symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('OS does not grant symlink creation to this runner')
            self.assertIsNone(allowed_path(str(root/'link'), (root,)))

    def test_output_redaction_and_unicode(self):
        text = safe_text('你好 C:\\private\\key.txt /etc/passwd /tmp sk-abcdefghijklmnop client-secret-value', secrets=('client-secret-value',))
        self.assertIn('你好', text)
        for value in ('C:\\private', '/etc/passwd', '/tmp', 'abcdefghijklmnop', 'client-secret-value'):
            self.assertNotIn(value, text)
        self.assertLessEqual(len(safe_text('中'*5000, 300)), 300)
        self.assertIn('截断', safe_text('中'*5000, 300))

    def test_all_server_requests_deny(self):
        cases = {'item/commandExecution/requestApproval': {'decision':'cancel'},
                 'item/fileChange/requestApproval': {'decision':'cancel'},
                 'execCommandApproval': {'decision':'abort'}, 'applyPatchApproval': {'decision':'abort'},
                 'item/permissions/requestApproval': {'permissions':{},'scope':'turn'},
                 'mcpServer/elicitation/request': {'action':'decline'},
                 'item/tool/requestUserInput': {'answers':{}}}
        for method, response in cases.items():
            self.assertEqual(deny_response(method, 17), {'id':17,'result':response})
        self.assertIn('error', deny_response('item/tool/call', 1))
        for method in ('account/chatgptAuthTokens/refresh', 'attestation/generate', 'new/approval'):
            self.assertIn('error', deny_response(method, 1))


class ConfigStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def config_env(self):
        return {'DINGTALK_CLIENT_ID':'test-id','DINGTALK_CLIENT_SECRET':'test-secret',
                'DINGTALK_ALLOWED_USER_IDS':'test-user','CODEX_ALLOWED_ROOTS':json.dumps([str(self.root)])}

    def test_config_fail_closed(self):
        with self.assertRaises(ConfigError): Config.load(self.root, {})
        with patch('shutil.which', return_value='/fake/codex'):
            config = Config.load(self.root, self.config_env())
            self.assertNotIn('test-secret', repr(config))
            for values in ({'DINGTALK_ALLOWED_USER_IDS':','}, {'CODEX_REMOTE_SANDBOX':'dangerFullAccess'},
                           {'CODEX_REMOTE_APPROVAL_POLICY':'on-request'}, {'CODEX_ALLOWED_ROOTS':'relative'}):
                with self.assertRaises(ConfigError): Config.load(self.root, self.config_env() | values)

    def test_env_precedence_no_interpolation(self):
        path = self.root/'.env'; path.write_text('TEST_BRIDGE_SETTING=local\nOTHER_LITERAL=$HOME\n',encoding='utf-8')
        with patch.dict(os.environ, {'TEST_BRIDGE_SETTING':'env'}):
            self.assertEqual(load_env(path)['TEST_BRIDGE_SETTING'], 'env')
            self.assertEqual(load_env(path)['OTHER_LITERAL'], '$HOME')

    def test_persistence_dedupe_and_expiry(self):
        state = State(self.root/'state.db')
        state.bind('dingtalk','conversation','thread')
        self.assertTrue(state.reserve('dingtalk','message'))
        self.assertFalse(state.reserve('dingtalk','message'))
        state.close()
        state = State(self.root/'state.db')
        self.assertEqual(state.get('dingtalk','conversation'), 'thread')
        self.assertFalse(state.reserve('dingtalk','message'))
        state.cleanup(int(time.time())+8*86400)
        self.assertTrue(state.reserve('dingtalk','message'))
        state.unbind('dingtalk','conversation')
        self.assertIsNone(state.get('dingtalk','conversation'))
        state.close()

    def test_singleton_state_lock(self):
        state = State(self.root/'state.db')
        try:
            with self.assertRaises(RuntimeError): State(self.root/'state.db')
        finally: state.close()

    def test_adapter_normalization(self):
        valid = {'msgtype':'text','msgId':'m','senderStaffId':'u','conversationId':'c','conversationType':'1','text':{'content':'你好'}}
        self.assertEqual(normalize(valid).text, '你好')
        self.assertEqual(normalize(valid).conversation_type, 'private')
        self.assertEqual(normalize(valid | {'conversationType':'2'}).conversation_type, 'group')
        for data in (None, {}, valid | {'senderStaffId':None}, valid | {'msgtype':'image'}, valid | {'text':[]}):
            self.assertIsNone(normalize(data))


class FakeProcess:
    def __init__(self):
        self.stdout, self.stderr = asyncio.StreamReader(), asyncio.StreamReader()
        self.stdin = self
        self.returncode = None
        self.sent = []
        self.on_request = None
        self.finished = asyncio.Event()

    def feed(self, obj):
        self.stdout.feed_data((json.dumps(obj)+'\n').encode())

    def write(self, raw):
        obj = json.loads(raw); self.sent.append(obj)
        if 'method' not in obj or 'id' not in obj: return
        if self.on_request and self.on_request(obj): return
        self.feed({'id':obj['id'],'result':{} if obj['method']=='initialize' else {'data':[]}})

    async def drain(self): pass
    def close(self): self.terminate()
    def terminate(self):
        if self.returncode is None:
            self.returncode = 0; self.stdout.feed_eof(); self.stderr.feed_eof(); self.finished.set()
    async def wait(self): await self.finished.wait(); return self.returncode


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.proc = FakeProcess()
        async def spawn(*args, **kwargs):
            self.spawn_args = args; self.spawn_kwargs = kwargs; return self.proc
        self.app = AppServer('fake-codex', timeout=0.1, spawn=spawn)
        await self.app.start()

    async def asyncTearDown(self): await self.app.close()

    async def test_handshake_and_transport(self):
        self.assertEqual([x['method'] for x in self.proc.sent], ['initialize','initialized'])
        self.assertNotIn('experimentalApi', json.dumps(self.proc.sent))
        self.assertNotIn('shell', self.spawn_kwargs)
        self.assertNotIn('--listen', self.spawn_args)

    async def test_out_of_order_response_correlation(self):
        requests = []
        def dispatch(obj):
            requests.append(obj)
            if len(requests)==2:
                for request in reversed(requests):
                    self.proc.feed({'id':request['id'],'result':{'thread':{'id':request['params']['threadId']}}})
            return True
        self.proc.on_request=dispatch
        a,b=await asyncio.gather(self.app.thread_read('a'),self.app.thread_read('b'))
        self.assertEqual((a['id'],b['id']),('a','b'))

    async def test_resume_writer_conflict(self):
        def dispatch(obj):
            self.proc.feed({'id':obj['id'],'error':{'code':-32600,'message':'already has an active writer'}}); return True
        self.proc.on_request=dispatch
        with self.assertRaises(BusyError): await self.app.thread_resume('a')
        params=self.proc.sent[-1]['params']
        self.assertEqual(params['sandbox'],'workspace-write')
        self.assertEqual(params['approvalPolicy'],'never')
        self.assertEqual(params['approvalsReviewer'],'user')

    async def test_notification_before_start_response(self):
        def dispatch(obj):
            self.proc.feed({'method':'turn/started','params':{'threadId':'t','turn':{'id':'turn'}}})
            self.proc.feed({'method':'item/completed','params':{'threadId':'t','turnId':'foreign','item':{'type':'agentMessage','text':'wrong'}}})
            self.proc.feed({'method':'item/completed','params':{'threadId':'t','turnId':'turn','item':{'type':'agentMessage','text':'你好'}}})
            self.proc.feed({'method':'turn/completed','params':{'threadId':'t','turn':{'id':'turn','status':'completed'}}})
            self.proc.feed({'id':obj['id'],'result':{'turn':{'id':'turn'}}}); return True
        self.proc.on_request=dispatch
        tid,done=await self.app.turn_start('t','hello','/safe')
        self.assertEqual(tid,'turn')
        self.assertEqual((await done)['text'],'你好')
        params=self.proc.sent[-1]['params']
        self.assertFalse(params['sandboxPolicy']['networkAccess'])
        self.assertEqual(params['approvalPolicy'],'never')

    async def test_interrupt_foreign_refused(self):
        with self.assertRaises(AppError): await self.app.turn_interrupt('foreign','turn')
        self.assertEqual(len(self.proc.sent),2)

    async def test_coordinator_stable_methods_and_readonly_schema(self):
        def dispatch(obj):
            if obj['method'] == 'turn/start':
                result = {'turn':{'id':'owned'}}
            else:
                result = {'thread':{'id':'assistant'}}
            self.proc.feed({'id':obj['id'],'result':result})
            return True
        self.proc.on_request=dispatch
        await self.app.coordinator_start('/safe','safe instructions')
        self.assertEqual(self.proc.sent[-1]['params']['sandbox'],'read-only')
        await self.app.coordinator_name('assistant')
        self.assertEqual(self.proc.sent[-1]['method'],'thread/name/set')
        await self.app.thread_resume('assistant',coordinator=True)
        self.assertEqual(self.proc.sent[-1]['params']['sandbox'],'read-only')
        await self.app.turn_start('assistant','hello','/safe',output_schema={'type':'object'})
        params=self.proc.sent[-1]['params']
        self.assertEqual(params['sandboxPolicy'],{'type':'readOnly'})
        self.assertEqual(params['outputSchema'],{'type':'object'})
        self.assertNotIn('dynamicTools',json.dumps(self.proc.sent))
        self.assertNotIn('experimentalApi',json.dumps(self.proc.sent))

    async def test_interrupt_owned_shape(self):
        done=asyncio.get_running_loop().create_future()
        self.app.runs['t']={'id':'owned','done':done,'generation':self.app.generation,'denied':False}
        await self.app.turn_interrupt('t','owned')
        self.assertEqual(self.proc.sent[-1]['method'],'turn/interrupt')
        self.assertEqual(self.proc.sent[-1]['params'],{'threadId':'t','turnId':'owned'})
        done.set_result({})

    async def test_unknown_server_request_refused(self):
        self.proc.feed({'id':77,'method':'future/approval','params':{'command':'must not run'}})
        await asyncio.sleep(0.01)
        self.assertIn('error',self.proc.sent[-1])
        self.assertNotIn('must not run',json.dumps(self.proc.sent))
        self.assertIsNotNone(self.proc.returncode)

    async def test_approval_refusal_kills_child(self):
        self.proc.feed({'method':'item/permissions/requestApproval','id':99,'params':{}})
        await asyncio.sleep(0.01)
        self.assertEqual(self.proc.sent[-1], {'id':99,'result':{'permissions':{},'scope':'turn'}})
        self.assertIsNotNone(self.proc.returncode)

    async def test_malformed_json_fail_closed(self):
        self.proc.stdout.feed_data(b'not-json\n')
        await asyncio.sleep(0.01)
        self.assertIsNotNone(self.proc.returncode)

    async def test_timeout_no_retry(self):
        self.proc.on_request=lambda obj: True
        with self.assertRaises(AppError): await self.app.thread_read('t')
        self.assertEqual(sum(x.get('method')=='thread/read' for x in self.proc.sent),1)
        self.assertIsNotNone(self.proc.returncode)

    async def test_process_exit_fails_pending(self):
        def dispatch(obj): self.proc.terminate(); return True
        self.proc.on_request=dispatch
        with self.assertRaises(AppError): await self.app.thread_list()


class FakeApp:
    def __init__(self, root):
        self.root=root; self.calls=[]; self.status='idle'; self.fail_resume=False; self.done=None; self.runs={}
    async def start(self): self.calls.append('start')
    async def thread_list(self, cursor=None):
        self.calls.append('list')
        return {'data':[{'id':'t','cwd':str(self.root),'name':'安全任务'},{'id':'bad','cwd':str(self.root/'missing'),'name':'excluded'}]}
    async def thread_read(self, tid): return {'id':tid,'cwd':str(self.root),'status':{'type':self.status}}
    async def thread_resume(self, tid):
        self.calls.append('resume')
        if self.fail_resume: raise BusyError()
        return await self.thread_read(tid)
    async def turn_start(self, tid, text, cwd):
        self.calls.append('turn'); self.done=asyncio.get_running_loop().create_future(); return 'turn',self.done
    async def turn_interrupt(self, tid, turn): self.calls.append('interrupt')
    def release(self, tid): pass
    async def close(self):
        if self.done and not self.done.done(): self.done.set_result({'status':'interrupted','text':''})


class RouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.state=State(self.root/'state.db')
        self.config=SimpleNamespace(users={'user'},conversations=set(),roots=(self.root,),client_id='dummy',client_secret='secret',max_input=4000,max_output=3000)
        self.app=FakeApp(self.root); self.router=Router(self.config,self.state,self.app); self.out=[]; self.seq=0
    async def asyncTearDown(self):
        await self.router.close(); self.state.close(); self.tmp.cleanup()
    async def send(self, text, **kwargs):
        self.seq+=1
        fields=dict(channel='dingtalk',message_id=str(self.seq),sender_id='user',conversation_id='chat',conversation_type='private',text=text)
        fields.update(kwargs)
        async def output(value): self.out.append(value)
        await self.router.handle(InboundMessage(**fields), output)
    async def bind(self): await self.send('/threads'); await self.send('/use 1')

    async def test_unknown_and_group_denied(self):
        await self.send('/threads',sender_id='unknown'); await self.send('/threads',conversation_type='group')
        self.assertEqual(self.app.calls,[]); self.assertEqual(self.out,[])

    async def test_conversation_restricted(self):
        self.config.conversations={'other'}
        await self.send('/threads'); self.assertEqual(self.app.calls,[])

    async def test_help_and_prohibited_commands(self):
        await self.send('/HELP'); self.assertIn('/stop',self.out[-1])
        for cmd in ('/rpc command/exec {}','/shell whoami','/approve','/use C:/work'):
            await self.send(cmd)
        self.assertEqual(self.app.calls,[])

    async def test_thread_list_filter_and_binding(self):
        await self.bind()
        self.assertEqual(self.state.get('dingtalk','chat'),'t')
        self.assertNotIn('excluded',''.join(self.out)); self.assertNotIn(str(self.root),''.join(self.out))
        await self.send('/current'); self.assertIn('当前',self.out[-1])
        await self.send('/unbind'); self.assertIsNone(self.state.get('dingtalk','chat'))

    async def test_stale_snapshot_and_invalid_index(self):
        await self.send('/use 1'); self.assertIsNone(self.state.get('dingtalk','chat'))
        await self.send('/threads'); await self.send('/use 0'); await self.send('/use 9')
        self.router.snapshots[('dingtalk','chat')]=(0,[('t','alias','title')])
        await self.send('/use 1'); self.assertIsNone(self.state.get('dingtalk','chat'))

    async def test_no_binding_oversize(self):
        await self.send('hello'); await self.send('a'*4001)
        self.assertEqual(self.app.calls,[])

    async def test_dedupe_busy_stop_complete(self):
        await self.bind()
        await self.send('hello',message_id='same'); await self.send('hello',message_id='same')
        await self.send('another')
        self.assertEqual(self.app.calls.count('turn'),1)
        self.assertIn('忙碌',self.out[-1])
        await self.send('/stop'); self.assertEqual(self.app.calls.count('interrupt'),1)
        self.app.done.set_result({'status':'completed','text':'你好'})
        await asyncio.gather(*self.router.tasks)
        self.assertIn('你好',self.out[-1]); self.assertFalse(self.router.active)

    async def test_desktop_writer_conflict(self):
        await self.bind(); self.app.fail_resume=True; await self.send('hello')
        self.assertNotIn('turn',self.app.calls)
        self.assertIn('占用',self.out[-1])
        await self.send('/stop'); self.assertNotIn('interrupt',self.app.calls)

    async def test_foreign_active(self):
        await self.bind(); self.app.status='active'; await self.send('hello')
        await self.send('/stop')
        self.assertNotIn('turn',self.app.calls); self.assertNotIn('interrupt',self.app.calls)

    async def test_binding_root_revalidated(self):
        await self.bind(); self.config.roots=(self.root/'missing',)
        await self.send('hello'); self.assertNotIn('turn',self.app.calls)

    async def test_only_owner_conversation_stops(self):
        await self.bind(); await self.send('hello')
        self.state.bind('dingtalk','other','t')
        await self.send('/stop',conversation_id='other')
        self.assertNotIn('interrupt',self.app.calls)

    async def test_no_final_fallback(self):
        await self.bind(); await self.send('hello')
        self.app.done.set_result({'status':'completed','text':''})
        await asyncio.gather(*self.router.tasks)
        self.assertIn('没有可返回',self.out[-1])

    async def test_completed_error_and_interrupted_output(self):
        await self.bind()
        for status,expected in [('failed','失败'),('interrupted','中断')]:
            await self.send('hello')
            self.app.done.set_result({'status':status,'text':'raw tool payload'})
            await asyncio.gather(*self.router.tasks)
            self.assertIn(expected,self.out[-1]); self.assertNotIn('raw tool',self.out[-1])

    async def test_pagination_preserves_indices(self):
        async def listing(cursor=None):
            return {'data':[{'id':str(i),'cwd':str(self.root),'name':f'task-{i}'} for i in range(15)]}
        self.app.thread_list=listing
        await self.send('/threads'); await self.send('/threads 2')
        self.assertIn('11.',self.out[-1]); self.assertIn('15.',self.out[-1])
        await self.send('/use 15')
        self.assertEqual(self.state.get('dingtalk','chat'),'14')

    async def test_duplicate_concurrent_inbound(self):
        await self.bind()
        await asyncio.gather(self.send('hello',message_id='same'),self.send('hello',message_id='same'))
        self.assertEqual(self.app.calls.count('turn'),1)


if __name__ == '__main__': unittest.main()
