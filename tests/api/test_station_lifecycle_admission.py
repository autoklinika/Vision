"""Busy authoring must not defer short operational requests past their response."""
import threading
import unittest
from unittest.mock import patch

import test_draft_editor as fixture
from vision_api.access import ReportUnavailable
from vision_station.client import RemoteStationOwner
from vision_station.inspection import InspectionRejected
from vision_station.server import CoreServer


class LifecycleAdmissionTests(unittest.TestCase):
    setUp=fixture.DraftEditorTests.setUp

    def _assert_busy_rejected(self, method, error):
        socket=self.root/"ipc/core.sock"
        server=CoreServer(socket,self.host)
        serving=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
        serving.start()
        proxy=RemoteStationOwner(socket)
        entered=threading.Event();release=threading.Event()
        def hold_editor_lock():
            with self.host._lifecycle_lock:
                entered.set()
                release.wait(5)
        holder=threading.Thread(target=hold_editor_lock)
        returned=(self.host.inspection_report() if method=="report" else self.host.station_report())
        with patch.object(self.host._inspection,method,return_value=returned) as operation:
            holder.start()
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(error):
                    if method=="report":
                        proxy.inspection_report()
                    elif method=="start":
                        proxy.start_inspection(selection_id="synthetic",instance_id=self.instance,
                            intent_token="a"*32,operator="test.operator")
                    else:
                        proxy.close_inspection(session_id="synthetic",instance_id=self.instance,
                            operator="test.operator")
                operation.assert_not_called()
            finally:
                release.set();holder.join(3)
                server.shutdown();serving.join(3);server.server_close()
            # Joining server workers also rules out dispatch after caller timeout.
            operation.assert_not_called()
        self.assertEqual(self.host.station_report()["state"],"NO_ACTIVE_SESSION")

    def test_busy_inspection_read_is_unavailable_without_late_dispatch(self):
        self._assert_busy_rejected("report",ReportUnavailable)

    def test_busy_start_is_rejected_without_late_dispatch(self):
        self._assert_busy_rejected("start",InspectionRejected)

    def test_busy_close_is_rejected_without_late_dispatch(self):
        self._assert_busy_rejected("close",InspectionRejected)


if __name__=="__main__":unittest.main()
