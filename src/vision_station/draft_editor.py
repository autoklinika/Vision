"""Bounded unsigned-draft editor. Core owns all persistence and validation."""
import json
import re

from vision_api.access import ReportUnavailable
from vision_modules.ecu_reference import load_json, canonical_json
from vision_modules.ecu_reference.models import thaw
from vision_modules.ecu_library_backend.read_model import (
    _profile_detail, _display_name, LibraryReadUnavailable)
from vision_modules.ecu_library_backend.storage import (
    DraftReadSnapshot, _ReadBudget, MAX_READ_PROFILES, identifier)
from vision_modules.ecu_library_backend.service import SCOPES

DOCUMENT_LIMIT = 64 * 1024
EDITOR_WIRE_LIMIT = 128 * 1024
ETAG = re.compile(r'"[0-9a-f]{64}"')
INSTANCE = re.compile(r'[0-9a-f]{32}')
DRAFT_SCHEMA = "vision.api.ecu-draft.v1"
VALIDATION_SCHEMA = "vision.api.ecu-draft-validation.v1"
FIELDS = {
    "open": {"instanceId", "key"},
    "create": {"instanceId", "family", "variant", "catalogRevision", "key", "revision", "displayName"},
    "save": {"instanceId", "key", "etag", "document"},
    "clone": {"instanceId", "key", "etag", "newKey", "newRevision"},
    "validate": {"instanceId", "key", "document", "stateId", "recipeId", "scope"},
}


class DraftConflict(Exception):
    """A stale edit, incompatible station state, or duplicate revision."""


class DraftRequestInvalid(ValueError):
    """A closed BAD_REQUEST reported by the Core owner."""


class DraftNotFound(Exception):
    """No requested draft or catalog record."""


