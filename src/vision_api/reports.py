"""Closed wire projections of one existing engine. No workflow construction."""
from datetime import datetime, timezone
import math
import re
from uuid import uuid4

from .access import AccessDenied, Authorizer, Credentials, CursorRejected, ReadGrant, ReportUnavailable

MAX_PROTECTED_BYTES = 131072
MAX_SEQUENCE = 2**53 - 1
MAX_STAGES = 256
MAX_EVENTS = 50
STATES = frozenset({"PENDING", "READY", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "BLOCKED", "TIMED_OUT"})
EVENT_KINDS = frozenset({
    "config_pinned", "transition", "dispatch", "ack", "denied", "result_accepted",
    "result_rejected", "localization_accepted", "context_invalidated", "preparation_verified",
    "planning_verified", "module_verified", "motion_verified", "capture_verified",
    "capture_complete_verified", "quality_verified", "module_archive_verified", "archive_verified", "OTHER",
})
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]+", re.ASCII)
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", re.ASCII)


def _identifier(value, maximum):
    return isinstance(value, str) and 1 <= len(value) <= maximum and IDENTIFIER.fullmatch(value) is not None


def _sequence(value, *, positive=False):
    return type(value) is int and (1 if positive else 0) <= value <= MAX_SEQUENCE


def _utc(value):
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def _timestamp(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ReportUnavailable()
    # isoformat keeps four-digit years consistently across platforms.
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _common(value, schema, fields):
    return (type(value) is dict and set(value) == fields
            and value["schema"] == schema and value["scope"] == "SESSION_READ_ONLY"
            and value["source"] in ("SYNTHETIC_TEST", "STATION")
            and isinstance(value["viewId"], str)
            and re.fullmatch(r"[0-9a-f]{32}", value["viewId"]) is not None
            and _identifier(value["sessionId"], 128) and _utc(value["capturedAt"]))


COMMON = {"schema", "scope", "source", "viewId", "sessionId", "capturedAt"}


def validate_session_report(value):
    if not _common(value, "vision.api.session.v1", COMMON | {"journalSequence", "invalidated", "stages"}):
        return False
    high = value["journalSequence"]
    stages = value["stages"]
    if (not _sequence(high) or type(value["invalidated"]) is not bool
            or type(stages) is not list or not 11 <= len(stages) <= MAX_STAGES):
        return False
    ids = set()
    for stage in stages:
        if type(stage) is not dict or set(stage) != {"id", "state", "historicalSuccess", "lastTransitionSequence", "lastAckSequence"}:
            return False
        if (not _identifier(stage["id"], 64) or stage["id"] in ids
                or not isinstance(stage["state"], str) or stage["state"] not in STATES
                or type(stage["historicalSuccess"]) is not bool):
            return False
        if value["invalidated"] and stage["state"] != "BLOCKED":
            return False
        if stage["state"] == "SUCCEEDED" and not stage["historicalSuccess"]:
            return False
        for key in ("lastTransitionSequence", "lastAckSequence"):
            seq = stage[key]
            if seq is not None and (not _sequence(seq, positive=True) or seq > high):
                return False
        ids.add(stage["id"])
    return {f"S{i:02}" for i in range(1, 12)} <= ids


def validate_events_report(value):
    if not _common(value, "vision.api.events.v1", COMMON | {"throughSequence", "afterSequence", "nextAfterSequence", "events"}):
        return False
    after, through = value["afterSequence"], value["throughSequence"]
    events, next_after = value["events"], value["nextAfterSequence"]
    if not _sequence(after) or not _sequence(through) or after > through or type(events) is not list or len(events) > MAX_EVENTS:
        return False
    previous = after
    for event in events:
        if type(event) is not dict or set(event) != {"sequence", "stageId", "kind", "timestamp", "state"}:
            return False
        seq = event["sequence"]
        if (not _sequence(seq, positive=True) or not previous < seq <= through
                or (event["stageId"] is not None and not _identifier(event["stageId"], 64))
                or not isinstance(event["kind"], str) or event["kind"] not in EVENT_KINDS
                or not _utc(event["timestamp"])
                or (event["state"] is not None and (not isinstance(event["state"], str) or event["state"] not in STATES))):
            return False
        if ((event["kind"] == "transition" and event["state"] is None)
                or (event["kind"] == "localization_accepted" and event["state"] != "SUCCEEDED")
                or (event["kind"] not in ("transition", "localization_accepted") and event["state"] is not None)):
            return False
        previous = seq
    if next_after is None:
        if previous != through:
            return False
    elif (not _sequence(next_after, positive=True) or len(events) != MAX_EVENTS
          or next_after != previous or next_after >= through):
        return False
    return True


class CoreReportProvider:
    """Fixed engine binding. Construct once in its trusted composition owner.

    ``source`` must be chosen explicitly by that owner. API-02 only supplies
    an injected seam and a synthetic test harness, not a station lifecycle.
    """

    def __init__(self, engine, *, source):
        from vision_core.workflow import Workflow
        if not isinstance(engine, Workflow) or source not in ("SYNTHETIC_TEST", "STATION"):
            raise ValueError("invalid provider binding")
        session_id = engine.context.session_id
        if not _identifier(session_id, 128):
            raise ValueError("unsupported session identifier")
        self._engine = engine
        self._source = source
        self._session_id = session_id
        self._view_id = uuid4().hex

    @property
    def session_id(self):
        return self._session_id

    @property
    def view_id(self):
        return self._view_id

    def _base(self, snapshot, schema):
        if snapshot.session_id != self._session_id:
            raise ReportUnavailable()
        return {"schema": schema, "scope": "SESSION_READ_ONLY", "source": self._source,
                "viewId": self._view_id, "sessionId": self._session_id,
                "capturedAt": _timestamp(snapshot.captured_at)}

    def session_report(self):
        try:
            snapshot = self._engine.read_snapshot()
            result = self._base(snapshot, "vision.api.session.v1")
            result.update(journalSequence=snapshot.high_water, invalidated=snapshot.invalidated,
                          stages=[{"id": s.stage_id, "state": s.state.value,
                                   "historicalSuccess": s.historical_success,
                                   "lastTransitionSequence": s.last_transition_sequence,
                                   "lastAckSequence": s.last_ack_sequence} for s in snapshot.stages])
            if not validate_session_report(result):
                raise ReportUnavailable()
            return result
        except Exception:
            raise ReportUnavailable() from None

    def events_report(self, *, view, after, through):
        if view != self._view_id or not _sequence(after) or not _sequence(through) or after > through:
            raise CursorRejected()
        try:
            page = self._engine.read_events(after_sequence=after, limit=MAX_EVENTS, through_sequence=through)
            result = self._base(page, "vision.api.events.v1")
            result.update(throughSequence=page.high_water, afterSequence=page.after_sequence,
                          nextAfterSequence=page.next_after_sequence,
                          events=[{"sequence": e.sequence, "stageId": e.stage_id, "kind": e.kind,
                                   "timestamp": _timestamp(e.timestamp),
                                   "state": e.state.value if e.state is not None else None} for e in page.events])
            if result["throughSequence"] != through or not validate_events_report(result):
                raise ReportUnavailable()
            return result
        except ValueError:
            raise CursorRejected() from None
        except Exception:
            raise ReportUnavailable() from None


class SessionReadService:
    """Authorization and one fixed provider, with no runtime reconfiguration."""

    def __init__(self, *, provider=None, authorizer: Authorizer | None = None):
        if provider is not None and not isinstance(provider, CoreReportProvider):
            raise ValueError("invalid provider")
        if authorizer is not None and not callable(authorizer):
            raise ValueError("invalid authorizer")
        self._provider = provider
        self._authorizer = authorizer

    def _authorize(self, credentials, scope):
        try:
            grant = self._authorizer(credentials) if self._authorizer is not None else None
        except Exception:
            raise AccessDenied() from None
        if type(grant) is not ReadGrant or scope not in grant.scopes:
            raise AccessDenied()
        provider = self._provider
        if provider is None:
            raise ReportUnavailable()
        if grant.session_id != provider.session_id:
            raise AccessDenied()
        return provider

    def session_report(self, credentials: Credentials):
        return self._authorize(credentials, "session:read").session_report()

    def events_report(self, credentials: Credentials, *, view, after, through):
        return self._authorize(credentials, "events:read").events_report(view=view, after=after, through=through)
