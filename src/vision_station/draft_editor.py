"""Bounded unsigned-draft editor. Core owns all persistence and validation."""
import base64
import binascii
import hashlib
import json
import re
import os
import stat

from vision_api.access import ReportUnavailable
from vision_modules.ecu_reference import load_json, canonical_json
from vision_modules.ecu_reference.models import thaw
from vision_modules.ecu_reference.validation import _id as reference_identifier
from vision_modules.ecu_library_backend.read_model import (
    _profile_detail, _display_name, LibraryReadUnavailable)
from vision_modules.ecu_library_backend.storage import (
    DraftReadSnapshot, _ReadBudget, MAX_READ_PROFILES, LIFECYCLES, identifier, _image_dimensions, image_type)
from vision_modules.ecu_library_backend.service import SCOPES

DOCUMENT_LIMIT = 64 * 1024
EDITOR_LOCK_TIMEOUT = 0.25
EDITOR_WIRE_LIMIT = 128 * 1024
ASSET_LIMIT = 2 * 1024 * 1024
ASSET_WIRE_LIMIT = 3 * 1024 * 1024
ASSET_PIXELS = 8_000_000
ASSET_COUNT = 256
ASSET_STORAGE_LIMIT = 256 * 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")
ASSET_SCHEMA = "vision.api.ecu-draft-asset.v1"
ETAG = re.compile(r'"[0-9a-f]{64}"')
INSTANCE = re.compile(r'[0-9a-f]{32}')
DRAFT_SCHEMA = "vision.api.ecu-draft.v1"
VALIDATION_SCHEMA = "vision.api.ecu-draft-validation.v1"
FIELDS = {
    "open": {"instanceId", "key"},
    "open_generation": {"instanceId","key","etag","snapshotId"},
    "archive": {"instanceId","key","etag"},
    "restore": {"instanceId","key","etag"},
    "submit_review": {"instanceId","key","etag"},
    "withdraw_review": {"instanceId","key","etag"},
    "publish_review": {"instanceId","key","etag","document","reviewProof"},
    "create": {"instanceId", "family", "variant", "catalogRevision", "key", "revision", "displayName"},
    "create_empty": {"instanceId", "family", "variant", "key", "revision", "displayName"},
    "save": {"instanceId", "key", "etag", "document"},
    "clone": {"instanceId", "key", "etag", "newKey", "newRevision"},
    "validate": {"instanceId", "key", "document", "stateId", "recipeId", "scope"},
    "validate_structure": {"instanceId", "key", "document"},
    "asset_import": {"instanceId", "key", "etag", "data"},
    "asset_preview": {"instanceId", "key", "etag", "assetId"},
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
                or provenance["released_snapshot_sha256"] is not None
                or any(row["approved"] for row in profile.data["validation_policies"]["readiness_by_scope_and_physical_state"])):
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
    for name in set(args) - {"instanceId", "etag", "document", "displayName", "scope", "data", "assetId", "snapshotId", "reviewProof"}:
        identifier(args[name])
    if "snapshotId" in args and not _match(INSTANCE,args["snapshotId"]):
        raise ValueError("invalid snapshot ID")
    if "assetId" in args:
        # An in-document reference ID, never a store filename or path.
        reference_identifier(args["assetId"])
    if "etag" in args and not _match(ETAG, args["etag"]):
        raise ValueError("invalid etag")
    if "displayName" in args:
        _label(args["displayName"])
    if action=="publish_review":
        proof=args["reviewProof"]
        if not isinstance(proof,str) or not 1<=len(proof)<=5464:
            raise ValueError("bounded review proof required")
        try:
            decoded=base64.b64decode(proof,validate=True)
        except (ValueError,binascii.Error):
            raise ValueError("invalid review proof") from None
        if not 1<=len(decoded)<=4096 or base64.b64encode(decoded).decode("ascii")!=proof:
            raise ValueError("invalid review proof")
    if action == "validate" and args["scope"] not in SCOPES:
        raise ValueError("invalid scope")