def _match(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _label(value):
    try:
        return _display_name(value)
    except LibraryReadUnavailable:
        raise ValueError("invalid display name") from None


def _profile(document, key):
    if type(document) is not dict:
        raise ValueError("document object required")
    try:
        raw = json.dumps(document, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("ascii")
        if len(raw) > DOCUMENT_LIMIT:
            raise ValueError("editor document exceeds 64 KiB")
        profile = load_json(raw)
        metadata = profile.data["metadata"]
        provenance = profile.data["provenance_release"]
        if (metadata["profile_id"] != key or metadata["status"] != "DRAFT"
                or metadata["template_only"] or metadata["content_sha256"] is not None
                or metadata["approval_scopes"] or provenance["release_approval"] is not None
                or provenance["released_snapshot_sha256"] is not None):
            raise ValueError("only unsigned drafts with matching identity are editable")
        # Do not publish a draft that the already deployed library projection
        # cannot represent (its IDs, names and row limits are stricter).
        _profile_detail(DraftReadSnapshot(key, profile, '"' + '0'*64 + '"', ()))
        return profile
    except LibraryReadUnavailable:
        raise ValueError("document exceeds library projection constraints") from None
    except (TypeError, OverflowError, RecursionError, UnicodeError):
        raise ValueError("invalid document") from None


def _check_args(action, args):
    if not isinstance(action, str) or action not in FIELDS or type(args) is not dict or set(args) != FIELDS[action]:
        raise ValueError("invalid editor request")
    if not _match(INSTANCE, args["instanceId"]):
        raise ValueError("invalid instance")
    for name in set(args) - {"instanceId", "etag", "document", "displayName", "scope"}:
        identifier(args[name])
    if "etag" in args and not _match(ETAG, args["etag"]):
        raise ValueError("invalid etag")
    if "displayName" in args:
        _label(args["displayName"])
    if action == "validate" and args["scope"] not in SCOPES:
        raise ValueError("invalid scope")


def _bounded_store(store, additional=0, create=False):
    """Check complete committed history under the same exclusive owner lock.

    Leave room for the next snapshot/pointer so an accepted GUI mutation
    cannot exceed the existing read model's aggregate byte/revision budget.
    """
    budget = _ReadBudget()
    keys = store._read_keys()
    if create and len(keys) >= MAX_READ_PROFILES:
        raise DraftConflict()
    for key in keys:
        store._chain(key, budget=budget)
    if additional and (budget.revisions_left < 1 or budget.bytes_left < additional + 2048):
        raise DraftConflict()


def _draft_report(value, instance):
    _profile(value["profile"], value["key"])
    return {"schema": DRAFT_SCHEMA, "source": "STATION", "instanceId": instance,
            "key": value["key"], "etag": value["etag"], "document": value["profile"]}


def _messages(values):
    # Only bounded validation diagnostics, never I/O exception details.
    return [str(x)[:256] for x in values[:64]]


class DraftEditor:
    def __init__(self, host):
        self.host = host

    def dispatch(self, action, args):
        _check_args(action, args)
        instance = self.host.station_report()["instanceId"]
        if instance != args["instanceId"]:
            raise DraftConflict()
        lib = self.host.library
        key = args["key"]
        if action == "validate":
            try:
                _profile(args["document"], key)
            except ValueError as exc:
                result = {"valid": False, "status": "INVALID_DOCUMENT",
                          "errors": [str(exc)[:256]], "blockers": []}
            else:
                # No caller-controlled capabilities, calibration or verified
                # asset evidence. Diagnostic only, never a release approval.
                r = lib.validate_profile(args["document"], args["stateId"], args["recipeId"], args["scope"])
                result = {"valid": r["valid"], "status": "NOT_READY" if r["valid"] else "INVALID_DOCUMENT",
                          "errors": _messages(r["errors"]), "blockers": _messages(r["blockers"])}
            return {"schema": VALIDATION_SCHEMA, "source": "STATION", "instanceId": instance,
                    "key": key, **result}
        if action == "open":
            try:
                # The existing bounded read snapshot verifies the full chain.
                row = next((r for r in lib.store.read_snapshot() if r.key == key), None)
                if row is None:
                    raise DraftNotFound()
                return _draft_report({"key":key,"profile":thaw(row.profile.data),"etag":row.etag},instance)
            except LibraryReadUnavailable:
                raise ReportUnavailable() from None
        if (self.host.station_report()["state"] != "NO_ACTIVE_SESSION"
                or self.host._inspection._poisoned or self.host._inspection._marker_exists()):
            raise DraftConflict()
        try:
            # The host lifecycle lock serializes this operation against start.
            # The store transaction also protects its ETag/history across owners.
            with lib.store.transaction():
                if action == "create":
                    _bounded_store(lib.store, additional=DOCUMENT_LIMIT, create=True)
                    value = lib.create_draft(args["family"],args["variant"],args["catalogRevision"],
                                             key,args["revision"],args["displayName"])
                else:
                    _bounded_store(lib.store)
                    old = lib.get_draft(key)
                    if old["etag"] != args["etag"]:
                        raise DraftConflict()
                    if action == "save":
                        candidate = _profile(args["document"],key)
                        _bounded_store(lib.store, additional=len(canonical_json(candidate)))
                        value = lib.update_draft(key,args["document"],args["etag"])
                    else:
                        candidate = thaw(_profile(old["profile"],key).data)
                        candidate["metadata"].update(profile_id=args["newKey"], profile_revision=args["newRevision"])
                        checked = _profile(candidate,args["newKey"])
                        _bounded_store(lib.store, additional=len(canonical_json(checked)), create=True)
                        value = lib.clone_draft(key,args["newKey"],args["newRevision"])
                return _draft_report(value,instance)
        except FileExistsError:
            raise DraftConflict() from None
        except FileNotFoundError:
            raise DraftNotFound() from None
        except LibraryReadUnavailable:
            raise ReportUnavailable() from None


def validate_draft_report(value):
    try:
        if (type(value) is not dict or set(value) != {"schema","source","instanceId","key","etag","document"}
                or value["schema"] != DRAFT_SCHEMA or value["source"] != "STATION"
                or not _match(INSTANCE,value["instanceId"]) or not _match(ETAG,value["etag"])):
            return False
        identifier(value["key"])
        _profile(value["document"],value["key"])
        return True
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def validate_diagnostic_report(value):
    try:
        if (type(value) is not dict or set(value) != {"schema","source","instanceId","key","valid","status","errors","blockers"}
                or value["schema"] != VALIDATION_SCHEMA or value["source"] != "STATION"
                or not _match(INSTANCE,value["instanceId"]) or type(value["valid"]) is not bool
                or value["status"] != ("NOT_READY" if value["valid"] else "INVALID_DOCUMENT")):
            return False
        identifier(value["key"])
        for k in ("errors","blockers"):
            if type(value[k]) is not list or len(value[k])>64 or any(not isinstance(x,str) or len(x)>256 for x in value[k]):
                return False
        return True
    except (ValueError, TypeError, KeyError):
        return False
