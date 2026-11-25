"""Offline private review workspace CLI (not a live station process).

Use separately staged data. The explicit configuration has no default
author/reviewer, calibration or capabilities. Never point it at live Core
storage. Local file ownership and the account provisioning authority are the
trust boundary; no HTTP or hardware access is provided.
"""
import argparse
from dataclasses import replace
import getpass
import json
import os
from pathlib import Path
import stat
import sys
from contextlib import contextmanager

from vision_api.access import AccessDenied
from vision_api.identity import IdentityStore
from vision_modules.ecu_library_backend import ECULibraryService
from vision_modules.ecu_profiles import load_json as load_catalog, canonical_json as catalog_json
from .reference_review import (ReferenceReviewService, ReviewAuthority, ReviewBlocked,
    ReviewConflict, _private, _canonical, _unique, catalog_review_blockers)

SCHEMA="vision.ecu-review-workspace.v1"
CONFIG="review-workspace.json"
CATALOG="catalog-candidate.json"
ACCOUNT="accounts.json"
DIRS=("library","reviews","catalog-release","reference-release","incoming")
MAX_CATALOG=512*1024
MAX_CONFIG=16*1024
MAX_IMAGE=8*1024*1024


def _write_new(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def _read_private(path,limit):
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError("unsafe private file")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        s=os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid()
                or stat.S_IMODE(s.st_mode)!=0o600 or s.st_size>limit):
            raise ValueError("private regular file required")
        with os.fdopen(fd,"rb",closefd=False) as stream:
            data=stream.read(limit+1)
        if len(data)>limit: raise ValueError("private file exceeds bound")
        return data
    finally: os.close(fd)


def _config(root):
    value=json.loads(_read_private(root/CONFIG,MAX_CONFIG).decode("utf-8"),object_pairs_hook=_unique)
    if (type(value) is not dict or set(value)!={"schema","authors","reviewers","calibrations","capabilities"}
            or value["schema"]!=SCHEMA or type(value["authors"]) is not list
            or type(value["reviewers"]) is not list or type(value["capabilities"]) is not list
            or type(value["calibrations"]) is not dict):
        raise ValueError("invalid offline review workspace")
    for name in DIRS: _private(root/name)
    return value


def prepare_workspace(path, *, family, variant, base_revision, profile_id, revision, display_name):
    """Initialize an isolated unsigned candidate from a built-in catalog record.

    Copy only existing declarations and FIELD_NOTE observations. Do not promote
    provenance, invent dimensions, copy private evidence or approve anything.
    The physical state is a declared (unverified) proposed top-PCB inspection.
    """
    path=Path(path)
    parent=_private(path.parent)
    if path.parent!=parent or path.name in ("",".",".."):
        raise ValueError("new private workspace path required")
    # Validate IDs by the existing record constructor/service. Refuse any
    # existing workspace; a failed preparation is retained for local review.
    path.mkdir(mode=0o700)
    root=_private(path)
    for name in DIRS: (root/name).mkdir(mode=0o700)
    library=ECULibraryService(root/"library")
    original=library.catalog.get(family,variant,base_revision)
    if revision==base_revision or profile_id==original.profile_id:
        raise ValueError("new profile key and revision required")
    # A new candidate retains declarations/field notes, not verified
    # geometry, calibration or execution capability from an earlier revision.
    if original.status!="DRAFT":
        raise ValueError("built-in unsigned catalog draft required")
    candidate=replace(original,profile_id=profile_id,revision=revision,status="DRAFT",approval=None,
        envelope=None,pcb_regions=(),views=(),calibration_dependencies=(),
        capabilities=(),required_capabilities=(),
        connectors=tuple(replace(c,position=None,identity_required=False) for c in original.connectors))
    draft=library.create_draft(family,variant,base_revision,profile_id,revision,display_name)
    document=draft["profile"]
    document["physical_states"]=[{"state_id":"pcb_exposed_top","display_name":"PCB exposed top",
        "geometry_id":None,"required_recipe_ids":[],"verified":False,"source_id":None}]
    draft=library.update_draft(profile_id,document,draft["etag"])
    _write_new(root/CATALOG,catalog_json(candidate).encode("ascii"))
    _write_new(root/CONFIG,_canonical({"schema":SCHEMA,"authors":[],"reviewers":[],
                                      "calibrations":{},"capabilities":[]}))
    return {"status":"DRAFT","workspace":str(root),"key":profile_id,"revision":revision,
            "catalogBlockers":list(catalog_review_blockers(candidate,{},set())),
            "draftEtag":draft["etag"],"approvalConfigured":False}


