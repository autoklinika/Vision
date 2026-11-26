"""Independent, persistent Vision fault episodes; no hardware commands."""
import os
import json
from pathlib import Path
import sqlite3
import stat
import threading
import time

from .luxonis import private_directory
from .nero import fresh, integer
from .nero_diagnostics import CATALOG, SOURCES, entry, decode, validate_entry
from .nero_clear import valid_id, valid_scope, validate_result, result

SCHEMA = "vision.api.nero-history.v1"
PAGE = 50
STATUSES = ("ALL", "ACTIVE", "RESOLVED")


def valid_query(source, status, before):
    return source in ("ALL", *SOURCES) and status in STATUSES and integer(before)


def validate_history(value):
    try:
        if (type(value) is not dict or set(value) != {"schema","source","instanceId","filterSource","filterStatus","before","nextBefore","events"}
                or value["schema"] != SCHEMA or value["source"] != "STATION"
                or not isinstance(value["instanceId"],str) or len(value["instanceId"])!=32
                or not all(c in "0123456789abcdef" for c in value["instanceId"])
                or not valid_query(value["filterSource"],value["filterStatus"],value["before"])
                or type(value["events"]) is not list or len(value["events"]) > PAGE):
            return False
        prev = value["before"] or 2**53
        for row in value["events"]:
            if (type(row) is not dict or set(row) != {"id","event","firstSeen","lastSeen","resolvedAt","status","lastClear"}
                    or not integer(row["id"]) or not 0 < row["id"] < prev
                    or not validate_entry(row["event"]) or row["event"]["severity"] == "INFO"
                    or row["status"] not in STATUSES[1:]
                    or (row["lastClear"] is not None and not validate_result(row["lastClear"]))
                    or not fresh(row["firstSeen"],row["firstSeen"])
                    or not fresh(row["lastSeen"],row["lastSeen"])
                    or row["lastSeen"] < row["firstSeen"]
                    or row["event"]["stamp"] != row["lastSeen"]
                    or (row["status"] == "ACTIVE" and row["resolvedAt"] is not None)
                    or (row["status"] == "RESOLVED" and (not fresh(row["resolvedAt"],row["resolvedAt"]) or row["resolvedAt"] < row["lastSeen"]))
                    or value["filterSource"] not in ("ALL",row["event"]["source"])
                    or value["filterStatus"] not in ("ALL",row["status"])):
                return False
            prev = row["id"]
        return value["nextBefore"] is None or (len(value["events"]) == PAGE and value["nextBefore"] == prev)
    except (KeyError,TypeError,ValueError):
        return False


