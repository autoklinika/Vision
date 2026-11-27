"""Closed manual Luxonis IR command. No generic ROS parameter or shell API."""
import json
import math
import os
import re
import subprocess

from vision_api.access import ReportUnavailable

SCHEMA = "vision.api.luxonis-ir.v1"
KEYS = {"dot": "driver.r_laser_dot_intensity", "flood": "driver.r_floodlight_intensity"}
GATE = "driver.i_enable_ir"
ON = 0.6


class IRRejected(Exception):
    """The station or the selected camera cannot admit this command."""


def valid_level(value):
    return type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1


def validate_request(value):
    return (type(value) is dict and set(value) == {"instanceId", "channel", "enabled"}
            and isinstance(value["instanceId"], str) and re.fullmatch(r"[0-9a-f]{32}", value["instanceId"])
            and isinstance(value["channel"], str) and value["channel"] in KEYS
            and type(value["enabled"]) is bool)


def controllable(report):
    return (report["previewAllowed"] and report["observer"] == "ACTIVE"
            and report["graph"] == "ACTIVE" and report["node"] == {"domain":186,"name":"/oak"}
            and report["hardwareConnection"] == "USB_DETECTED"
            and all(s == "AVAILABLE" for s in report["endpoints"].values())
            and report["settings"].get(GATE) is True
            and all(valid_level(report["settings"].get(k)) for k in KEYS.values()))


def validate_result(value):
    try:
        return (type(value) is dict and set(value) == {"schema","source","instanceId","channel","enabled","dot","flood","capturedAt"}
                and value["schema"] == SCHEMA and value["source"] == "STATION"
                and validate_request({k:value[k] for k in ("instanceId","channel","enabled")})
                and all(valid_level(value[k]) for k in KEYS)
                and type(value["capturedAt"]) in (int,float) and math.isfinite(value["capturedAt"])
                and 0 < value["capturedAt"] < 253402300800
                and abs(value[value["channel"]] - (ON if value["enabled"] else 0.0)) < 1e-6)
    except (TypeError, ValueError, KeyError):
        return False


class IRController:
    """Invoke only a fixed system-Python ROS adapter, never caller-controlled code."""
    def __init__(self, *, run=subprocess.run):
        self.run = run

    def change(self, instance_id, channel, enabled):
        if not validate_request({"instanceId":instance_id,"channel":channel,"enabled":enabled}):
            raise ValueError("invalid IR command")
        env = dict(os.environ, ROS_DOMAIN_ID="186", ROS_LOCALHOST_ONLY="1",
                   ROS_HOME="/srv/vision-data/tools/vision-luxonis/ros",
                   ROS_LOG_DIR="/srv/vision-data/tools/vision-luxonis/ros/log",
                   PYTHONDONTWRITEBYTECODE="1", TMPDIR="/srv/vision-data/tmp")
        # No interpolated shell code. Only two allowlisted channel names and
        # a boolean token are arguments. The fixed adapter performs readback.
        try:
            result = self.run(["/bin/bash", "-c",
                'source /opt/ros/jazzy/setup.bash; exec /usr/bin/python3 -B -m vision_station.ros_luxonis_ir "$@"',
                "vision-luxonis-ir", channel, "on" if enabled else "off"],
                env=env, capture_output=True, text=True, timeout=7.0, check=False)
            if result.returncode == 2:
                raise IRRejected()
            if result.returncode or len(result.stdout)>1024:
                raise ReportUnavailable()
            data=json.loads(result.stdout)
            if type(data) is not dict or set(data)!={"dot","flood","capturedAt"}:
                raise ReportUnavailable()
            report={"schema":SCHEMA,"source":"STATION","instanceId":instance_id,
                    "channel":channel,"enabled":enabled,**data}
            if not validate_result(report):
                raise ReportUnavailable()
            return report
        except (IRRejected, ReportUnavailable):
            raise
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            raise ReportUnavailable() from None
