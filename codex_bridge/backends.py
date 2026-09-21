"""Fixed, locally configured SSH stdio backends; never a chat shell gateway."""
import asyncio
import json
import shlex
from pathlib import PurePosixPath

from .app_server import AppServer, AppError
from .security import allowed_path


# Runs on the target OS, so Windows never guesses Linux symlink/cwd semantics.
VALIDATE_PATHS = '''import json,sys
from pathlib import Path
data=json.load(sys.stdin)
roots=[Path(x).resolve(strict=True) for x in data['roots']]
if not all(x.is_dir() for x in roots): raise ValueError('Invalid root')
result=[]
for value in data['paths']:
    resolved=None
    try:
        p=Path(value)
        if p.is_absolute() and '..' not in p.parts:
            real=p.resolve(strict=True)
            if real.is_dir() and any(real==r or r in real.parents for r in roots):
                resolved=str(real)
    except (OSError,ValueError,RuntimeError,TypeError): pass
    result.append(resolved)
print(json.dumps(result))
'''


class SSHServer(AppServer):
    def __init__(self, config, spawn=None):
        self.remote = config
        self.native_spawn = spawn or asyncio.create_subprocess_exec
        self.prefix = ('ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                       '-o','ForwardAgent=no','-o','ConnectTimeout=10',
                       '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2',config.host)
        super().__init__(config.command, timeout=45, spawn=self._spawn_remote)

    async def _spawn_remote(self, command, *args, **kwargs):
        invocation = shlex.join(['env','CODEX_HOME='+self.remote.home,command,*args])
        return await self.native_spawn(*self.prefix,invocation,**kwargs)

    async def validate_paths(self, paths):
        if len(paths)>100 or any(not isinstance(p,str) or len(p)>4096 for p in paths):
            raise AppError('Invalid remote cwd metadata')
        process = await self.native_spawn(*self.prefix,shlex.join(['python3','-c',VALIDATE_PATHS]),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            payload=json.dumps({'roots':self.remote.roots,'paths':paths}).encode()
            out,_=await asyncio.wait_for(process.communicate(payload),20)
            if process.returncode or len(out)>1024*1024:
                raise ValueError()
            values=json.loads(out)
            if not isinstance(values,list) or len(values)!=len(paths):
                raise ValueError()
            if any(p is not None and (not isinstance(p,str) or not PurePosixPath(p).is_absolute()) for p in values):
                raise ValueError()
            return [PurePosixPath(p) if p else None for p in values]
        except (ValueError,asyncio.TimeoutError,OSError):
            raise AppError('Remote workspace verification failed') from None
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


class Backends:
    def __init__(self, config, local=None, remotes=None):
        self.config=config
        self.local=local or AppServer(config.command,config.codex_home)
        self.remotes=remotes if remotes is not None else {r.alias:SSHServer(r) for r in config.remotes}
        self.verified={}

    @property
    def runs(self):
        result=dict(self.local.runs)
        for alias,app in self.remotes.items():
            result.update({self.qualify(alias,tid):value for tid,value in app.runs.items()})
        return result

    @staticmethod
    def qualify(alias,tid):
        return 'ssh:'+alias+':'+tid

    def route(self,tid):
        if not isinstance(tid,str):
            raise AppError('Invalid task identifier')
        if not tid.startswith('ssh:'):
            return self.local,tid,None
        parts=tid.split(':',2)
        if len(parts)!=3 or parts[1] not in self.remotes or not parts[2] or ':' in parts[2]:
            raise AppError('Unknown task host')
        return self.remotes[parts[1]],parts[2],parts[1]

    async def start(self):
        await self.local.start()

    def path_for(self,thread):
        _,_,alias=self.route(thread['id'])
        if alias is None:
            return allowed_path(thread.get('cwd'),self.config.roots)
        record=self.verified.get(thread['id'])
        return record[1] if record and record[0]==thread.get('cwd') else None

    async def wrap(self,alias,threads):
        if alias is None:
            return [dict(t,host='local') for t in threads]
        app=self.remotes[alias]
        paths=[t.get('cwd') if isinstance(t.get('cwd'),str) else '' for t in threads]
        validated=await app.validate_paths(paths)
        result=[]
        for thread,path in zip(threads,validated):
            tid=self.qualify(alias,thread['id'])
            if path:
                self.verified[tid]=(thread.get('cwd'),path)
            else:
                self.verified.pop(tid,None)
            result.append(dict(thread,id=tid,host=alias))
        return result

    async def thread_list(self,cursor=None):
        # Opaque host+cursor pairs are internal, never accepted from chat.
        aliases=[None,*self.remotes]
        position,inner=(0,None) if cursor is None else cursor
        alias=aliases[position]
        app=self.local if alias is None else self.remotes[alias]
        await app.start()
        result=await app.thread_list(inner)
        items=await self.wrap(alias,result.get('data',[]))
        next_inner=result.get('nextCursor')
        next_cursor=(position,next_inner) if next_inner else ((position+1,None) if position+1<len(aliases) else None)
        return {'data':items,'nextCursor':next_cursor}

    async def thread_read(self,tid,include_turns=False):
        app,raw,alias=self.route(tid)
        await app.start()
        # Authorize metadata before requesting any remote history.
        meta=(await self.wrap(alias,[await app.thread_read(raw)]))[0]
        if not self.path_for(meta):
            raise AppError('Task outside configured workspace')
        if not include_turns:
            return meta
        full=(await self.wrap(alias,[await app.thread_read(raw,include_turns=True)]))[0]
        if not self.path_for(full):
            raise AppError('Workspace changed')
        return full

    async def thread_resume(self,tid,coordinator=False):
        app,raw,alias=self.route(tid)
        await self.thread_read(tid)
        if coordinator and alias is not None:
            raise AppError('Coordinator must be local')
        thread=await app.thread_resume(raw,coordinator=coordinator)
        wrapped=(await self.wrap(alias,[thread]))[0]
        if not self.path_for(wrapped):
            raise AppError('Workspace changed during resume')
        return wrapped

    async def turn_start(self,tid,text,cwd,output_schema=None):
        app,raw,alias=self.route(tid)
        # Revalidate on the owning OS immediately before the side effect.
        thread=await self.thread_read(tid)
        checked=self.path_for(thread)
        if str(checked)!=str(cwd):
            raise AppError('Workspace mismatch')
        return await app.turn_start(raw,text,checked,output_schema=output_schema)

    async def coordinator_start(self,cwd,instructions):
        if not allowed_path(str(cwd),self.config.roots):
            raise AppError('Coordinator workspace not allowed')
        return await self.local.coordinator_start(cwd,instructions)

    async def coordinator_name(self,tid):
        app,raw,alias=self.route(tid)
        if alias is not None:
            raise AppError('Cannot rename a remote task')
        await app.coordinator_name(raw)

    async def turn_interrupt(self,tid,turn_id):
        app,raw,_=self.route(tid)
        return await app.turn_interrupt(raw,turn_id)

    def release(self,tid):
        app,raw,_=self.route(tid)
        app.release(raw)

    async def close(self):
        await asyncio.gather(self.local.close(),*(app.close() for app in self.remotes.values()))
