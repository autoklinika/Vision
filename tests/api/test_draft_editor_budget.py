"""Real IPC at a valid near-limit history and bounded editor admission."""
import copy
import fcntl
import os
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_draft_editor as fixture
from vision_api.access import Credentials
from vision_modules.ecu_library_backend.storage import MAX_READ_BYTES, DraftReadUnavailable, _snapshot_hash
from vision_station.client import RemoteStationOwner
from vision_station.draft_editor import DraftConflict
from vision_station.server import CoreServer


class DraftEditorBudgetTests(unittest.TestCase):
    setUp=fixture.DraftEditorTests.setUp

    def _proxy(self):
        sock=self.root/"ipc/core.sock"
        server=CoreServer(sock,self.host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
        thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        return RemoteStationOwner(sock)

    def _create_args(self):
        return dict(instanceId=self.instance,family="neutral-family",variant="neutral-variant",
                    key=self.key,revision="r1",displayName="Synthetic history budget")

    def _seed_history(self, total):
        # A fixture builder avoids O(n squared) authoring just to reach a valid
        # persisted state. Every envelope/hash/link is checked by the real reader.
        store=self.host.library.store
        with store.transaction():
            pointer_path=store.root/"drafts"/(self.key+".json")
            previous=json.loads(pointer_path.read_bytes())["generation"]
            first=json.loads((store.root/"history"/(self.key+"--"+previous+".json")).read_bytes())
            for index in range(total-1):
                generation=f"{index:032x}"
                snapshot={k:v for k,v in first.items() if k!="snapshot_sha256"}
                snapshot.update(generation=generation,previous=previous)
                snapshot["snapshot_sha256"]=_snapshot_hash(snapshot)
                data=json.dumps(snapshot,ensure_ascii=True,separators=(",",":"))
                (store.root/"history"/(self.key+"--"+generation+".json")).write_text(data,encoding="ascii")
                previous=generation
            pointer_path.write_text(json.dumps(dict(key=self.key,generation=previous),separators=(",",":")),encoding="ascii")
        byte_count=pointer_path.stat().st_size+sum(p.stat().st_size for p in (store.root/"history").iterdir())
        self.assertLess(byte_count,MAX_READ_BYTES)

    def test_near_budget_history_is_available_through_real_ipc(self):
        self.host.draft_editor("create_empty",self._create_args())
        self._seed_history(3000)
        proxy=self._proxy()
        args=dict(instanceId=self.instance,key=self.key)
        opened=proxy.draft_editor("open",args)
        doc=copy.deepcopy(opened["document"])
        doc["identity"]["manufacturer"]="Synthetic budget check"
        saved=proxy.draft_editor("save",{**args,"etag":opened["etag"],"document":doc})
        self.assertNotEqual(saved["etag"],opened["etag"])
        self.assertEqual(saved["document"],doc)
        cloned=proxy.draft_editor("clone",{**args,"etag":saved["etag"],"newKey":"synthetic-copy","newRevision":"r2"})
        self.assertEqual(cloned["document"]["identity"],doc["identity"])
        report=proxy.library_reader.library_report(Credentials())
        entry=next(e for e in report["entries"] if e["kind"]=="REFERENCE_DRAFT" and e["profileId"]==self.key)
        detail=proxy.library_reader.entry_report(Credentials(),entry_id=entry["entryId"],view=report["viewId"])
        self.assertEqual(detail["profile"]["historyCount"],3001)
        history=proxy.library_reader.history_report(Credentials(),entry_id=entry["entryId"],view=report["viewId"],after=0)
        self.assertEqual(history["totalCount"],3001)
        self.assertEqual(self.host.station_report()["state"],"NO_ACTIVE_SESSION")

    def test_busy_owner_rejects_without_late_mutation(self):
        proxy=self._proxy()
        entered=threading.Event();release=threading.Event()
        def hold_lifecycle():
            with self.host._lifecycle_lock:
                entered.set()
                release.wait(5)
        holder=threading.Thread(target=hold_lifecycle)
        holder.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(DraftConflict):
                proxy.draft_editor("create_empty",self._create_args())
            self.assertTrue(holder.is_alive())
            self.assertEqual(self.host.library.store.keys(),[])
        finally:
            release.set();holder.join(3)
        self.assertEqual(self.host.library.store.keys(),[])
        created=proxy.draft_editor("create_empty",self._create_args())
        self.assertEqual(created["key"],self.key)

    def test_external_store_lock_rejects_without_late_mutation(self):
        proxy=self._proxy()
        store=self.host.library.store
        with store.transaction():
            pass
        fd=os.open(store.root/".lock",os.O_RDWR)
        try:
            # A distinct open description represents another process owner.
            fcntl.flock(fd,fcntl.LOCK_EX)
            with self.assertRaises(DraftConflict):
                proxy.draft_editor("create_empty",self._create_args())
            self.assertEqual(store.keys(),[])
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
        self.assertEqual(store.keys(),[])
        self.assertEqual(proxy.draft_editor("create_empty",self._create_args())["key"],self.key)

    def test_thread_store_lock_rejects_without_late_mutation(self):
        proxy=self._proxy()
        store=self.host.library.store
        entered=threading.Event();release=threading.Event()
        def hold_store():
            with store.lock:
                entered.set()
                release.wait(5)
        holder=threading.Thread(target=hold_store)
        holder.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(DraftConflict):
                proxy.draft_editor("create_empty",self._create_args())
            self.assertTrue(holder.is_alive())
            self.assertEqual(store.keys(),[])
        finally:
            release.set();holder.join(3)
        self.assertEqual(store.keys(),[])
        self.assertEqual(proxy.draft_editor("create_empty",self._create_args())["key"],self.key)

    def test_store_wait_expiration_is_checked_before_retrying_free_lock(self):
        store=self.host.library.store
        with store.transaction():
            pass
        fd=os.open(store.root/".lock",os.O_RDWR)
        clock=[100.0]
        def resume_after_deadline(_delay):
            # Deterministic scheduling pause: the other owner releases while
            # this waiter is suspended past its admission deadline.
            fcntl.flock(fd,fcntl.LOCK_UN)
            clock[0]+=1
        fake_time=SimpleNamespace(monotonic=lambda:clock[0],sleep=resume_after_deadline)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            with patch("vision_modules.ecu_library_backend.storage.time",fake_time):
                with self.assertRaises(DraftReadUnavailable) as rejected:
                    with store.transaction(timeout=.25):
                        self.fail("Expired waiter was admitted")
            self.assertEqual(rejected.exception.reason,"LIBRARY_BUSY")
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
        with store.transaction(timeout=0):
            pass

    def test_store_thread_lock_cannot_consume_the_file_lock_deadline(self):
        store=self.host.library.store
        clock=[100.0]
        actual_lock=store.lock
        def acquire_after_deadline(**kwargs):
            acquired=actual_lock.acquire(**kwargs)
            clock[0]+=1
            return acquired
        delayed_lock=SimpleNamespace(acquire=acquire_after_deadline,release=actual_lock.release)
        fake_time=SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda _delay:None)
        with patch.object(store,"lock",delayed_lock), patch("vision_modules.ecu_library_backend.storage.time",fake_time):
            with self.assertRaises(DraftReadUnavailable) as rejected:
                with store.transaction(timeout=.25):
                    self.fail("Consumed admission deadline was ignored")
        self.assertEqual(rejected.exception.reason,"LIBRARY_BUSY")
        with store.transaction(timeout=0):
            pass


if __name__=="__main__":unittest.main()
