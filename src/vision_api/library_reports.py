"""Closed, read-only transport for an existing ECU library owner.

No storage constructor, reference validation command, release, specimen
selection or operational readiness evaluation is reachable through these reads.
"""
import hashlib
import json
import re
import unicodedata

from .access import (AccessDenied, Credentials, CursorRejected, LibraryAuthorizer,
                     LibraryReadGrant, ReportUnavailable)
from .reports import _timestamp, _utc

PAGE_SIZE = 50
MAX_ENTRIES = 512
MAX_HISTORY = 4096
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
SECTION_NAMES = (
    "metadata", "identity", "physical_states", "coordinate_systems", "geometry",
    "connectors_landmarks", "reference_assets", "recognition_rules",
    "localization_rules", "pcb_definition", "photography_recipes", "thermal_recipes",
    "inspection_workflows", "validation_policies", "provenance_release",
)
SCOPES = ("browse_and_select", "verify_identity", "localize", "photo_inspection",
          "thermal_relative", "thermal_radiometric")
COMMON = {"schema", "scope", "source", "libraryId", "viewId", "capturedAt"}
ENTRY_FIELDS = {"entryId", "kind", "profileId", "family", "variant", "revision",
                "displayName", "status", "readiness", "reasonCode", "etag"}


def _object(value, keys):
    return type(value) is dict and set(value) == keys


def _id(value):
    return isinstance(value, str) and IDENT.fullmatch(value) is not None


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % size, value) is not None


def _text(value, maximum):
    return (isinstance(value, str) and 1 <= len(value) <= maximum
            and value.strip() != "" and "/" not in value and "\\" not in value
            and not any(unicodedata.category(c).startswith("C") for c in value))


def _etag(value):
    return isinstance(value, str) and re.fullmatch(r'"[0-9a-f]{64}"', value) is not None


def _count(value, maximum=1_000_000, minimum=0):
    return type(value) is int and minimum <= value <= maximum


def _common(value, schema, fields):
    return (_object(value, COMMON | fields) and value["schema"] == schema
            and value["scope"] == "LIBRARY_READ_ONLY"
            and value["source"] in ("SYNTHETIC_TEST", "STATION")
            and _id(value["libraryId"]) and _hex(value["viewId"], 64)
            and _utc(value["capturedAt"]))


def _entry(value):
    if (not _object(value, ENTRY_FIELDS) or not _hex(value["entryId"], 32)
            or not all(_id(value[k]) for k in ("profileId", "family", "variant", "revision"))
            or not _text(value["displayName"], 160) or value["readiness"] != "NOT_READY"):
        return False
    if value["kind"] == "CATALOG_RECORD":
        return (value["status"] in ("DRAFT", "READY_FOR_REVIEW", "APPROVED")
                and value["reasonCode"] == "CATALOG_ONLY" and value["etag"] is None)
    return (value["kind"] == "REFERENCE_DRAFT" and value["status"] == "DRAFT"
            and value["reasonCode"] == "UNSIGNED_DRAFT" and _etag(value["etag"]))


def _page(value, items, maximum, *, empty=True):
    after, total, next_after = value["after"], value["totalCount"], value["nextAfter"]
    if (not _count(total, maximum, 0 if empty else 1) or not _count(after, maximum)
            or after % PAGE_SIZE != 0 or type(items) is not list
            or after > total or (after == total and total != 0)
            or len(items) != min(PAGE_SIZE, total - after)):
        return False
    expected = after + len(items) if after + len(items) < total else None
    return (next_after is None if expected is None
            else type(next_after) is int and next_after == expected)


def validate_library_report(value):
    if not _common(value, "vision.api.library.v1", {"after", "totalCount", "nextAfter", "entries"}):
        return False
    entries = value["entries"]
    return (_page(value, entries, MAX_ENTRIES) and all(_entry(e) for e in entries)
            and len({e["entryId"] for e in entries}) == len(entries))


