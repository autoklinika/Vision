"""Append-only SQLite event journal."""
import json
import sqlite3
import time
from .models import Event


class Journal:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            step_id TEXT NOT NULL, request_id TEXT NOT NULL, kind TEXT NOT NULL,
            data TEXT NOT NULL, timestamp REAL NOT NULL);
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append only'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append only'); END;''')
        self.db.commit()

    def append(self, session_id: str, step_id: str, request_id: str, kind: str, data: dict) -> None:
        with self.db:
            self.db.execute('INSERT INTO events(session_id,step_id,request_id,kind,data,timestamp) VALUES (?,?,?,?,?,?)',
                            (session_id, step_id, request_id, kind, json.dumps(data, sort_keys=True, allow_nan=False), time.time()))

    def replay(self, session_id: str) -> list[Event]:
        rows = self.db.execute('SELECT sequence,session_id,step_id,request_id,kind,data,timestamp FROM events WHERE session_id=? ORDER BY sequence', (session_id,))
        return [Event(*row[:5], json.loads(row[5]), row[6]) for row in rows]

    def close(self) -> None:
        self.db.close()
