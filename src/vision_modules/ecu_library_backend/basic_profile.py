"""V2 authoring declaration, not an executable reference or readiness receipt.

Identity remains in the existing V1 document. Raw dimensions, private photo
associations and inspection preferences have their own small declaration in
the same immutable generation. No invented source, uncertainty, camera pose,
calibration or policy enters the executable contract.
"""
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import unicodedata

from vision_modules.ecu_reference.models import thaw

SCHEMA = "vision.ecu-declaration.v2"
STATES = {"closed": "Closed ECU", "pcb_top": "Exposed PCB top", "pcb_bottom": "Exposed PCB bottom"}
PHOTO_ROLES = ("label", "housing", "connectors", "pcb_top", "pcb_bottom", "other")
TEMPLATES = ("standard_pcb",)  # requested preference only; not an installed template
LIMIT = 16384
MAX_IMAGES = 32
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
_SHA = re.compile(r"[a-f0-9]{64}", re.ASCII)


def text(value, limit, *, empty=False):
    return (isinstance(value,str) and len(value)<=limit and (empty or bool(value.strip()))
            and not any(unicodedata.category(c).startswith("C") for c in value))


def identity_id(label):
    """Spaces are accepted in display labels; technical IDs stay stable."""
    if not text(label,64):
        raise ValueError("invalid family or variant label")
    value=re.sub(r" +","_",label.strip())
    if not _ID.fullmatch(value):
        raise ValueError("family and variant use letters, digits, spaces, _ or -")
    return value


@lru_cache(maxsize=1)
def _technical_defaults():
    path=Path(__file__).resolve().parents[3]/"docs/templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json"
    data=json.loads(path.read_text(encoding="utf-8"))
    return {k:v for k,v in data.items() if k not in ("metadata","identity")}


def eligible(profile):
    """Only a blank technical V1 draft may adopt V2, explicitly and losslessly."""
    data=thaw(profile.data)
    if (data["metadata"]["status"]!="DRAFT" or
            not all(data.get(k)==v for k,v in _technical_defaults().items()) or
            any(data["identity"][k] for k in ("variant_relations","distinguishing_features","known_indistinguishable_variants"))):
        return False
    try:
        validate_identity_input({**{k:data["identity"][k] for k in ("manufacturer","manufacturer_part_numbers","oem_part_numbers","aliases")},
                                 "displayName":data["metadata"]["display_name"]})
    except ValueError:
        return False
    return True


def validate_identity_input(value):
    if type(value) is not dict or set(value)!={"manufacturer","manufacturer_part_numbers","oem_part_numbers","aliases","displayName"}:
        raise ValueError("invalid simplified identity fields")
    if value["manufacturer"] is not None and not text(value["manufacturer"],160):
        raise ValueError("invalid manufacturer")
    if not text(value["displayName"],160) or "/" in value["displayName"] or "\\" in value["displayName"]:
        raise ValueError("invalid display name")
    for k in ("manufacturer_part_numbers","oem_part_numbers","aliases"):
        rows=value[k]
        if type(rows) is not list or len(rows)>64 or any(not text(s,160) for s in rows) or len(set(rows))!=len(rows):
            raise ValueError("invalid part numbers or aliases")
    return value


def validate_basic(value, profile):
    if type(value) is not dict or set(value)!={"schema","familyLabel","variantLabel","states","photos","inspection"} or value["schema"]!=SCHEMA:
        raise ValueError("invalid ECU declaration")
    m=profile.data["metadata"]
    if (not eligible(profile) or identity_id(value["familyLabel"])!=m["family_id"]
            or identity_id(value["variantLabel"])!=m["variant_id"]):
        raise ValueError("declaration does not match an unsigned empty technical profile")
    states=value["states"]
    if type(states) is not list or len(states)>len(STATES):
        raise ValueError("invalid physical states")
    seen=set()
    for state in states:
        if type(state) is not dict or set(state)!={"stateId","dimensionsMm"} or state["stateId"] not in STATES or state["stateId"] in seen:
            raise ValueError("invalid or duplicate physical state")
        seen.add(state["stateId"])
        dims=state["dimensionsMm"]
        if type(dims) is not list or len(dims)!=3 or any(x is not None and
                (type(x) not in (int,float) or not math.isfinite(x) or not 0<x<=1000000) for x in dims):
            raise ValueError("dimensions must be positive millimetres or missing")
    photos=value["photos"]
    if type(photos) is not list or len(photos)>MAX_IMAGES:
        raise ValueError("invalid photo list")
    hashes=set()
    for photo in photos:
        if (type(photo) is not dict or set(photo)!={"sha256","mime","bytes","stateId","role"}
                or photo["stateId"] not in seen or photo["role"] not in PHOTO_ROLES
                or not isinstance(photo["sha256"],str) or not _SHA.fullmatch(photo["sha256"])
                or photo["sha256"] in hashes or photo["mime"] not in ("image/jpeg","image/png")
                or type(photo["bytes"]) is not int or not 1<=photo["bytes"]<=2*1024*1024):
            raise ValueError("invalid or duplicate reference photo")
        hashes.add(photo["sha256"])
    i=value["inspection"]
    if (type(i) is not dict or set(i)!={"template","overview","oblique","details","customRoi","notes"}
            or (i["template"] is not None and i["template"] not in TEMPLATES)
            or any(type(i[k]) is not bool for k in ("overview","oblique","details","customRoi"))
            or not isinstance(i["notes"],str) or len(i["notes"])>1024
            or not text(i["notes"].replace("\n",""),1024,empty=True)):
        raise ValueError("invalid inspection preferences")
    if len(json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(",",":")).encode("ascii"))>LIMIT:
        raise ValueError("ECU declaration exceeds storage budget")
    return value


def basic_payload(value):
    if type(value) is not dict or set(value)!={"identity","declaration"}:
        raise ValueError("invalid simplified profile payload")
    validate_identity_input(value["identity"])
    if type(value["declaration"]) is not dict:
        raise ValueError("invalid simplified declaration")
    return value["identity"],value["declaration"]


def apply_identity(document, identity):
    validate_identity_input(identity)
    document["metadata"]["display_name"]=identity["displayName"]
    document["identity"].update({k:identity[k] for k in ("manufacturer","manufacturer_part_numbers","oem_part_numbers","aliases")})
    return document
