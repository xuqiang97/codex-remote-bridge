import os
import sqlite3
import time


class State:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = open(str(path) + '.lock', 'a+b')
        try:
            self.lock_file.seek(0)
            if self.lock_file.read(1) == b'':
                self.lock_file.write(b'0'); self.lock_file.flush()
            self.lock_file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            raise RuntimeError('Another bridge is using this state file') from None
        self.db = sqlite3.connect(path)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS bindings(channel TEXT, conversation_id TEXT, thread_id TEXT,
        updated_at INTEGER, PRIMARY KEY(channel,conversation_id));
        CREATE TABLE IF NOT EXISTS seen_messages(channel TEXT, message_id TEXT, seen_at INTEGER,
        PRIMARY KEY(channel,message_id));
        CREATE TABLE IF NOT EXISTS coordinators(channel TEXT, conversation_id TEXT, sender_id TEXT,
        thread_id TEXT, PRIMARY KEY(channel,conversation_id));
        CREATE TABLE IF NOT EXISTS dispatches(id INTEGER PRIMARY KEY, channel TEXT,
        conversation_id TEXT, thread_id TEXT, turn_id TEXT, status TEXT, updated_at INTEGER);
        ''')
        self.cleanup()
        with self.db:
            self.db.execute("UPDATE dispatches SET status='unknown' WHERE status IN ('starting','running')")

    def coordinator(self, key):
        return self.db.execute('SELECT sender_id,thread_id FROM coordinators WHERE channel=? AND conversation_id=?', key).fetchone()

    def set_coordinator(self, key, sender, tid):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO coordinators VALUES(?,?,?,?)', (*key, sender, tid))

    def coordinator_ids(self):
        return {r[0] for r in self.db.execute('SELECT thread_id FROM coordinators')}

    def dispatch(self, key, tid):
        with self.db:
            c = self.db.execute("INSERT INTO dispatches(channel,conversation_id,thread_id,turn_id,status,updated_at) VALUES(?,?,?,NULL,'starting',?)", (*key, tid, int(time.time())))
            return c.lastrowid

    def update_dispatch(self, identity, status, turn_id=None):
        with self.db:
            self.db.execute('UPDATE dispatches SET status=?,turn_id=COALESCE(?,turn_id),updated_at=? WHERE id=?', (status,turn_id,int(time.time()),identity))

    def recent_dispatches(self, key):
        return [dict(zip(('thread_id','turn_id','status','updated_at'), r)) for r in self.db.execute('SELECT thread_id,turn_id,status,updated_at FROM dispatches WHERE channel=? AND conversation_id=? ORDER BY id DESC LIMIT 20', key)]

    def reserve(self, channel, mid, now=None):
        now = int(time.time()) if now is None else now
        with self.db:
            self.db.execute('DELETE FROM seen_messages WHERE seen_at < ?', (now-7*86400,))
            if self.db.execute('SELECT count(*) FROM seen_messages').fetchone()[0] >= 100000:
                raise RuntimeError('Dedupe capacity exceeded')
            c = self.db.execute('INSERT OR IGNORE INTO seen_messages VALUES(?,?,?)', (channel, mid, now))
            return c.rowcount == 1

    def cleanup(self, now=None):
        with self.db:
            self.db.execute('DELETE FROM seen_messages WHERE seen_at < ?', ((int(time.time()) if now is None else now)-7*86400,))

    def get(self, channel, conversation):
        row = self.db.execute('SELECT thread_id FROM bindings WHERE channel=? AND conversation_id=?', (channel, conversation)).fetchone()
        return row[0] if row else None

    def bind(self, channel, conversation, tid):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO bindings VALUES(?,?,?,?)', (channel, conversation, tid, int(time.time())))

    def unbind(self, channel, conversation):
        with self.db:
            self.db.execute('DELETE FROM bindings WHERE channel=? AND conversation_id=?', (channel, conversation))

    def close(self):
        self.db.close()
        self.lock_file.close()
