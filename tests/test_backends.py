import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from codex_bridge.app_server import AppError
from codex_bridge.backends import Backends, SSHServer, VALIDATE_PATHS
from codex_bridge.config import Config, ConfigError, RemoteConfig, remote_configs


class RemoteConfigTests(unittest.TestCase):
    def entry(self):
        return dict(alias='work',host='work-host',command='/usr/bin/codex',home='/home/test/.codex',roots=['/work/project'])

    def test_configuration_is_fixed_and_defaults_off(self):
        self.assertEqual(remote_configs('[]'),())
        value=remote_configs(json.dumps([self.entry()]))[0]
        self.assertEqual(value.alias,'work')
        self.assertNotIn('/home',repr(value))
        for changes in ({'host':'-oProxyCommand=bad'},{'host':'host;cmd'}, {'alias':'local'},
                        {'roots':['/']},{'roots':['relative']},{'command':'codex --exec'},
                        {'home':'/home/../root'},{'roots':[]}):
            with self.assertRaises(ConfigError):remote_configs(json.dumps([self.entry()|changes]))
        with self.assertRaises(ConfigError):remote_configs(json.dumps([self.entry(),self.entry()]))

    def test_remote_native_validation_rejects_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'allowed';root.mkdir()
            sibling=Path(temp)/'allowed-other';sibling.mkdir()
            data={'roots':[str(root)],'paths':[str(root),str(sibling),str(root/'..'/'allowed-other'),'relative',str(root/'missing')]}
            output=io.StringIO()
            with patch('sys.stdin',io.StringIO(json.dumps(data))),patch('sys.stdout',output):
                exec(compile(VALIDATE_PATHS,'remote-validator','exec'),{})
            self.assertEqual(json.loads(output.getvalue()),[str(root.resolve()),None,None,None,None])

    def test_remote_validator_resolves_symlink_on_own_os(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'allowed';root.mkdir()
            outside=Path(temp)/'outside';outside.mkdir()
            link=root/'escape'
            try:
                link.symlink_to(outside,target_is_directory=True)
            except OSError:
                self.skipTest('Symlink privilege unavailable')
            output=io.StringIO()
            with patch('sys.stdin',io.StringIO(json.dumps({'roots':[str(root)],'paths':[str(link)]}))),patch('sys.stdout',output):
                exec(compile(VALIDATE_PATHS,'remote-validator','exec'),{})
            self.assertEqual(json.loads(output.getvalue()),[None])


class BackendFake:
    def __init__(self,cwd):
        self.cwd=cwd;self.calls=[];self.runs={};self.allowed=True
    async def start(self):pass
    async def close(self):pass
    async def thread_list(self,cursor=None):
        return {'data':[{'id':'same-id','cwd':self.cwd,'name':'task'}]}
    async def thread_read(self,tid,include_turns=False):
        self.calls.append(('read',tid,include_turns))
        return {'id':tid,'cwd':self.cwd,'status':{'type':'idle'}}
    async def thread_resume(self,tid,coordinator=False):
        self.calls.append(('resume',tid));return await self.thread_read(tid)
    async def validate_paths(self,paths):
        return [PurePosixPath(p) if self.allowed else None for p in paths]
    async def turn_start(self,tid,text,cwd,output_schema=None):
        self.calls.append(('turn',tid,str(cwd)));return 'owned-turn',None
    async def turn_interrupt(self,tid,turn):
        self.calls.append(('interrupt',tid,turn))
    def release(self,tid):self.calls.append(('release',tid))


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        config=Config('client','secret',frozenset({'user'}),frozenset(),(self.root,),'fake',self.root/'state.db')
        self.local=BackendFake(str(self.root));self.remote=BackendFake('/work/project')
        self.app=Backends(config,self.local,{'work':self.remote})
    async def asyncTearDown(self):self.tmp.cleanup()

    async def test_host_qualified_ids_and_pagination(self):
        first=await self.app.thread_list()
        second=await self.app.thread_list(first['nextCursor'])
        self.assertEqual(first['data'][0]['id'],'same-id')
        self.assertEqual(second['data'][0]['id'],'ssh:work:same-id')
        self.assertEqual(second['data'][0]['host'],'work')
        self.assertEqual(self.app.path_for(second['data'][0]),PurePosixPath('/work/project'))
        self.assertIsNone(second['nextCursor'])

    async def test_root_denial_precedes_remote_history(self):
        self.remote.allowed=False
        with self.assertRaises(AppError):await self.app.thread_read('ssh:work:id',include_turns=True)
        self.assertEqual(self.remote.calls,[('read','id',False)])

    async def test_recheck_before_turn_blocks_root_change(self):
        await self.app.thread_read('ssh:work:id')
        self.remote.allowed=False
        with self.assertRaises(AppError):await self.app.turn_start('ssh:work:id','work',PurePosixPath('/work/project'))
        self.assertFalse(any(c[0]=='turn' for c in self.remote.calls))

    async def test_interrupt_and_release_use_correct_host(self):
        await self.app.turn_interrupt('ssh:work:id','turn')
        self.app.release('ssh:work:id')
        self.assertEqual(self.remote.calls,[('interrupt','id','turn'),('release','id')])
        self.assertEqual(self.local.calls,[])
        with self.assertRaises(AppError):await self.app.thread_read('ssh:unknown:id')

    async def test_remote_transport_no_ports_or_shell_passthrough(self):
        calls=[]
        async def spawn(*args,**kwargs):calls.append((args,kwargs));return object()
        config=RemoteConfig('work','work-host','/usr/bin/codex','/home/test/.codex',('/work/project',))
        remote=SSHServer(config,spawn=spawn)
        await remote._spawn_remote(config.command,'app-server','-c','approval_policy="never"')
        args,kwargs=calls[0]
        self.assertIn('StrictHostKeyChecking=yes',args)
        self.assertIn('ForwardAgent=no',args)
        self.assertNotIn('-L',args);self.assertNotIn('-R',args)
        self.assertNotIn('shell',kwargs)
        self.assertIn('app-server',args[-1]);self.assertNotIn('--listen',args[-1])
