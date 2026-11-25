"""Trusted, offline review composition for catalog and reference releases.

This is not an HTTP/IPC endpoint or a second operational library owner.
Use an explicitly provisioned IdentityStore, private directories and the
existing library/release stores in a commissioned backend composition.
"""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from types import MappingProxyType

from vision_api.access import AccessDenied
from vision_api.identity import IdentityStore
from vision_modules.ecu_library_backend import ECULibraryService
from vision_modules.ecu_library_backend.storage import REPO, _ReadBudget
from vision_modules.ecu_profiles import ECUCatalog, ReleaseStore, record_sha256
from vision_modules.ecu_profiles.models import (
    ECURecord, ApprovalEvidence, identifier, canonical_json as catalog_json,
    load_json as load_catalog, text as checked_text)
from vision_modules.ecu_profiles.promotion import validate_draft, to_core_ecu_profile
from vision_modules.ecu_reference import (
    AssetStore, ReferenceReleaseStore, canonical_json, content_sha256, load_json)
from vision_modules.ecu_reference.compiler import _check_review_contents
from vision_modules.ecu_reference.models import thaw

SCHEMA = "vision.ecu-review.v1"
MAX_REVIEW_BYTES = 1024 * 1024
MAX_REVIEWS = 1024
MAX_RELEASES = 256
MAX_ASSETS = 32
MAX_ASSET_TOTAL = 64 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}", re.ASCII)
ETAG = re.compile(r'"[0-9a-f]{64}"', re.ASCII)
SCOPE = "photo_inspection"


class ReviewConflict(ValueError):
    """A reviewed snapshot or released revision is stale/conflicting."""


class ReviewBlocked(ValueError):
    """A candidate does not yet satisfy the review requirements."""
    def __init__(self, blockers):
        self.blockers = tuple(blockers)
        super().__init__("; ".join(self.blockers))


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate review field")
        result[key] = value
    return result


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00","Z")


def _private(path):
    p = Path(path)
    if (not p.is_absolute() or ".." in p.parts or p == REPO or REPO in p.parents
            or any(x.is_symlink() for x in (p,*p.parents))):
        raise ValueError("absolute private data directory required")
    s = p.stat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
        raise ValueError("private owner-only data directory required")
    return p


class ReviewAuthority:
    """Explicitly configured, disjoint author/reviewer accounts.

    Tokens are checked by the existing IdentityStore. Usernames and roles are
    not accepted from an HTTP body or a draft document. The configured local
    store and account-provisioning authority remain trusted.
    """
    def __init__(self, identity, *, authors, reviewers):
        if not isinstance(identity, IdentityStore):
            raise ValueError("existing identity store required")
        self.identity = identity
        if isinstance(authors,str) or isinstance(reviewers,str):
            raise ValueError("explicit account collections required")
        self.authors = frozenset(identifier(x) for x in authors)
        self.reviewers = frozenset(identifier(x) for x in reviewers)
        if not self.authors or not self.reviewers or self.authors & self.reviewers or len(self.authors|self.reviewers)>64:
            raise ValueError("disjoint explicit author and reviewer accounts required")

    def require(self, token, permission):
        session = self.identity.session(token, touch=False)
        username = session["username"]
        allowed = {"author":self.authors,"reviewer":self.reviewers,
                   "read":self.authors|self.reviewers}.get(permission,frozenset())
        if session["role"] != "operator" or username not in allowed:
            raise AccessDenied()
        return username


