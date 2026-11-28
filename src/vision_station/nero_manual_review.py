"""Station commissioning review: real telemetry, no hardware command path.

A verified review candidate is not an accepted physical motion profile.
This Core specialization owns a separate review library and has no
manual transport, inspection composition, IR controller or error-clear
transport. It cannot construct a native owner or publish a motion command.
"""
from .host import CoreHost
from .inspection import InspectionRejected
from .nero_manual_composition import review_profile
from .nero_manual_api import status
from .nero_manual_station import Candidate
from .nero_tcp import project


REASON = "REVIEW_ONLY"


class ManualReviewHost(CoreHost):
    def __init__(self, library_root, *, candidate, nero_directory,
                 nero_joint_limits=None):
        if not isinstance(candidate, Candidate) or nero_directory is None:
            raise ValueError("review candidate and live observer required")
        self._profile = review_profile(candidate)
        super().__init__(library_root, nero_directory=nero_directory,
                         nero_joint_limits=nero_joint_limits)

    def nero_manual_report(self):
        instance = self.station_report()["instanceId"]
        telemetry = project(self.nero_report())
        return status(instance, {
            "state": "IDLE", "reason": REASON,
            "driveEnabled": telemetry["driveEnabled"],
            "pipelineReady": False, "enableAvailable": False,
            "jogAvailable": False, "holdAvailable": False,
            "linearMax": self._profile.linear_max,
            "angularMax": self._profile.angular_max,
        })

    def attach_runtime(self, runtime):
        raise InspectionRejected()

    def start_inspection(self, **intent):
        raise InspectionRejected()