def validate_library_entry_report(value):
    if (not _common(value, "vision.api.library-entry.v1", {"entry", "catalog", "profile"})
            or not _entry(value["entry"])):
        return False
    catalog, profile = value["catalog"], value["profile"]
    if value["entry"]["kind"] == "CATALOG_RECORD":
        if (profile is not None or not _object(catalog, {"connectors", "fieldNoteCount", "fieldNotesVerified", "envelopePresent"})
                or not _count(catalog["fieldNoteCount"]) or catalog["fieldNotesVerified"] is not False
                or type(catalog["envelopePresent"]) is not bool
                or type(catalog["connectors"]) is not list or len(catalog["connectors"]) > 64):
            return False
        rows = catalog["connectors"]
        return (all(_object(r, {"id", "color"}) and _id(r["id"]) and r["color"] in ("black", "gray", "other") for r in rows)
                and len({r["id"] for r in rows}) == len(rows))
    if (catalog is not None or not _object(profile, {"sections", "physicalStates", "workflows", "historyCount"})
            or not _count(profile["historyCount"], MAX_HISTORY, 1)):
        return False
    sections, states, workflows = profile["sections"], profile["physicalStates"], profile["workflows"]
    if (type(sections) is not list or len(sections) != len(SECTION_NAMES)
            or type(states) is not list or len(states) > 128
            or type(workflows) is not list or len(workflows) > 128):
        return False
    for name, section in zip(SECTION_NAMES, sections):
        if (not _object(section, {"name", "rowCount", "status"}) or section["name"] != name
                or section["status"] != "NOT_EVALUATED"
                or (section["rowCount"] is not None and not _count(section["rowCount"]))):
            return False
    if not all(_object(s, {"id", "displayName", "declaredVerified"}) and _id(s["id"])
               and _text(s["displayName"], 160) and type(s["declaredVerified"]) is bool for s in states):
        return False
    state_ids = {s["id"] for s in states}
    return (len(state_ids) == len(states)
            and all(_object(w, {"id", "stateId", "scope"}) and _id(w["id"])
                    and _id(w["stateId"]) and w["stateId"] in state_ids and w["scope"] in SCOPES for w in workflows)
            and len({w["id"] for w in workflows}) == len(workflows))


def validate_library_history_report(value):
    if (not _common(value, "vision.api.library-history.v1",
                    {"entryId", "profileId", "revision", "etag", "after", "totalCount", "nextAfter", "items"})
            or not _hex(value["entryId"], 32) or not _id(value["profileId"])
            or not _id(value["revision"]) or not _etag(value["etag"])
            or not _page(value, value["items"], MAX_HISTORY, empty=False)):
        return False
    rows = value["items"]
    if not all(_object(r, {"snapshotId", "etag", "revision"}) and _hex(r["snapshotId"], 32)
               and _etag(r["etag"]) and r["revision"] == value["revision"] for r in rows):
        return False
    return (len({r["snapshotId"] for r in rows}) == len(rows)
            and len({r["etag"] for r in rows}) == len(rows)
            and (all(r["etag"] != value["etag"] for r in rows) if value["nextAfter"] is not None
                 else rows[-1]["etag"] == value["etag"]))


def _entry_id(kind, summary):
    identity = (kind, summary.profile_id, summary.family, summary.variant, summary.revision)
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode("ascii")).hexdigest()[:32]


def _summary(kind, summary):
    return {"entryId": _entry_id(kind, summary), "kind": kind,
            "profileId": summary.profile_id, "family": summary.family,
            "variant": summary.variant, "revision": summary.revision,
            "displayName": summary.display_name, "status": summary.status,
            "readiness": summary.readiness, "reasonCode": summary.reason_code,
            "etag": summary.etag if kind == "REFERENCE_DRAFT" else None}


def _slice(items, after):
    total = len(items)
    if (not _count(after, MAX_HISTORY) or after % PAGE_SIZE
            or after > total or (after == total and total != 0)):
        raise CursorRejected()
    page = items[after:after + PAGE_SIZE]
    return {"after": after, "totalCount": total,
            "nextAfter": after + len(page) if after + len(page) < total else None}, page