class ReviewStore:
    """Exclusive immutable review envelopes, content-addressed by SHA-256."""
    def __init__(self, directory):
        self.path = _private(directory)
        self._fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self): return self
    def __exit__(self,*args): self.close()

    @staticmethod
    def _name(review_id):
        if not isinstance(review_id,str) or not HEX.fullmatch(review_id):
            raise ValueError("invalid review ID")
        return review_id+".json"

    def publish(self, envelope):
        raw = _canonical(envelope)
        if len(raw)>MAX_REVIEW_BYTES:
            raise ValueError("review envelope exceeds size limit")
        review_id = _digest(raw)
        name = self._name(review_id)
        # No automatic retention/deletion. Stop before the private journal
        # grows without an explicitly reviewed retention procedure.
        with os.scandir(self.path) as entries:
            if sum(1 for _ in entries)>=MAX_REVIEWS:
                raise ReviewBlocked(("review workspace capacity exceeded",))
        pending = ".pending-"+secrets.token_hex(16)
        fd = os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self._fd)
        try:
            with os.fdopen(fd,"wb") as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.link(pending,name,src_dir_fd=self._fd,dst_dir_fd=self._fd,follow_symlinks=False)
            os.fsync(self._fd)
        finally:
            os.unlink(pending,dir_fd=self._fd);os.fsync(self._fd)
        return review_id

    def read(self, review_id):
        name = self._name(review_id)
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self._fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                    or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>MAX_REVIEW_BYTES):
                raise ValueError("invalid review envelope")
            with os.fdopen(fd,"rb",closefd=False) as stream:
                raw=stream.read(MAX_REVIEW_BYTES+1)
        finally:
            os.close(fd)
        if len(raw)>MAX_REVIEW_BYTES or _digest(raw)!=review_id:
            raise ValueError("review envelope integrity failure")
        envelope=json.loads(raw.decode("ascii"),object_pairs_hook=_unique,
                            parse_constant=lambda _:(_ for _ in ()).throw(ValueError("invalid number")))
        if type(envelope) is not dict or _canonical(envelope)!=raw:
            raise ValueError("noncanonical review envelope")
        common={"schema","kind","author","submittedAt","environment","document"}
        kind=envelope.get("kind")
        extra={"recordSha256"} if kind=="CATALOG" else {"draftEtag","draftSha256","recordSha256",
                "reviewSha256","stateId","recipeId","scope","assets"} if kind=="REFERENCE" else None
        if extra is None or set(envelope)!=common|extra or envelope["schema"]!=SCHEMA:
            raise ValueError("invalid review envelope")
        identifier(envelope["author"])
        return envelope


def catalog_review_blockers(record, calibrations, capabilities):
    """Review diagnostics for a measured catalog candidate, not approval."""
    blockers=list(validate_draft(record))
    if record.status not in ("DRAFT","READY_FOR_REVIEW") or record.approval is not None:
        blockers.append("unsigned catalog candidate required")
    if any(calibrations.get(k)!=v for k,v in record.calibration_dependencies):
        blockers.append("matching calibration revisions required")
    if not set(record.required_capabilities)<=set(capabilities):
        blockers.append("required station capabilities missing")
    return tuple(blockers)


def _unsigned_reference(profile):
    d=profile.data;m=d["metadata"];p=d["provenance_release"]
    if (m["schema_version"]!="1" or m["status"]!="DRAFT" or m["template_only"] is not False
            or m["approval_scopes"] or m["content_sha256"] is not None
            or p["release_approval"] is not None or p["released_snapshot_sha256"] is not None
            or any(x["approved"] for x in d["validation_policies"]["readiness_by_scope_and_physical_state"])):
        raise ReviewBlocked(("unsigned DRAFT without author-supplied approval flags required",))


def _review_candidate(profile):
    _unsigned_reference(profile)
    d=thaw(profile.data);d["metadata"]["status"]="REVIEW_READY"
    return load_json(_canonical(d))


def _seal_reference(candidate, state, recipe, reviewer, approved_at, reference):
    d=thaw(candidate.data)
    m,p=d["metadata"],d["provenance_release"]
    if m["status"]!="REVIEW_READY":
        raise ValueError("review candidate required")
    selected={"state_id":state,"recipe_id":recipe,"scope":SCOPE}
    rows=d["validation_policies"]["readiness_by_scope_and_physical_state"]
    matches=[x for x in rows if all(x[k]==v for k,v in selected.items())]
    if len(matches)!=1 or any(x["approved"] for x in rows):
        raise ValueError("exact unsigned proposed scope required")
    matches[0]["approved"]=True
    m["status"]="APPROVED";m["approval_scopes"]=[selected]
    digest=content_sha256(load_json(_canonical(d)))
    m["content_sha256"]=digest
    p["released_snapshot_sha256"]=digest
    p["release_approval"]={"reviewer_id":reviewer,"approved_at":approved_at,
                           "reference":reference,"content_sha256":digest}
    return load_json(_canonical(d))


