"""Trusted offline reference release boundary.

HTTP/IPC publication requires an explicitly configured review authority.
The station owner must supply a
separate authenticated review verifier, already approved matching ECU record,
private stores, calibrated capabilities and staging directory. Diagnostic
readiness never grants approval. This module cannot start an inspection.
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import os
import tempfile
import subprocess

from vision_modules.ecu_reference import (
    ReferenceReleaseStore, ReferenceLibrary, canonical_json, compile_profile,
    content_sha256, load_json,
)
from vision_modules.ecu_reference.models import ReferenceProfile, thaw
from vision_modules.ecu_profiles import record_sha256
from vision_modules.ecu_library_backend.storage import _check_path
from .draft_editor import _bounded_store, _reserve_store_budget, _profile
from types import MappingProxyType
from .inspection import Selection


@dataclass(frozen=True)
class ReviewIntent:
    profile_id: str
    submitted_etag: str
    draft_digest: str
    release_digest: str
    catalog_digest: str
    reviewer_id: str
    approval_reference: str
    approved_at: str
    scopes: tuple


def unsigned_content(reviewed):
    """Strip ONLY independent endorsement fields, not measurement evidence."""
    document = thaw(reviewed.data)
    document["metadata"].update(status="DRAFT", approval_scopes=[], content_sha256=None)
    document["provenance_release"].update(release_approval=None,released_snapshot_sha256=None)
    for row in document["validation_policies"]["readiness_by_scope_and_physical_state"]:
        row["approved"] = False
    return _profile(document, document["metadata"]["profile_id"])


def _approved_scopes(profile):
    document = profile.data
    def key(row):
        return row["state_id"],row["recipe_id"],row["scope"]
    scopes = tuple(sorted(key(x) for x in document["metadata"]["approval_scopes"]))
    approved = tuple(sorted(key(x) for x in document["validation_policies"]["readiness_by_scope_and_physical_state"] if x["approved"]))
    # The installed Runtime compiles photo inspection only. Do not advertise
    # unsupported thermal/other execution scopes as approved by this workflow.
    if not scopes or len(scopes)>16 or scopes != approved or len(set(scopes))!=len(scopes) or any(s[2]!="photo_inspection" for s in scopes):
        raise ValueError("exact supported review scopes required")
    return scopes


def _choice(profile,state,recipe):
    m=profile.data["metadata"]
    identity=(m["family_id"],m["variant_id"],m["profile_revision"],state,recipe)
    digest=hashlib.sha256(json.dumps(identity,separators=(",",":")).encode("ascii")).hexdigest()
    return Selection("ref-"+digest[:48],*identity)


def _compile(profile, library, reference_store, release_store, asset_store, calibrations, capabilities):
    m=profile.data["metadata"]
    record=library.catalog.get(m["family_id"],m["variant_id"],m["profile_revision"])
    choices=[]
    for state,recipe,_scope in _approved_scopes(profile):
        compile_profile(profile,state,recipe,record,library.catalog,release_store,
            dict(calibrations), capabilities=capabilities, asset_store=asset_store,
            reference_release_store=reference_store)
        choices.append(_choice(profile,state,recipe))
    return tuple(choices)


def publish_reviewed_reference(host, reviewed, expected_etag, *, authenticate_review,
        reference_store, release_store, reference_library, asset_store,
        calibrations, capabilities, staging_root):
    """Publish an independently reviewed exact saved generation, then mark it.

    This is a trusted publication boundary, not a browser approval operation.
    A verifier authenticates the full immutable intent (including both
    digests and submitted ETag); it must enforce reviewer independence and
    provenance in the deployment's own trust system. Hashes alone are not
    authorization. If a crash occurs after immutable publication but before
    the local marker, explicit re-execution against the same submitted ETag
    accepts only the exact existing release, never overwrites it.
    """
    if not isinstance(reviewed,ReferenceProfile) or not callable(authenticate_review):
        raise ValueError("explicit approved reference and review authority required")
    if not isinstance(reference_store,ReferenceReleaseStore) or not isinstance(reference_library,ReferenceLibrary):
        raise ValueError("trusted release stores required")
    root=_check_path(staging_root)
    if not root.is_dir() or root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o077:
        raise ValueError("private staging directory required")
    if not host._lifecycle_lock.acquire(timeout=.25):
        raise ValueError("station busy")
    try:
        if (host.station_report()["state"]!="NO_ACTIVE_SESSION" or
                host._inspection._poisoned or host._inspection._marker_exists()):
            raise ValueError("station must be idle")
        library=host.library
        m=reviewed.data["metadata"]
        key=m["profile_id"]
        with library.store.transaction(timeout=.25):
            budget,_=_bounded_store(library.store)
            saved=library.get_draft(key)
            if saved["etag"]!=expected_etag or saved.get("lifecycle")!="REVIEW_READY":
                raise ValueError("exact submitted review generation required")
            draft=_profile(saved["profile"],key)
            if canonical_json(unsigned_content(reviewed))!=canonical_json(draft):
                raise ValueError("reviewed release differs from submitted measurements")
            digest=ReferenceReleaseStore._validate(reviewed)
            scopes=_approved_scopes(reviewed)
            record=library.catalog.get(m["family_id"],m["variant_id"],m["profile_revision"])
            release_store.require(record)
            approval=reviewed.data["provenance_release"]["release_approval"]
            intent=ReviewIntent(key,expected_etag,content_sha256(draft),digest,record_sha256(record),
                                approval["reviewer_id"],approval["reference"],approval["approved_at"],scopes)
            if authenticate_review(intent) is not True:
                raise ValueError("review authorization not established")
            # Check all references and every executable scope in a private
            # temporary release store, before irreversible publication.
            with tempfile.TemporaryDirectory(prefix="reference-review-",dir=root) as staged:
                with ReferenceReleaseStore(staged) as candidate_store:
                    candidate_store.publish(reviewed)
                    choices=_compile(reviewed,library,candidate_store,release_store,asset_store,calibrations,capabilities)
            for existing in reference_library.list_profiles():
                old=existing.data["metadata"]
                if (old["family_id"],old["variant_id"],old["profile_revision"])==(m["family_id"],m["variant_id"],m["profile_revision"]) and canonical_json(existing)!=canonical_json(reviewed):
                    raise ValueError("reference revision already registered")
            _reserve_store_budget(budget,len(canonical_json(draft)))
            try:
                reference_store.publish(reviewed)
            except FileExistsError:
                reference_store.require(reviewed)
            reference_store.require(reviewed)
            library.store.transition(key,expected_etag,"RELEASED",release_digest=digest)
            reference_library.register(reviewed)
        composition=host._inspection.composition
        if composition is not None and getattr(composition,"managed_releases",False) and (
                composition.reference_library is reference_library and composition.reference_release_store is reference_store
                and composition.release_store is release_store and composition.asset_store is asset_store):
            # Configuration opted in. Refresh the exact approved choices only
            # after the private transaction committed; never select/start one.
            composition.refresh_released_selections(library)
        return choices
    finally:
        host._lifecycle_lock.release()


def review_intent_bytes(intent):
    """Canonical bytes for a deployment-provided independent signature verifier."""
    if not isinstance(intent,ReviewIntent):
        raise ValueError("typed review intent required")
    return b"vision-reference-review-v1\0"+json.dumps(asdict(intent),sort_keys=True,ensure_ascii=True,
        separators=(",",":"),allow_nan=False).encode("ascii")


class Ed25519ReviewVerifier:
    """Optional local verifier using explicitly enrolled reviewer public keys.

    Keys are raw 32-byte Ed25519 public keys supplied by trusted configuration.
    Private signing keys never belong on Core. This authenticates endorsement,
    not physical measurements; reviewer enrollment and independent review are
    owner responsibilities. No key is accepted from the browser/package.
    """
    def __init__(self, reviewers, staging_root):
        self.root=_check_path(staging_root)
        if not self.root.is_dir() or self.root.stat().st_uid!=os.getuid() or self.root.stat().st_mode & 0o077:
            raise ValueError("private verifier staging required")
        keys=dict(reviewers)
        if not 1<=len(keys)<=32 or any(not isinstance(name,str) or not name or len(name)>128
                or not isinstance(key,bytes) or len(key)!=32 for name,key in keys.items()):
            raise ValueError("explicit enrolled reviewer public keys required")
        self.keys=MappingProxyType(keys)

    def __call__(self,intent,proof):
        if not isinstance(intent,ReviewIntent) or not isinstance(proof,bytes) or len(proof)!=64:
            return False
        key=self.keys.get(intent.reviewer_id)
        if key is None:
            return False
        try:
            with tempfile.TemporaryDirectory(prefix="review-proof-",dir=self.root) as directory:
                root=_check_path(directory)
                # RFC 8410 Ed25519 SubjectPublicKeyInfo DER prefix.
                (root/"key.der").write_bytes(bytes.fromhex("302a300506032b6570032100")+key)
                (root/"intent").write_bytes(review_intent_bytes(intent))
                (root/"signature").write_bytes(proof)
                result=subprocess.run(["/usr/bin/openssl","pkeyutl","-verify","-pubin","-keyform","DER",
                    "-inkey",str(root/"key.der"),"-rawin","-in",str(root/"intent"),"-sigfile",str(root/"signature")],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2,check=False)
                return result.returncode==0
        except (OSError,ValueError,subprocess.SubprocessError):
            return False


@dataclass(frozen=True)
class ReviewAuthority:
    """Configured by the trusted local owner, never by request data.

    verifier(intent, proof_bytes) must authenticate the independent reviewer
    and their actual evidence. A raw digest or browser role is insufficient.
    """
    verifier: object
    reference_store: object
    release_store: object
    reference_library: object
    asset_store: object
    calibrations: object
    capabilities: object
    staging_root: object

    def __post_init__(self):
        if not callable(self.verifier) or not isinstance(self.reference_store,ReferenceReleaseStore) or not isinstance(self.reference_library,ReferenceLibrary):
            raise ValueError("explicit review authority and stores required")
        object.__setattr__(self,"calibrations",MappingProxyType(dict(self.calibrations)))
        object.__setattr__(self,"capabilities",frozenset(self.capabilities))

    def publish(self,host,reviewed,etag,proof):
        if not isinstance(proof,bytes) or not 1<=len(proof)<=4096:
            raise ValueError("bounded independent review proof required")
        return publish_reviewed_reference(host,reviewed,etag,authenticate_review=lambda intent:self.verifier(intent,proof),
            reference_store=self.reference_store,release_store=self.release_store,reference_library=self.reference_library,
            asset_store=self.asset_store,calibrations=self.calibrations,capabilities=self.capabilities,staging_root=self.staging_root)


def load_managed_releases(library, reference_library, reference_store):
    """Reconstruct managed release registrations from committed private history.

    A release published before its lifecycle commit is NOT selectable by this
    managed path. Legacy externally configured registrations remain separate.
    """
    snapshot=library.store.read_snapshot()
    by_key={row.key:row for row in snapshot}
    for row in snapshot:
        if row.lifecycle!="RELEASED":
            continue
        revision=row.profile.data["metadata"]["profile_revision"]
        try:
            released=reference_store.read(row.key,revision)
            if content_sha256(released)!=row.release_digest or canonical_json(unsigned_content(released))!=canonical_json(row.profile):
                continue
            reference_library.register(released)
        except (ValueError,OSError,KeyError):
            continue
    return by_key


def approved_selections(library, *, reference_library, reference_store, release_store,
                        asset_store, calibrations, capabilities):
    """Prepare only exact, compiled approved selections for a trusted composition.

    Registration in ReferenceLibrary alone never establishes readiness.
    Invalid, missing or changed releases are omitted. No recipe is selected
    automatically, and the normal Runtime.resolve/start gates run again.
    """
    if not isinstance(reference_library,ReferenceLibrary):
        raise ValueError("explicit reference library required")
    managed=load_managed_releases(library,reference_library,reference_store)
    result=[]
    for profile in reference_library.list_profiles():
        row=managed.get(profile.data["metadata"]["profile_id"])
        if row is not None and (row.lifecycle!="RELEASED" or row.release_digest!=content_sha256(profile)):
            continue
        try:
            result.extend(_compile(profile,library,reference_store,release_store,asset_store,calibrations,capabilities))
        except (OSError,ValueError,KeyError):
            continue
    if len(result)>16:
        raise ValueError("explicit selection limit exceeded")
    return tuple(result)