class LibraryReportProvider:
    """Composition binds one already-initialized owner and an explicit source."""

    def __init__(self, service, *, library_id, source):
        from vision_modules.ecu_library_backend import ECULibraryService
        from vision_modules.ecu_library_backend.read_model import LibraryReadModel
        if not isinstance(service, ECULibraryService) or not _id(library_id) or source not in ("SYNTHETIC_TEST", "STATION"):
            raise ValueError("invalid provider binding")
        self._model = LibraryReadModel(service)
        self._library_id = library_id
        self._source = source

    @property
    def library_id(self):
        return self._library_id

    def _read(self, view=None):
        snapshot = self._model.capture()
        if not _hex(snapshot.view_id, 64):
            raise ReportUnavailable()
        if view is not None and (not _hex(view, 64) or view != snapshot.view_id):
            raise CursorRejected()
        entries = [(_summary("CATALOG_RECORD", d.summary), d) for d in snapshot.catalog]
        entries += [(_summary("REFERENCE_DRAFT", d.summary), d) for d in snapshot.profiles]
        entries.sort(key=lambda e: tuple(e[0][k] for k in ("kind", "family", "variant", "revision", "profileId")))
        if (len(entries) > MAX_ENTRIES or not all(_entry(e) for e, _ in entries)
                or len({e["entryId"] for e, _ in entries}) != len(entries)):
            raise ReportUnavailable()
        return snapshot, entries

    def _base(self, snapshot, schema):
        return {"schema": schema, "scope": "LIBRARY_READ_ONLY", "source": self._source,
                "libraryId": self.library_id, "viewId": snapshot.view_id,
                "capturedAt": _timestamp(snapshot.captured_at)}

    @staticmethod
    def _checked(value, validator):
        if not validator(value):
            raise ReportUnavailable()
        return value

    def library_report(self, *, view=None, after=0):
        try:
            if view is None and after != 0:
                raise CursorRejected()
            snapshot, entries = self._read(view)
            paging, page = _slice(entries, after)
            result = {**self._base(snapshot, "vision.api.library.v1"), **paging, "entries": [e for e, _ in page]}
            return self._checked(result, validate_library_report)
        except CursorRejected:
            raise
        except Exception:
            raise ReportUnavailable() from None

    def _select(self, *, entry_id, view):
        if not _hex(entry_id, 32) or not _hex(view, 64):
            raise CursorRejected()
        snapshot, entries = self._read(view)
        for entry, detail in entries:
            if entry["entryId"] == entry_id:
                return snapshot, entry, detail
        raise CursorRejected()

    def entry_report(self, *, entry_id, view):
        try:
            snapshot, entry, detail = self._select(entry_id=entry_id, view=view)
            result = {**self._base(snapshot, "vision.api.library-entry.v1"), "entry": entry, "catalog": None, "profile": None}
            if entry["kind"] == "CATALOG_RECORD":
                result["catalog"] = {"connectors": [{"id": c.connector_id, "color": c.color} for c in detail.connectors],
                                     "fieldNoteCount": detail.field_note_count, "fieldNotesVerified": detail.field_notes_verified,
                                     "envelopePresent": detail.envelope_present}
            else:
                result["profile"] = {
                    "sections": [{"name": s.name, "rowCount": s.row_count, "status": s.status} for s in detail.sections],
                    "physicalStates": [{"id": s.state_id, "displayName": s.display_name, "declaredVerified": s.declared_verified} for s in detail.physical_states],
                    "workflows": [{"id": w.recipe_id, "stateId": w.state_id, "scope": w.scope} for w in detail.workflows],
                    "historyCount": len(detail.history),
                }
            return self._checked(result, validate_library_entry_report)
        except CursorRejected:
            raise
        except Exception:
            raise ReportUnavailable() from None

    def history_report(self, *, entry_id, view, after=0):
        try:
            snapshot, entry, detail = self._select(entry_id=entry_id, view=view)
            if entry["kind"] != "REFERENCE_DRAFT":
                raise CursorRejected()
            paging, page = _slice(detail.history, after)
            result = {**self._base(snapshot, "vision.api.library-history.v1"), **paging,
                      "entryId": entry_id, "profileId": entry["profileId"], "revision": entry["revision"], "etag": entry["etag"],
                      "items": [{"snapshotId": h.snapshot_id, "etag": h.etag, "revision": h.revision} for h in page]}
            return self._checked(result, validate_library_history_report)
        except CursorRejected:
            raise
        except Exception:
            raise ReportUnavailable() from None


class LibraryReadService:
    def __init__(self, *, provider=None, authorizer: LibraryAuthorizer | None = None):
        if provider is not None and not isinstance(provider, LibraryReportProvider):
            raise ValueError("invalid provider")
        if authorizer is not None and not callable(authorizer):
            raise ValueError("invalid authorizer")
        self._provider, self._authorizer = provider, authorizer

    def _authorize(self, credentials):
        try:
            grant = self._authorizer(credentials) if self._authorizer is not None else None
        except Exception:
            raise AccessDenied() from None
        if type(grant) is not LibraryReadGrant or "library:read" not in grant.scopes:
            raise AccessDenied()
        if self._provider is None:
            raise ReportUnavailable()
        if grant.library_id != self._provider.library_id:
            raise AccessDenied()
        return self._provider

    def library_report(self, credentials: Credentials, **query):
        return self._authorize(credentials).library_report(**query)

    def entry_report(self, credentials: Credentials, **query):
        return self._authorize(credentials).entry_report(**query)

    def history_report(self, credentials: Credentials, **query):
        return self._authorize(credentials).history_report(**query)