class FaultHistory:
    def __init__(self, directory):
        root = private_directory(Path(directory))
        path = root / "diagnostics.sqlite3"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink != 1:
                raise ValueError("invalid NERO history database")
        finally:
            os.close(fd)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=1)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, family TEXT NOT NULL,
                code INTEGER NOT NULL, catalog TEXT NOT NULL, description TEXT NOT NULL,
                severity TEXT NOT NULL, first_seen REAL NOT NULL,
                last_seen REAL NOT NULL, resolved_at REAL,
                CHECK(last_seen>=first_seen), CHECK(resolved_at IS NULL OR resolved_at>=last_seen)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS active_episode
                ON episodes(source,family,code) WHERE resolved_at IS NULL;
            CREATE INDEX IF NOT EXISTS episode_filter ON episodes(source,resolved_at,id);
            CREATE TABLE IF NOT EXISTS clear_attempts (
                seq INTEGER PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL,
                scope INTEGER NOT NULL, operator TEXT NOT NULL, started REAL NOT NULL,
                finished REAL, payload TEXT
            );
            CREATE TABLE IF NOT EXISTS clear_episode (
                operation_id TEXT NOT NULL, episode_id INTEGER NOT NULL,
                PRIMARY KEY(operation_id,episode_id)
            );
        """)
        with self.db:
            # Crash during a command is ambiguous, never replay it on restart.
            for row in self.db.execute("SELECT * FROM clear_attempts WHERE payload IS NULL").fetchall():
                v=result(row["operation_id"],row["scope"],"UNVERIFIED","INTERRUPTED",invoked=None)
                self.db.execute("UPDATE clear_attempts SET finished=?,payload=? WHERE operation_id=?",
                                (max(time.time(),row["started"]),json.dumps(v,allow_nan=False),row["operation_id"]))
        self._scope_stamps = {}
        self._last_seen = {}

    def observe(self, report):
        conditions, coverage = decode(report)
        current = {(e["source"],e["family"],e["code"]) for e in conditions if e["severity"] != "INFO"}
        with self.lock:
            with self.db:
                active = {(r["source"],r["family"],r["code"]):r for r in self.db.execute(
                    "SELECT * FROM episodes WHERE resolved_at IS NULL")}
                updated = {}
                for scope, stamp in coverage.items():
                    if stamp <= self._scope_stamps.get(scope, 0):
                        continue
                    present = {key for key in current if key[:2] == scope}
                    for key in present:
                        row = active.get(key)
                        if row is None:
                            observed=entry(*key,stamp)
                            self.db.execute("INSERT INTO episodes(source,family,code,catalog,description,severity,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?)",
                                            (*key,CATALOG,observed["description"],observed["severity"],stamp,stamp))
                        elif stamp >= row["last_seen"] + 5:
                            # Bound writes during persistent faults. Flush exact
                            # last observed time when resolving or cleanly closing.
                            self.db.execute("UPDATE episodes SET last_seen=? WHERE id=?", (stamp,row["id"]))
                    for key, row in active.items():
                        if key[:2] != scope or key in present or stamp < row["last_seen"]:
                            continue
                        last = max(row["last_seen"], self._last_seen.get(key,0))
                        if stamp >= last:
                            self.db.execute("UPDATE episodes SET last_seen=?,resolved_at=? WHERE id=?", (last,stamp,row["id"]))
                    updated[scope] = stamp
                # Commit first, then advance in-memory observation watermarks.
            self._scope_stamps.update(updated)
            for key in tuple(self._last_seen):
                if key[:2] in updated and key not in current:
                    del self._last_seen[key]
            for key in current:
                if key[:2] in updated:
                    self._last_seen[key] = updated[key[:2]]

    def page(self, instance, source="ALL", status="ALL", before=0):
        if not valid_query(source,status,before):
            raise ValueError("invalid NERO history query")
        clauses, args = [], []
        if source != "ALL":
            clauses.append("source=?"); args.append(source)
        if status != "ALL":
            clauses.append("resolved_at IS " + ("NULL" if status=="ACTIVE" else "NOT NULL"))
        if before:
            clauses.append("id<?"); args.append(before)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.lock:
            rows = self.db.execute("SELECT * FROM episodes"+where+" ORDER BY id DESC LIMIT ?", (*args,PAGE+1)).fetchall()
            events=[]
            for row in rows[:PAGE]:
                key = (row["source"],row["family"],row["code"])
                last = max(row["last_seen"], self._last_seen.get(key,0)) if row["resolved_at"] is None else row["last_seen"]
                clear=self.db.execute("""SELECT a.payload FROM clear_attempts a JOIN clear_episode l
                    ON a.operation_id=l.operation_id WHERE l.episode_id=? AND a.payload IS NOT NULL ORDER BY a.seq DESC LIMIT 1""",
                    (row["id"],)).fetchone()
                observed=entry(*key,last)
                if (row["catalog"],row["description"],row["severity"])!=(CATALOG,observed["description"],observed["severity"]):
                    raise ValueError("NERO history catalog revision requires an explicit migration")
                events.append({"id":row["id"],"event":observed,"firstSeen":row["first_seen"],
                               "lastClear":json.loads(clear["payload"]) if clear else None,
                               "lastSeen":last,"resolvedAt":row["resolved_at"],
                               "status":"ACTIVE" if row["resolved_at"] is None else "RESOLVED"})
        return {"schema":SCHEMA,"source":"STATION","instanceId":instance,"filterSource":source,
                "filterStatus":status,"before":before,"nextBefore":events[-1]["id"] if len(rows)>PAGE else None,"events":events}

    def begin_clear(self,operation,scope,operator,now):
        """Durably reserve ID before any dispatch; duplicate IDs never resend."""
        if not valid_id(operation) or not valid_scope(scope):
            raise ValueError("invalid operation")
        with self.lock, self.db:
            row=self.db.execute("SELECT * FROM clear_attempts WHERE operation_id=?",(operation,)).fetchone()
            if row is not None:
                if (row["scope"],row["operator"])!=(scope,operator):
                    raise ValueError("operation identity mismatch")
                return json.loads(row["payload"]) if row["payload"] else result(operation,scope,"UNVERIFIED","INTERRUPTED",invoked=None)
            self.db.execute("INSERT INTO clear_attempts(operation_id,scope,operator,started) VALUES(?,?,?,?)",
                            (operation,scope,operator,now))
            sql="""INSERT INTO clear_episode(operation_id,episode_id) SELECT ?,id FROM episodes
                    WHERE resolved_at IS NULL AND source!='ARM'"""
            args=[operation]
            if scope!=255:
                sql+=" AND source=?";args.append(f"J{scope}")
            self.db.execute(sql,args)
            return None

    def finish_clear(self,operation,value,now):
        if not validate_result(value) or operation!=value["operationId"]:
            raise ValueError("invalid clear result")
        with self.lock,self.db:
            cur=self.db.execute("UPDATE clear_attempts SET finished=MAX(started,?),payload=? WHERE operation_id=? AND payload IS NULL AND scope=?",
                (now,json.dumps(value,allow_nan=False,separators=(",",":")),operation,value["scope"]))
            if cur.rowcount!=1:
                raise ValueError("clear reservation missing")
        return value

    def attempts(self,instance,source="ALL",before=0):
        if source not in ("ALL",*SOURCES) or not integer(before):
            raise ValueError("invalid attempts query")
        clauses=["payload IS NOT NULL"];args=[]
        if source=="ARM":clauses.append("0")
        elif source!="ALL":
            clauses.append("(scope=? OR scope=255)");args.append(int(source[1:]))
        if before:clauses.append("seq<?");args.append(before)
        with self.lock:
            rows=self.db.execute("SELECT * FROM clear_attempts WHERE "+" AND ".join(clauses)+" ORDER BY seq DESC LIMIT ?",(*args,21)).fetchall()
        events=[{"id":r["seq"],"startedAt":r["started"],"finishedAt":r["finished"],"operation":json.loads(r["payload"])} for r in rows[:20]]
        return {"schema":"vision.api.nero-clear-history.v1","source":"STATION","instanceId":instance,
                "filterSource":source,"before":before,"nextBefore":events[-1]["id"] if len(rows)>20 else None,"events":events}

    def close(self):
        with self.lock, self.db:
            for key, stamp in self._last_seen.items():
                self.db.execute("UPDATE episodes SET last_seen=MAX(last_seen,?) WHERE source=? AND family=? AND code=? AND resolved_at IS NULL",
                                (stamp,*key))
        self.db.close()


class HistorySampler:
    """Runs with the independent Core owner, never with browser polling."""
    def __init__(self, history, monitor, instance):
        self.history, self.monitor, self.instance = history, monitor, instance
        self.stop = threading.Event()
        self.available = False
        self.thread = threading.Thread(target=self._run, name="nero-history", daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            try:
                self.history.observe(self.monitor.report(self.instance()))
                self.available = True
            except Exception:
                self.available = False
            self.stop.wait(.4)

    def close(self):
        self.stop.set()
        self.thread.join()
        self.history.close()


def validate_attempts(v):
    try:
        if (type(v) is not dict or set(v)!={"schema","source","instanceId","filterSource","before","nextBefore","events"}
                or v["schema"]!="vision.api.nero-clear-history.v1" or v["source"]!="STATION" or not valid_id(v["instanceId"])
                or v["filterSource"] not in ("ALL",*SOURCES) or not integer(v["before"])
                or type(v["events"]) is not list or len(v["events"])>20):
            return False
        prev=v["before"] or 2**53
        for row in v["events"]:
            if (type(row) is not dict or set(row)!={"id","startedAt","finishedAt","operation"}
                    or not integer(row["id"]) or not 0<row["id"]<prev
                    or not fresh(row["startedAt"],row["startedAt"])
                    or not fresh(row["finishedAt"],row["finishedAt"]) or row["finishedAt"]<row["startedAt"]
                    or not validate_result(row["operation"])):
                return False
            scope=row["operation"]["scope"]
            if v["filterSource"]!="ALL" and (v["filterSource"]=="ARM" or scope not in (255,int(v["filterSource"][1:]))):return False
            prev=row["id"]
        return v["nextBefore"] is None or (len(v["events"])==20 and v["nextBefore"]==prev)
    except (KeyError,TypeError,ValueError):
        return False
