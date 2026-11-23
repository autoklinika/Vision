"""Append-only SQLite event journal."""
import json
import sqlite3
import time
import threading
from contextlib import contextmanager
from .models import Event


class Journal:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            step_id TEXT NOT NULL, request_id TEXT NOT NULL, kind TEXT NOT NULL,
            data TEXT NOT NULL, timestamp REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS stage_claims (session_id TEXT NOT NULL, step_id TEXT NOT NULL, PRIMARY KEY(session_id, step_id));
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append only'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append only'); END;''')
        self.db.commit()

    @contextmanager
    def transaction(self):
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def append(self, session_id: str, step_id: str, request_id: str, kind: str, data: dict) -> None:
        with self._lock:
            in_transaction = self.db.in_transaction
            try:
                self.db.execute('INSERT INTO events(session_id,step_id,request_id,kind,data,timestamp) VALUES (?,?,?,?,?,?)',
                                (session_id, step_id, request_id, kind, json.dumps(data, sort_keys=True, allow_nan=False), time.time()))
                if not in_transaction:
                    self.db.commit()
            except BaseException:
                if not in_transaction:
                    self.db.rollback()
                raise

    def replay(self, session_id: str) -> list[Event]:
        rows = self.db.execute('SELECT sequence,session_id,step_id,request_id,kind,data,timestamp FROM events WHERE session_id=? ORDER BY sequence', (session_id,))
        return [Event(*row[:5], json.loads(row[5]), row[6]) for row in rows]

    def close(self) -> None:
        self.db.close()