def _decode_image(value):
    if not isinstance(value,str) or not 1 <= len(value) <= 4*((ASSET_LIMIT+2)//3):
        raise ValueError("bounded image data required")
    try:
        data=base64.b64decode(value,validate=True)
    except (ValueError,binascii.Error,UnicodeError):
        raise ValueError("invalid image encoding") from None
    if base64.b64encode(data).decode("ascii") != value:
        raise ValueError("noncanonical image encoding")
    _image_preflight(data)
    return data


def _image_preflight(data):
    if not 1 <= len(data) <= ASSET_LIMIT:
        raise ValueError("editor image exceeds 2 MiB")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime="image/png"
    elif data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
        mime="image/jpeg"
    else:
        raise ValueError("JPEG or PNG required")
    width,height=_image_dimensions(data,mime)
    if width<=0 or height<=0 or width*height>ASSET_PIXELS or max(width,height)>8192:
        raise ValueError("editor image exceeds dimension budget")
    return mime


def _asset_capacity(store,sha,size):
    # Count the managed directory under the owner transaction. Do not prune
    # private data on behalf of an editor and do not accept arbitrary paths.
    count=0;total=0;exists=False;examined=0
    with os.scandir(store.root/"assets") as entries:
        for entry in entries:
            examined+=1
            if examined>ASSET_COUNT*2:
                raise DraftConflict()
            if not SHA256.fullmatch(entry.name):
                if entry.name.startswith(".tmp-"):
                    continue
                raise DraftConflict()
            info=entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise DraftConflict()
            count+=1;total+=info.st_size
            exists=exists or entry.name==sha
    if not exists and (count>=ASSET_COUNT or total+size>ASSET_STORAGE_LIMIT):
        raise DraftConflict()


def _asset_report(instance,key,asset,*,data=None,asset_id=None):
    report={"schema":ASSET_SCHEMA,"source":"STATION","instanceId":instance,
            "key":key,"sha256":asset["sha256"],"relativePath":asset["relative_path"],
            "bytes":asset["size"],"mime":asset["mime"],"status":"UNVERIFIED"}
    if data is not None:
        report.update(data=base64.b64encode(data).decode("ascii"),assetId=asset_id)
    return report


def validate_asset_report(value,preview=False):
    expected={"schema","source","instanceId","key","sha256","relativePath","bytes","mime","status"}
    if preview: expected|={"data","assetId"}
    try:
        if (type(value) is not dict or set(value)!=expected or value["schema"]!=ASSET_SCHEMA
                or value["source"]!="STATION" or not _match(INSTANCE,value["instanceId"])
                or not _match(SHA256,value["sha256"]) or value["relativePath"]!="assets/"+value["sha256"]
                or type(value["bytes"]) is not int or not 1<=value["bytes"]<=ASSET_LIMIT
                or value["mime"] not in ("image/png","image/jpeg") or value["status"]!="UNVERIFIED"):
            return False
        identifier(value["key"])
        if preview:
            reference_identifier(value["assetId"])
            data=_decode_image(value["data"])
            if len(data)!=value["bytes"] or hashlib.sha256(data).hexdigest()!=value["sha256"] or _image_preflight(data)!=value["mime"]:
                return False
        return True
    except (ValueError,TypeError,KeyError,OverflowError):
        return False


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
    _reserve_store_budget(budget, additional)
    return budget, len(keys)


def _reserve_store_budget(budget, additional):
    # The caller retains the same outer transaction. No writes can invalidate
    # this budget between the complete history check and its reservation.
    if additional and (budget.revisions_left < 1 or budget.bytes_left < additional + 2048):
        raise DraftConflict()


def _draft_report(value, instance):
    _profile(value["profile"], value["key"])
    report = {"schema": DRAFT_SCHEMA, "source": "STATION", "instanceId": instance,
            "key": value["key"], "etag": value["etag"], "document": value["profile"]}
    if value.get("lifecycle","ACTIVE")!="ACTIVE": report["lifecycle"]=value["lifecycle"]
    if "snapshotId" in value: report["snapshotId"]=value["snapshotId"]
    if value.get("releaseDigest"): report["releaseDigest"]=value["releaseDigest"]
    if value.get("reviewAvailable") is True: report["reviewAvailable"]=True
    return report


def _messages(values):
    # Only bounded validation diagnostics, never I/O exception details.
    return [str(x)[:256] for x in values[:64]]


class DraftEditor:
    def __init__(self, host):
        self.host = host

    def report(self,value,instance):
        return _draft_report({**value,"reviewAvailable":self.host._review_authority is not None},instance)

    def dispatch(self, action, args):
        _check_args(action, args)
        instance = self.host.station_report()["instanceId"]
        if instance != args["instanceId"]:
            raise DraftConflict()
        lib = self.host.library
        key = args["key"]
        if action in ("validate","validate_structure"):
            try:
                _profile(args["document"], key)
            except ValueError as exc:
                result = {"valid": False, "status": "INVALID_DOCUMENT",
                          "errors": [str(exc)[:256]], "blockers": []}
            else:
                if action=="validate_structure":
                    return {"schema":VALIDATION_SCHEMA,"source":"STATION","instanceId":instance,
                            "key":key,"valid":True,"status":"NOT_READY","errors":[],
                            "blockers":["Structural validation only; no approval or inspection readiness evaluated."]}
                # No caller-controlled capabilities, calibration or verified
                # asset evidence. Diagnostic only, never a release approval.
                r = lib.validate_profile(args["document"], args["stateId"], args["recipeId"], args["scope"])
                result = {"valid": r["valid"], "status": "NOT_READY" if r["valid"] else "INVALID_DOCUMENT",
                          "errors": _messages(r["errors"]), "blockers": _messages(r["blockers"])}
            return {"schema": VALIDATION_SCHEMA, "source": "STATION", "instanceId": instance,
                    "key": key, **result}
        if action=="publish_review":
            if self.host._review_authority is None:
                raise DraftConflict()
            raw=json.dumps(args["document"],ensure_ascii=True,allow_nan=False,separators=(",",":")).encode("ascii")
            if len(raw)>DOCUMENT_LIMIT:
                raise ValueError("reviewed document exceeds editor limit")
            reviewed=load_json(raw)
            if reviewed.data["metadata"]["profile_id"]!=key:
                raise ValueError("reviewed profile key mismatch")
            self.host._review_authority.publish(self.host,reviewed,args["etag"],
                                               base64.b64decode(args["reviewProof"],validate=True))
            return self.report(lib.get_draft(key),instance)
        if action=="open_generation":
            try:
                profile, etag, lifecycle, digest = lib.store.read_generation(key,args["snapshotId"],args["etag"])
                return self.report({"key":key,"profile":thaw(profile.data),"etag":etag,
                    "lifecycle":lifecycle,"snapshotId":args["snapshotId"],"releaseDigest":digest},instance)
            except FileNotFoundError:
                raise DraftNotFound() from None
            except FileExistsError:
                raise DraftConflict() from None
            except LibraryReadUnavailable:
                raise ReportUnavailable() from None
        if action in ("open","asset_preview"):
            try:
                # The existing bounded read snapshot verifies the full chain.
                row = next((r for r in lib.store.read_snapshot() if r.key == key), None)
                if row is None:
                    raise DraftNotFound()
                if action=="open":
                    return self.report({"key":key,"profile":thaw(row.profile.data),"etag":row.etag,"lifecycle":row.lifecycle,"releaseDigest":row.release_digest},instance)
                if row.etag!=args["etag"]:
                    raise DraftConflict()
                item=next((x for x in row.profile.data["reference_assets"]["assets"] if x["asset_id"]==args["assetId"]),None)
                if item is None:
                    raise DraftNotFound()
                sha=item["sha256"].lower()
                if (item["relative_path"]!="assets/"+sha or item["mime"] not in ("image/png","image/jpeg")
                        or not 1<=item["bytes"]<=ASSET_LIMIT or not SHA256.fullmatch(sha)):
                    raise ValueError("only managed bounded reference images may be previewed")
                data=lib.store._read("assets",sha,ASSET_LIMIT)
                mime=_image_preflight(data)
                if len(data)!=item["bytes"] or hashlib.sha256(data).hexdigest()!=sha or mime!=item["mime"] or image_type(data)!=mime:
                    raise ValueError("reference image integrity failure")
                return _asset_report(instance,key,{"sha256":sha,"relative_path":"assets/"+sha,
                    "size":len(data),"mime":mime},data=data,asset_id=args["assetId"])
            except FileNotFoundError:
                raise DraftNotFound() from None
            except LibraryReadUnavailable:
                raise ReportUnavailable() from None
        if (self.host.station_report()["state"] != "NO_ACTIVE_SESSION"
                or self.host._inspection._poisoned or self.host._inspection._marker_exists()):
            raise DraftConflict()
        try:
            # The host lifecycle lock serializes this operation against start.
            # The store transaction also protects its ETag/history across owners.
            with lib.store.transaction(timeout=EDITOR_LOCK_TIMEOUT):
                if action in ("create","create_empty"):
                    _bounded_store(lib.store, additional=DOCUMENT_LIMIT, create=True)
                    if action == "create":
                        value = lib.create_draft(args["family"],args["variant"],args["catalogRevision"],
                                                 key,args["revision"],args["displayName"])
                    else:
                        value = lib.create_empty_draft(args["family"],args["variant"],key,args["revision"],args["displayName"])
                else:
                    budget, profile_count = _bounded_store(lib.store)
                    old = lib.get_draft(key)
                    if old["etag"] != args["etag"]:
                        raise DraftConflict()
                    lifecycle = old.get("lifecycle","ACTIVE")
                    transitions={"archive":("ACTIVE","ARCHIVED"),"restore":("ARCHIVED","ACTIVE"),
                                 "submit_review":("ACTIVE","REVIEW_READY"),"withdraw_review":("REVIEW_READY","ACTIVE")}
                    if action in transitions:
                        before, after = transitions[action]
                        if lifecycle!=before: raise DraftConflict()
                        _reserve_store_budget(budget,len(canonical_json(_profile(old["profile"],key))))
                        etag=lib.store.transition(key,args["etag"],after)
                        return self.report({**old,"etag":etag,"lifecycle":after},instance)
                    if action!="clone" and lifecycle!="ACTIVE":
                        raise DraftConflict()
                    if action=="asset_import":
                        data=_decode_image(args["data"])
                        sha=hashlib.sha256(data).hexdigest()
                        _asset_capacity(lib.store,sha,len(data))
                        asset=lib.ingest_reference_image(data)
                        return _asset_report(instance,key,asset)
                    if action == "save":
                        candidate = _profile(args["document"],key)
                        _reserve_store_budget(budget, len(canonical_json(candidate)))
                        value = lib.update_draft(key,args["document"],args["etag"])
                    else:
                        candidate = thaw(_profile(old["profile"],key).data)
                        candidate["metadata"].update(profile_id=args["newKey"], profile_revision=args["newRevision"])
                        checked = _profile(candidate,args["newKey"])
                        if profile_count >= MAX_READ_PROFILES:
                            raise DraftConflict()
                        _reserve_store_budget(budget, len(canonical_json(checked)))
                        value = lib.clone_draft(key,args["newKey"],args["newRevision"])
                return self.report(value,instance)
        except FileExistsError:
            raise DraftConflict() from None
        except FileNotFoundError:
            raise DraftNotFound() from None
        except LibraryReadUnavailable as exc:
            if exc.reason == "LIBRARY_BUSY":
                raise DraftConflict() from None
            raise ReportUnavailable() from None


def validate_draft_report(value):
    try:
        fields={"schema","source","instanceId","key","etag","document"}
        if (type(value) is not dict or not fields <= set(value) <= fields | {"lifecycle","snapshotId","releaseDigest","reviewAvailable"}
                or value.get("lifecycle","ACTIVE") not in LIFECYCLES
                or (value.get("lifecycle")=="RELEASED")!=("releaseDigest" in value)
                or ("releaseDigest" in value and not _match(SHA256,value["releaseDigest"]))
                or ("reviewAvailable" in value and value["reviewAvailable"] is not True)
                or ("snapshotId" in value and (not _match(INSTANCE,value["snapshotId"]) or
                    value["etag"] != '"'+hashlib.sha256(value["snapshotId"].encode("ascii")).hexdigest()+'"'))
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