def _status(root,cfg):
    # Read the persisted catalog candidate; do not initialize a second store
    # or access an operational service to produce this status.
    record=load_catalog(_read_private(root/CATALOG,MAX_CATALOG))
    return {"status":record.status,"scope":"UNSIGNED_WORKING_CATALOG","profileId":record.profile_id,
            "family":record.family,"variant":record.variant,"revision":record.revision,
            "catalogBlockers":list(catalog_review_blockers(record,cfg["calibrations"],cfg["capabilities"])),
            "approvalConfigured":bool(cfg["authors"] and cfg["reviewers"] and
                                       not set(cfg["authors"]) & set(cfg["reviewers"]) and (root/ACCOUNT).is_file()),
            "fieldNoteCount":len(record.field_notes),"verifiedEnvelope":record.envelope is not None
                and record.envelope.provenance.status=="VERIFIED"}


@contextmanager
def _authenticated(root,cfg,username):
    # The marker is required, and all data is in an explicitly staged
    # workspace. This CLI is never a wrapper around a running Core socket.
    identity=IdentityStore(root/ACCOUNT)
    authority=ReviewAuthority(identity,authors=cfg["authors"],reviewers=cfg["reviewers"])
    token,_=identity.login(username,getpass.getpass("Review account password: "),"local-review-cli")
    try:
        service=ReferenceReviewService(ECULibraryService(root/"library"),authority,
            review_root=root/"reviews",catalog_release_root=root/"catalog-release",
            reference_release_root=root/"reference-release",calibrations=cfg["calibrations"],
            capabilities=cfg["capabilities"])
        yield service,token
    finally:
        identity.logout(token)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",required=True,type=Path)
    parser.add_argument("--username")
    commands=parser.add_subparsers(dest="command",required=True)
    prepare=commands.add_parser("prepare")
    for name in ("family","variant","base-revision","profile-id","revision","display-name"):
        prepare.add_argument("--"+name,required=True)
    commands.add_parser("status")
    commands.add_parser("submit-catalog")
    export=commands.add_parser("export-review-image")
    export.add_argument("review_id");export.add_argument("asset_id")
    submit=commands.add_parser("submit-reference")
    submit.add_argument("key");submit.add_argument("etag");submit.add_argument("state");submit.add_argument("recipe")
    inspect=commands.add_parser("inspect");inspect.add_argument("review_id")
    approve=commands.add_parser("approve");approve.add_argument("review_id")
    approve.add_argument("--decision-reference",required=True)
    ingest=commands.add_parser("ingest-image");ingest.add_argument("name",help="Private 0600 file in incoming/")
    try:
        args=parser.parse_args(argv)
        if args.command=="prepare":
            result=prepare_workspace(args.workspace,family=args.family,variant=args.variant,
                base_revision=args.base_revision,profile_id=args.profile_id,revision=args.revision,
                display_name=args.display_name)
        else:
            root=_private(args.workspace);cfg=_config(root)
            if args.command=="status": result=_status(root,cfg)
            else:
                if not args.username: parser.error("--username is required for review operations")
                with _authenticated(root,cfg,args.username) as (service,token):
                    if args.command=="submit-catalog":
                        result=service.submit_catalog(token,load_catalog(_read_private(root/CATALOG,MAX_CATALOG)))
                    elif args.command=="submit-reference":
                        result=service.submit_reference(token,args.key,args.etag,args.state,args.recipe)
                    elif args.command=="inspect":
                        result=service.inspect(token,args.review_id)
                    elif args.command=="export-review-image":
                        data,mime=service.read_review_image(token,args.review_id,args.asset_id)
                        extension="png" if mime=="image/png" else "jpg"
                        filename="review-"+args.review_id+"-"+args.asset_id+"."+extension
                        _write_new(root/"incoming"/filename,data)
                        result={"status":"EXPORTED","filename":filename}
                    elif args.command=="approve":
                        service.authority.require(token,"reviewer")
                        report=service.inspect(token,args.review_id)
                        if report["status"]!="REVIEW_READY":
                            raise ReviewConflict("review is not current")
                        # Display the exact private immutable snapshot to the
                        # reviewer and require a separate deliberate decision.
                        print(json.dumps(report,ensure_ascii=True,indent=2,allow_nan=False))
                        answer=input("Confirm independent review of exact review ID (type APPROVE): ")
                        if answer!="APPROVE": raise ValueError("approval not confirmed")
                        result=service.approve(token,args.review_id,args.decision_reference)
                    else:
                        name=args.name
                        if Path(name).name!=name or name in ("",".",".."):
                            raise ValueError("incoming filename required")
                        result=service.ingest_image(token,_read_private(root/"incoming"/name,MAX_IMAGE))
        print(json.dumps(result,ensure_ascii=True,indent=2,allow_nan=False))
        return 0
    except ReviewBlocked as exc:
        print(json.dumps({"status":"BLOCKED","blockers":exc.blockers},ensure_ascii=True),file=sys.stderr)
    except (AccessDenied,ReviewConflict,ValueError,OSError,KeyError,TypeError,EOFError):
        print("Review operation rejected or unavailable; no automatic retry. Inspect the private workspace.",file=sys.stderr)
    return 1


if __name__=="__main__":
    raise SystemExit(main())