class ReferenceReviewService:
    """One trusted local author/reviewer workflow, with no hardware operations.

    Catalog approval publishes a new immutable ECURecord; reference approval
    requires that exact released record plus the existing compiler's checks.
    The original draft pointer/history is never modified by a review.
    """
    def __init__(self, library, authority, *, review_root, catalog_release_root,
                 reference_release_root, calibrations, capabilities):
        if not isinstance(library,ECULibraryService) or not isinstance(authority,ReviewAuthority):
            raise ValueError("existing library and review authority required")
        self.library,self.authority=library,authority
        self.review_root,self.catalog_root,self.reference_root=(
            _private(p) for p in (review_root,catalog_release_root,reference_release_root))
        asset_root=_private(library.store.root)
        if len({asset_root,self.review_root,self.catalog_root,self.reference_root})!=4:
            raise ValueError("separate review, release and draft namespaces required")
        self.asset_root=asset_root
        if type(calibrations) is not dict:
            raise ValueError("explicit calibration revisions required")
        self.calibrations=MappingProxyType({identifier(k):identifier(v) for k,v in calibrations.items()})
        self.capabilities=frozenset(identifier(x) for x in capabilities)

    def _environment(self):
        return {"calibrations":dict(self.calibrations),"capabilities":sorted(self.capabilities)}

    def _envelope(self, kind, author, document, **extra):
        return {"schema":SCHEMA,"kind":kind,"author":author,"submittedAt":_now(),
                "environment":self._environment(),"document":document,**extra}

    def _draft(self, key, expected_etag):
        identifier(key)
        if not isinstance(expected_etag,str) or not ETAG.fullmatch(expected_etag):
            raise ValueError("exact draft ETag required")
        # Bound even this trusted backend review read; use the same owner
        # transaction and the existing verified lineage.
        generation,profile=self.library.store._chain(key,budget=_ReadBudget())[0]
        etag=self.library.store.etag(generation.encode("ascii"))
        if etag!=expected_etag:
            raise ReviewConflict("draft generation changed")
        return profile

    @staticmethod
    def _exists(root, store_type, profile_id, revision):
        # Existing immutable release stores enforce the actual open/publish
        # boundary. lexists includes a dangling symlink, which is a conflict.
        return os.path.lexists(root/store_type._name(profile_id,revision))

    def _catalog_release_records(self):
        # A second key must not publish a duplicate family/variant/revision.
        # Read only bounded, explicitly managed immutable catalog releases.
        with ReleaseStore(self.catalog_root) as store:
            count=0
            with os.scandir(self.catalog_root) as entries:
                for entry in entries:
                    count+=1
                    if count>MAX_RELEASES*2:
                        raise ReviewBlocked(("catalog release directory limit exceeded",))
                    name=entry.name
                    if not name.endswith(".json"):
                        continue
                    stem=name[:-5]
                    length,sep,tail=stem.partition("_")
                    if not sep or not length.isascii() or not length.isdecimal() or len(length)>3:
                        raise ReviewBlocked(("invalid catalog release filename",))
                    size=int(length)
                    if not 1<=size<=64 or len(tail)<=size+1 or tail[size]!="_":
                        raise ReviewBlocked(("invalid catalog release filename",))
                    key,revision=tail[:size],tail[size+1:]
                    try:
                        if name!=ReleaseStore._name(key,revision):
                            raise ValueError("invalid release name")
                        yield store.read(key,revision)
                    except (ValueError,OSError):
                        raise ReviewBlocked(("invalid existing catalog release",)) from None

    def _check_catalog_candidate(self, record):
        blockers=list(catalog_review_blockers(record,self.calibrations,self.capabilities))
        # The built-in/loaded catalog is immutable by identity. Never try to
        # replace its DRAFT revision in place with a new approved record.
        def same_identity(other):
            return ((other.family,other.variant,other.revision)==(record.family,record.variant,record.revision)
                    or (other.profile_id,other.revision)==(record.profile_id,record.revision))
        if len(self.library.catalog._records)>MAX_RELEASES:
            raise ReviewBlocked(("catalog registry capacity exceeded",))
        if any(same_identity(x) for x in self.library.catalog.list_records()):
            blockers.append("catalog revision already registered; choose a new revision")
        releases=list(self._catalog_release_records())
        if len(releases)>=MAX_RELEASES:
            blockers.append("catalog release capacity exceeded")
        if any(same_identity(x) for x in releases) or self._exists(self.catalog_root,ReleaseStore,record.profile_id,record.revision):
            blockers.append("catalog release already exists")
        if blockers: raise ReviewBlocked(blockers)

    def _released_catalog(self, profile):
        m=profile.data["metadata"]
        with ReleaseStore(self.catalog_root) as releases:
            try:
                record=releases.read(m["profile_id"],m["profile_revision"])
            except (ValueError,OSError):
                raise ReviewBlocked(("matching approved catalog release missing or invalid",)) from None
            if (record.family,record.variant)!=(m["family_id"],m["variant_id"]):
                raise ReviewBlocked(("catalog identity mismatch",))
            try:
                existing=self.library.catalog.get(record.family,record.variant,record.revision)
            except KeyError:
                pass  # Can be reviewed before explicit commissioning.
            else:
                if existing!=record:
                    raise ReviewBlocked(("registered catalog revision conflicts with release",))
            catalog=ECUCatalog();catalog.register(record)
            to_core_ecu_profile(record,dict(self.calibrations),catalog=catalog)
        return record,catalog

    def _image(self, asset):
        # V1 uses the pre-existing validated JPEG/PNG ingest store only.
        # No caller paths, URL fetches, models or PDF parsing.
        sha=asset["sha256"].lower()
        if (asset["kind"] not in ("photo","image") or asset["relative_path"]!="assets/"+sha
                or asset["verified"] is not True or asset["privacy_class"] not in ("private","controlled")):
            raise ReviewBlocked(("asset is not a managed reviewed reference image: "+asset["asset_id"],))
        try:
            data,mime=self.library.read_reference_image(sha)
        except (OSError,ValueError):
            raise ReviewBlocked(("reference image missing, corrupt or invalid: "+asset["asset_id"],)) from None
        if len(data)!=asset["bytes"] or mime!=asset["mime"]:
            raise ReviewBlocked(("reference image size or MIME mismatch: "+asset["asset_id"],))
        return data,mime

    def _verify_assets(self, profile):
        d=profile.data;p=d["provenance_release"]
        assets=d["reference_assets"]["assets"]
        if len(assets)>MAX_ASSETS or sum(a["bytes"] for a in assets)>MAX_ASSET_TOTAL:
            raise ReviewBlocked(("reference material budget exceeded",))
        sources={s["source_id"]:s for s in p["measurement_sources"]}
        hashes={h["asset_id"]:h["sha256"].lower() for h in p["asset_hashes"]}
        if set(hashes)!={a["asset_id"] for a in assets}:
            raise ReviewBlocked(("complete asset manifest required",))
        result=[]
        for asset in sorted(assets,key=lambda a:a["asset_id"]):
            identifier(asset["asset_id"])
            if (sources[asset["source_id"]]["status"]!="VERIFIED"
                    or hashes[asset["asset_id"]]!=asset["sha256"].lower()):
                raise ReviewBlocked(("asset provenance or manifest mismatch: "+asset["asset_id"],))
            data,mime=self._image(asset)
            result.append({"assetId":asset["asset_id"],"sha256":_digest(data),"bytes":len(data),"mime":mime})
        return result

    def _check_reference(self, candidate,state,recipe):
        identifier(state);identifier(recipe)
        m=candidate.data["metadata"]
        if self._exists(self.reference_root,ReferenceReleaseStore,m["profile_id"],m["profile_revision"]):
            raise ReviewConflict("reference release already exists")
        record,catalog=self._released_catalog(candidate)
        assets=self._verify_assets(candidate)
        try:
            with ReleaseStore(self.catalog_root) as releases, AssetStore(self.asset_root) as store:
                _check_review_contents(candidate,state,recipe,record,catalog,releases,
                                       dict(self.calibrations),capabilities=self.capabilities,asset_store=store)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            raise ReviewBlocked(("reference content is not review-ready: "+str(exc)[:512],)) from None
        return record,assets

    def ingest_image(self, token, data):
        self.authority.require(token,"author")
        # Existing store returns UNVERIFIED. Ingestion cannot approve evidence.
        return self.library.ingest_reference_image(data)

    def submit_catalog(self, token, record):
        author=self.authority.require(token,"author")
        if not isinstance(record,ECURecord):
            raise ValueError("typed catalog candidate required")
        candidate=load_catalog(catalog_json(record))
        with self.library.store.transaction():
            self._check_catalog_candidate(candidate)
            candidate=replace(candidate,status="READY_FOR_REVIEW")
            envelope=self._envelope("CATALOG",author,json.loads(catalog_json(candidate)),
                                    recordSha256=record_sha256(candidate))
            if self.authority.require(token,"author")!=author:
                raise AccessDenied()
            with ReviewStore(self.review_root) as store:
                review_id=store.publish(envelope)
        return {"reviewId":review_id,"status":"REVIEW_READY"}

    def submit_reference(self, token, key, etag, state, recipe):
        author=self.authority.require(token,"author")
        with self.library.store.transaction():
            draft=self._draft(key,etag)
            candidate=_review_candidate(draft)
            record,assets=self._check_reference(candidate,state,recipe)
            envelope=self._envelope("REFERENCE",author,thaw(candidate.data),
                draftEtag=etag,draftSha256=_digest(canonical_json(draft).encode("ascii")),
                recordSha256=record_sha256(record),reviewSha256=content_sha256(candidate),
                stateId=state,recipeId=recipe,scope=SCOPE,assets=assets)
            if self.authority.require(token,"author")!=author:
                raise AccessDenied()
            with ReviewStore(self.review_root) as store:
                review_id=store.publish(envelope)
        return {"reviewId":review_id,"status":"REVIEW_READY"}

    def inspect(self, token, review_id):
        self.authority.require(token,"read")
        with self.library.store.transaction(), ReviewStore(self.review_root) as store:
            envelope=store.read(review_id)
            status=self._status(review_id,envelope)
        return {"reviewId":review_id,"status":status,"review":envelope}

    def _status(self, review_id,envelope):
        if envelope["kind"]=="CATALOG":
            candidate=load_catalog(_canonical(envelope["document"]))
            if not self._exists(self.catalog_root,ReleaseStore,candidate.profile_id,candidate.revision):
                return "REVIEW_READY" if envelope["environment"]==self._environment() else "STALE"
            with ReleaseStore(self.catalog_root) as store:
                released=store.read(candidate.profile_id,candidate.revision)
            approval=released.approval
            if (record_sha256(released)!=envelope["recordSha256"] or not approval
                    or not approval.reference.startswith("review:"+review_id+" ")
                    or approval.reviewer_id==envelope["author"]):
                raise ReviewConflict("catalog revision released by a different review")
            return "APPROVED"
        candidate=load_json(_canonical(envelope["document"]));m=candidate.data["metadata"]
        if not self._exists(self.reference_root,ReferenceReleaseStore,m["profile_id"],m["profile_revision"]):
            if envelope["environment"]!=self._environment():
                return "STALE"
            try:
                draft=self._draft(m["profile_id"],envelope["draftEtag"])
                if _digest(canonical_json(draft).encode("ascii"))!=envelope["draftSha256"]:
                    return "STALE"
            except (ReviewConflict,FileNotFoundError):
                return "STALE"
            return "REVIEW_READY"
        with ReferenceReleaseStore(self.reference_root) as store:
            released=store.read(m["profile_id"],m["profile_revision"])
        a=released.data["provenance_release"]["release_approval"]
        expected=_seal_reference(candidate,envelope["stateId"],envelope["recipeId"],
                                 a["reviewer_id"],a["approved_at"],a["reference"])
        if (released!=expected or not a["reference"].startswith("review:"+review_id+" ")
                or a["reviewer_id"]==envelope["author"]):
            raise ReviewConflict("reference revision released by a different review")
        return "APPROVED"

    def read_review_image(self,token,review_id,asset_id):
        self.authority.require(token,"read")
        identifier(asset_id)
        with ReviewStore(self.review_root) as store:
            envelope=store.read(review_id)
        if envelope["kind"]!="REFERENCE":
            raise ValueError("reference review required")
        candidate=load_json(_canonical(envelope["document"]))
        asset=next((a for a in candidate.data["reference_assets"]["assets"] if a["asset_id"]==asset_id),None)
        if asset is None:
            raise ValueError("asset not in review")
        data,mime=self._image(asset)
        if {"assetId":asset_id,"sha256":_digest(data),"bytes":len(data),"mime":mime} not in envelope["assets"]:
            raise ReviewConflict("reviewed image changed")
        return data,mime

    def approve(self, token, review_id, decision_reference):
        reviewer=self.authority.require(token,"reviewer")
        checked_text(decision_reference)
        if len(decision_reference)>512 or any(ord(c)<32 for c in decision_reference):
            raise ValueError("bounded human review evidence reference required")
        reference="review:"+review_id+" "+decision_reference
        with self.library.store.transaction(), ReviewStore(self.review_root) as reviews:
            envelope=reviews.read(review_id)
            if reviewer==envelope["author"]:
                raise AccessDenied()
            if envelope["environment"]!=self._environment():
                raise ReviewConflict("review environment changed")
            if self._status(review_id,envelope)!="REVIEW_READY":
                raise ReviewConflict("review is stale or already approved; inspect its status")
            if envelope["kind"]=="CATALOG":
                candidate=load_catalog(_canonical(envelope["document"]))
                if candidate.status!="READY_FOR_REVIEW" or record_sha256(candidate)!=envelope["recordSha256"]:
                    raise ReviewConflict("catalog candidate changed")
                self._check_catalog_candidate(candidate)
                approval=ApprovalEvidence(candidate.profile_id,candidate.revision,
                            envelope["recordSha256"],reviewer,_now(),reference)
                released=replace(candidate,status="APPROVED",approval=approval)
                catalog=ECUCatalog();catalog.register(released)
                if self.authority.require(token,"reviewer")!=reviewer:
                    raise AccessDenied()
                with ReleaseStore(self.catalog_root) as store:
                    digest=store.publish(released,dict(self.calibrations),catalog=catalog)
            else:
                candidate=load_json(_canonical(envelope["document"]))
                key=candidate.data["metadata"]["profile_id"]
                draft=self._draft(key,envelope["draftEtag"])
                if (_digest(canonical_json(draft).encode("ascii"))!=envelope["draftSha256"]
                        or _review_candidate(draft)!=candidate
                        or content_sha256(candidate)!=envelope["reviewSha256"] or envelope["scope"]!=SCOPE):
                    raise ReviewConflict("draft content changed after submission")
                record,assets=self._check_reference(candidate,envelope["stateId"],envelope["recipeId"])
                if record_sha256(record)!=envelope["recordSha256"] or assets!=envelope["assets"]:
                    raise ReviewConflict("review evidence changed")
                released=_seal_reference(candidate,envelope["stateId"],envelope["recipeId"],
                                         reviewer,_now(),reference)
                if self.authority.require(token,"reviewer")!=reviewer:
                    raise AccessDenied()
                with ReferenceReleaseStore(self.reference_root) as store:
                    digest=store.publish(released)
            return {"reviewId":review_id,"status":"APPROVED","releaseSha256":digest}
