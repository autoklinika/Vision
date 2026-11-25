"""Public-safe boot status, deliberately not a Core/Runtime report."""
from datetime import datetime, timezone
import re

STATUS_KEYS = frozenset(("schema", "scope", "api", "reportTime", "coreReadiness",
                         "observedAt", "reasonCode", "components"))
_STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def validate_boot_status(value):
    if not isinstance(value, dict) or value.keys() != STATUS_KEYS:
        return False
    stamp = value["reportTime"]
    if not isinstance(stamp, str) or not _STAMP.fullmatch(stamp):
        return False
    try:
        parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    if parsed.year < 1:
        return False
    return (
        value["schema"] == "vision.api.status.v1"
        and value["scope"] == "LAB_API_ONLY"
        and value["api"] == "AVAILABLE"
        and value["coreReadiness"] == "UNKNOWN"
        and value["observedAt"] is None
        and value["reasonCode"] == "CORE_REPORT_NOT_CONNECTED"
        and isinstance(value["components"], list)
        and not value["components"]
    )


def boot_status():
    # API process wall clock, not an observed hardware timestamp.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema": "vision.api.status.v1",
        "scope": "LAB_API_ONLY",
        "api": "AVAILABLE",
        "reportTime": stamp,
        "coreReadiness": "UNKNOWN",
        "observedAt": None,
        "reasonCode": "CORE_REPORT_NOT_CONNECTED",
        "components": [],
    }
