"""Explicit session composition. No hardware commands or fabricated readiness."""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from types import MappingProxyType
from uuid import uuid4

from vision_api.reports import _timestamp, _utc
from vision_core import Context, Journal, State
from vision_core.profiles import validate_profiles
from vision_core.ports import Request
from vision_modules.ecu_profiles import Declaration
from vision_modules.ecu_reference import compile_profile
from vision_runtime import VisionRuntimeCoordinator
from .hardware_presence import usb_hardware_connections, valid_hardware_connection
from .readiness import device_observation, read_snapshot, valid_reason

DEVICES = ("luxonis", "nero", "moveit", "sony")
# Explicit, installed ROS 2 service bindings for the current station.
# The guarded NERO service only proves service liveness (no motion permission).
# The two alternative plan-only scenes include Luxonis and MoveIt. An active
# scene service is NOT evidence that either individual ROS node or device works.
# Do not infer Sony acquisition availability from USB presence or a legacy app.
STANDALONE_CAMERA_UNIT = "vision-luxonis.service"
UNITS = MappingProxyType({
    "luxonis": ("vision-nero-oak-scene-lab.service", "vision-nero-oak800-scene-lab.service", STANDALONE_CAMERA_UNIT),
    "nero": ("vision-nero-guarded-lab.service",),
    "moveit": ("vision-nero-oak-scene-lab.service", "vision-nero-oak800-scene-lab.service"),
})
MAX_AGE = 5.0
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)
USER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", re.ASCII)
HEX32 = re.compile(r"[0-9a-f]{32}", re.ASCII)
SCHEMA = "vision.api.inspection.v1"
BLOCKERS = frozenset({"COMPOSITION_UNCONFIGURED", "NO_APPROVED_SELECTION",
                      "DEVICES_NOT_VERIFIED", "SESSION_ACTIVE", "RECOVERY_REQUIRED"})


class InspectionRejected(Exception):
    """Closed, sanitized rejection; never expose exception text to a client."""


def _matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _private_dir(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("private session directory required")
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private session directory required")
    return path


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _create_private(path, data=b""):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_dir(path.parent)


@dataclass(frozen=True)
class DeviceStatus:
    device: str
    availability: str
    readiness: str
    observed_at: float
    hardware_connection: str = "UNKNOWN"
    readiness_reason: str | None = None

    def __post_init__(self):
        if (self.device not in DEVICES or self.availability not in ("ACTIVE", "INACTIVE", "UNKNOWN")
                or self.readiness not in ("READY", "NOT_READY", "UNKNOWN")
                or not valid_hardware_connection(self.device, self.hardware_connection)
                or (self.readiness_reason is not None and not valid_reason(self.device,self.readiness_reason,self.readiness))
                or type(self.observed_at) not in (float, int) or not math.isfinite(self.observed_at)
                or self.observed_at < 0 or (self.readiness == "READY" and self.availability != "ACTIVE")):
            raise ValueError("invalid device status")


def systemd_diagnostics(readiness_report=None):
    """Read only the liveness of explicitly bound ROS 2 services.

    Missing/unloaded units and unrecognized/transitional states are UNKNOWN,
    not INACTIVE. A loaded active alternative establishes service liveness;
    INACTIVE requires every bound alternative to be known stopped or failed.
    USB and service liveness never establish operational readiness alone.
    The optional local ROS observer adds diagnostic evidence, never trusted
    Runtime composition or inspection/motion authorization.
    """
    names = tuple(dict.fromkeys(unit for units in UNITS.values() for unit in units))
    values = {}
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", "--property=Id,LoadState,ActiveState", *names],
            capture_output=True, text=True, timeout=0.65, check=False)
        duplicates = set()
        for block in result.stdout.split("\n\n"):
            fields = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
            name = fields.get("Id")
            if name not in names:
                continue
            if name in values:
                duplicates.add(name)
            values[name] = (
                fields.get("ActiveState") if fields.get("LoadState") == "loaded" else None
            )
        for name in duplicates:
            values[name] = None
    except (OSError, subprocess.SubprocessError, ValueError):
        values = {}

    def availability(device):
        states = tuple(values.get(name) for name in UNITS.get(device, ()))
        if "active" in states:
            return "ACTIVE"
        if states and all(state in ("inactive", "failed") for state in states):
            return "INACTIVE"
        return "UNKNOWN"

    hardware = usb_hardware_connections()
    now = time.time()
    observations = read_snapshot(readiness_report, now)
    active_scenes = tuple(source for source, unit in zip(("oak","oak800"), UNITS["moveit"])
                          if values.get(unit) == "active")
    # The standalone camera runs in domain 186, not the scene observer's
    # domain 181. Never borrow evidence from an unrelated legacy scene.
    camera_sources = active_scenes + (("standalone186",) if values.get(STANDALONE_CAMERA_UNIT) == "active" else ())
    devices = []
    for device in DEVICES:
        available = availability(device)
        connection = hardware.get(device, "UNKNOWN")
        observation = device_observation(device, available, connection, observations, camera_sources if device == "luxonis" else active_scenes, now)
        devices.append(DeviceStatus(device, available, observation.state, observation.observed_at,
                                    connection, observation.reason))
    return tuple(devices)


@dataclass(frozen=True)
class Selection:
    """Opaque id maps to an exact released recipe, not a client path/profile."""
    selection_id: str
    family: str
    variant: str
    revision: str
    physical_state: str
    recipe: str

    def __post_init__(self):
        if not all(_matches(ID, v) for v in (self.selection_id, self.family, self.variant,
                                            self.revision, self.physical_state, self.recipe)):
            raise ValueError("invalid selection")

    def report(self):
        return {"selectionId": self.selection_id, "family": self.family, "variant": self.variant,
                "revision": self.revision, "physicalState": self.physical_state, "recipe": self.recipe}


class RuntimeComposition:
    """Trusted, installed composition boundary using the real Runtime constructor.

    Releases/stores and the verifier come from explicit backend configuration,
    never IPC/HTTP. A catalog record is read from the single Core-owned catalog.
    This does not discover equipment or generate calibration. Only a trusted
    receipt provider and the existing Runtime verifier can advance S01.
    """
    def __init__(self, *, selections, profiles, calibrations, requirements, capabilities,
                 release_store, reference_release_store, reference_library, asset_store,
                 trust_verifier, readiness_provider, readiness_receipt_provider, sensor_frame, scene_frame,
                 known_transforms, max_age, max_skew, clock=time.time, managed_releases=False):
        selections = tuple(selections)
        if (type(managed_releases) is not bool or not (0 if managed_releases else 1) <= len(selections) <= 16 or any(not isinstance(s, Selection) for s in selections)
                or len({s.selection_id for s in selections}) != len(selections)
                or not callable(readiness_provider) or not callable(readiness_receipt_provider)
                or not callable(trust_verifier) or not callable(clock)):
            raise ValueError("explicit trusted composition required")
        self.selections = MappingProxyType({s.selection_id: s for s in selections})
        self.managed_releases = managed_releases
        self.profiles = MappingProxyType(dict(profiles))
        self.calibrations = MappingProxyType(dict(calibrations))
        self.requirements = MappingProxyType({k: frozenset(v) for k,v in requirements.items()})
        self.capabilities = frozenset(capabilities)
        self.release_store, self.reference_release_store = release_store, reference_release_store
        self.reference_library, self.asset_store = reference_library, asset_store
        self.trust_verifier, self.readiness_provider = trust_verifier, readiness_provider
        self.readiness_receipt_provider = readiness_receipt_provider
        self.sensor_frame, self.scene_frame = sensor_frame, scene_frame
        self.known_transforms = frozenset(known_transforms)
        self.max_age, self.max_skew, self.clock = max_age, max_skew, clock

    @classmethod
    def from_released_references(cls, library, **configuration):
        """Explicit owner configuration; only fully compiled releases appear."""
        from .reference_review import approved_selections
        if "selections" in configuration:
            raise ValueError("choose explicit selections or approved release discovery")
        choices=approved_selections(library,reference_library=configuration["reference_library"],
            reference_store=configuration["reference_release_store"],
            release_store=configuration["release_store"],asset_store=configuration["asset_store"],
            calibrations=configuration["calibrations"],capabilities=configuration["capabilities"])
        return cls(selections=choices,managed_releases=True,**configuration)

    def refresh_released_selections(self, library):
        if not self.managed_releases:
            return
        from .reference_review import approved_selections
        try:
            choices=approved_selections(library,reference_library=self.reference_library,
                reference_store=self.reference_release_store,release_store=self.release_store,
                asset_store=self.asset_store,calibrations=self.calibrations,capabilities=self.capabilities)
        except Exception:
            # The release is retained, but an unavailable/over-limit selection
            # view cannot authorize an inspection.
            choices=()
        self.selections=MappingProxyType({s.selection_id:s for s in choices})

    def resolve(self, library, selection_id):
        choice = self.selections[selection_id]
        record = library.catalog.get(choice.family, choice.variant, choice.revision)
        reference = self.reference_library.select(choice.family, choice.variant, choice.revision)
        bundle = compile_profile(reference, choice.physical_state, choice.recipe, record,
                                 library.catalog, self.release_store, dict(self.calibrations),
                                 capabilities=self.capabilities, asset_store=self.asset_store,
                                 reference_release_store=self.reference_release_store,
                                 library=self.reference_library)
        profiles = {**self.profiles, "ecu": bundle.core_profile}
        if validate_profiles(profiles, self.calibrations, self.requirements):
            raise ValueError("profiles not ready")
        return choice, record, reference, profiles

    def build(self, library, resolved, operator, session_id, journal):
        choice, record, reference, profiles = resolved
        # Keep the browser identity exact in the private intent record. A stable
        # namespaced digest is used in the stricter Runtime identifier grammar.
        operator_id = "op-" + hashlib.sha256(operator.encode("utf-8")).hexdigest()[:48]
        def independent_verifier(kind, receipt):
            # Runtime also rejects its normalized operator id. Preserve the
            # same independence rule for the authenticated browser identity.
            if receipt.source == operator:
                return False
            return self.trust_verifier(kind, receipt)
        return VisionRuntimeCoordinator(
            journal, Context(session_id, {k:p.revision for k,p in profiles.items()}),
            profiles, self.calibrations, self.requirements, self.max_age,
            declaration=Declaration(choice.family, choice.variant, choice.revision, operator_id),
            record=record, catalog=library.catalog, release_store=self.release_store,
            reference_profile=reference, physical_state=choice.physical_state, recipe=choice.recipe,
            capabilities=self.capabilities, asset_store=self.asset_store,
            reference_release_store=self.reference_release_store, trust_verifier=independent_verifier,
            sensor_frame=self.sensor_frame, scene_frame=self.scene_frame, known_transforms=self.known_transforms,
            max_skew=self.max_skew, clock=self.clock, library=self.reference_library, strict_planning=True)

    def prepare(self, runtime):
        """S01 -> S02 through the existing verified gates; never dispatch S03.

        The provider obtains a fresh, independently verifiable ReadinessReceipt
        for the exact request after dispatch. Service status is not a receipt.
        """
        request = Request("S01", "ready-" + uuid4().hex, runtime.engine.context)
        runtime.begin("S01", request)
        try:
            receipt = self.readiness_receipt_provider(request)
        except Exception:
            runtime.engine.stop("S01", State.FAILED, "readiness source unavailable")
            return
        result = runtime.prepare_station(receipt, request)
        if result.status == "SUCCEEDED":
            runtime.confirm_selection(Request("S02", "select-" + uuid4().hex, runtime.engine.context))


def _can_close(engine):
    # Only completed inspection or pre-localization session with no running
    # stage. Closing a physical/motion stage is NOT a stop/recovery operation.
    return (engine.states["S11"] == State.SUCCEEDED or
            (not any(state in (State.READY, State.RUNNING) for state in engine.states.values())
             and not (set(engine.requests) - {"S01", "S02"})))


class InspectionOwner:
    """One session owner; caller holds the host lifecycle lock throughout."""
    def __init__(self, host, *, composition=None, session_root=None, diagnostics=None):
        if composition is not None and not isinstance(composition, RuntimeComposition):
            raise ValueError("typed runtime composition required")
        if composition is not None and session_root is None:
            raise ValueError("private session root required")
        self.host, self.composition = host, composition
        self.root = _private_dir(session_root) if session_root is not None else None
        self.diagnostics = diagnostics or systemd_diagnostics
        self.journal = None
        self.owned_id = None
        self._poisoned = False
        self.intent_token = uuid4().hex

    @property
    def marker(self):
        return self.root / "active-session" if self.root is not None else None

    def _marker_exists(self):
        return self.marker is not None and os.path.lexists(self.marker)

    def _devices(self):
        now = time.time()
        provider = self.composition.readiness_provider if self.composition is not None else self.diagnostics
        try:
            items = tuple(provider())
            now = time.time()
            if (len(items) != len(DEVICES) or any(not isinstance(x, DeviceStatus) for x in items)
                    or set(x.device for x in items) != set(DEVICES)):
                raise ValueError("invalid device snapshot")
            data = {x.device:x for x in items}
            return tuple(data[d] if 0 <= now-data[d].observed_at <= MAX_AGE
                         else DeviceStatus(d,"UNKNOWN","UNKNOWN",now) for d in DEVICES)
        except Exception:
            return tuple(DeviceStatus(d,"UNKNOWN","UNKNOWN",now) for d in DEVICES)

    def _choices(self):
        result = []
        if self.composition is not None:
            for selection in self.composition.selections:
                try:
                    result.append(self.composition.resolve(self.host.library, selection)[0])
                except Exception:
                    continue
        return tuple(result)

    def report(self):
        station = self.host.station_report()
        devices = self._devices()
        choices = self._choices()
        blockers = []
        if self.composition is None or self.root is None:
            blockers.append("COMPOSITION_UNCONFIGURED")
        if not choices:
            blockers.append("NO_APPROVED_SELECTION")
        if any(d.readiness != "READY" or d.readiness_reason is not None for d in devices):
            blockers.append("DEVICES_NOT_VERIFIED")
        if station["state"] == "SESSION_ACTIVE":
            blockers.append("SESSION_ACTIVE")
        recovery_required = self._poisoned or (self._marker_exists() and
            (self.owned_id is None or station["sessionId"] != self.owned_id))
        if recovery_required:
            blockers.append("RECOVERY_REQUIRED")
        closable = False
        if not recovery_required and self.owned_id is not None and self.host._runtime is not None:
            engine = self.host._runtime.engine
            with engine.owner_operation():
                closable = _can_close(engine)
        return {"schema":SCHEMA, "source":"STATION", "instanceId":station["instanceId"],
                "capturedAt":_timestamp(time.time()), "sessionId":station["sessionId"],
                "intentToken":self.intent_token,
                "devices":[{"device":d.device, "availability":d.availability, "readiness":d.readiness,
                            "observedAt":_timestamp(d.observed_at),
                            "hardwareConnection":d.hardware_connection,
                            **({"readinessReason":d.readiness_reason} if d.readiness_reason is not None else {})} for d in devices],
                "selections":[s.report() for s in choices], "blockers":blockers,
                "startAllowed":not blockers, "closeAllowed":closable}

    def start(self, *, selection_id, instance_id, intent_token, operator):
        if not (_matches(ID, selection_id) and _matches(HEX32, instance_id) and _matches(HEX32, intent_token) and _matches(USER, operator)):
            raise ValueError("invalid inspection intent")
        report = self.report()
        if (instance_id != report["instanceId"] or intent_token != self.intent_token or not report["startAllowed"]
                or selection_id not in {s["selectionId"] for s in report["selections"]}
                or self.host._runtime is not None or self.owned_id is not None or self._marker_exists()):
            raise InspectionRejected()
        # Recompile the selected release before opening the journal; no
        # cached or user-supplied profile can authorize the session.
        try:
            resolved = self.composition.resolve(self.host.library, selection_id)
        except Exception:
            raise InspectionRejected() from None
        if any(d.readiness != "READY" or d.readiness_reason is not None for d in self._devices()):
            raise InspectionRejected()
        session_id = "inspection-" + uuid4().hex
        root = _private_dir(self.root)
        self.intent_token = uuid4().hex
        _create_private(self.marker, (session_id + "\n").encode("ascii"))
        journal = None
        try:
            folder = root / session_id
            folder.mkdir(mode=0o700)
            _sync_dir(root)
            _create_private(folder / "intent.json", json.dumps({"sessionId":session_id,
                            "operator":operator, "selection":resolved[0].report()},
                            sort_keys=True, ensure_ascii=True).encode("ascii"))
            journal_path = folder / "journal.sqlite"
            _create_private(journal_path)
            journal = Journal(str(journal_path))
            runtime = self.composition.build(self.host.library, resolved, operator, session_id, journal)
            self.host.attach_runtime(runtime)
            self.journal, self.owned_id = journal, session_id
        except Exception:
            if journal is not None:
                journal.close()
            self._poisoned = True
            # Keep durable marker even after an uncertain partial start.
            raise InspectionRejected() from None
        try:
            self.composition.prepare(runtime)
        except Exception:
            # A journal/transport failure may be ambiguous. Keep the bound
            # session and durable marker; do not resume, retry, or claim PASS.
            self._poisoned = True
            raise InspectionRejected() from None
        return self.host.station_report()

    def close(self, *, session_id, instance_id, operator):
        if not (_matches(ID, session_id) and _matches(HEX32, instance_id) and _matches(USER, operator)):
            raise ValueError("invalid inspection intent")
        station = self.host.station_report()
        if (self._poisoned or instance_id != station["instanceId"] or session_id != self.owned_id
                or session_id != station["sessionId"] or self.host._runtime is None or self.journal is None):
            raise InspectionRejected()
        engine = self.host._runtime.engine
        with engine.owner_operation():
            if not _can_close(engine):
                raise InspectionRejected()
            try:
                if engine.states["S11"] != State.SUCCEEDED:
                    engine.invalidate("operator closed pre-localization inspection")
                _create_private(self.root / session_id / "closed.json",
                                json.dumps({"operator":operator,"sessionId":session_id}, sort_keys=True).encode("ascii"))
                if not self.host.clear_runtime(station["sessionViewId"]):
                    raise InspectionRejected()
                self.journal.close()
                self.journal = None
                self.marker.unlink()
                _sync_dir(self.root)
                self.owned_id = None
                self.intent_token = uuid4().hex
            except Exception:
                self._poisoned = True
                raise InspectionRejected() from None
        return self.host.station_report()

    def shutdown(self):
        # Do not clear a durable marker or auto-resume on process restart.
        if self.journal is not None:
            self.journal.close()
            self.journal = None


def validate_inspection_report(value):
    if (type(value) is not dict or set(value) != {"schema","source","instanceId","capturedAt","sessionId",
            "devices","selections","blockers","startAllowed","closeAllowed","intentToken"}
            or value["schema"] != SCHEMA or value["source"] != "STATION"
            or not _matches(HEX32,value["instanceId"]) or not _matches(HEX32,value["intentToken"]) or not _utc(value["capturedAt"])
            or (value["sessionId"] is not None and not isinstance(value["sessionId"],str))
            or type(value["startAllowed"]) is not bool or type(value["closeAllowed"]) is not bool
            or type(value["blockers"]) is not list or not all(isinstance(x,str) and x in BLOCKERS for x in value["blockers"])
            or value["startAllowed"] != (not value["blockers"]) or len(set(value["blockers"])) != len(value["blockers"])
            or type(value["devices"]) is not list or len(value["devices"]) != len(DEVICES)
            or type(value["selections"]) is not list or len(value["selections"]) > 16):
        return False
    if value["sessionId"] is not None and (len(value["sessionId"]) > 128 or not re.fullmatch(r"[A-Za-z0-9_.:-]+",value["sessionId"])):
        return False
    if value["closeAllowed"] and value["sessionId"] is None:
        return False
    for device,row in zip(DEVICES,value["devices"]):
        # Accept only the exact legacy shape or the documented optional
        # hardware observation extension; old Core releases remain readable.
        base_keys = {"device","availability","readiness","observedAt"}
        if (type(row) is not dict or not base_keys <= set(row) <= base_keys | {"hardwareConnection","readinessReason"}
                or not valid_hardware_connection(device, row.get("hardwareConnection", "UNKNOWN"))
                or ("readinessReason" in row and (not isinstance(row["readinessReason"],str)
                    or not valid_reason(device,row["readinessReason"],row["readiness"])))
                or row["device"] != device or row["availability"] not in ("ACTIVE","INACTIVE","UNKNOWN")
                or row["readiness"] not in ("READY","NOT_READY","UNKNOWN") or not _utc(row["observedAt"])
                or (row["readiness"] == "READY" and row["availability"] != "ACTIVE")):
            return False
    ids = []
    for row in value["selections"]:
        if (type(row) is not dict or set(row) != {"selectionId","family","variant","revision","physicalState","recipe"}
                or not all(_matches(ID,x) for x in row.values())):
            return False
        ids.append(row["selectionId"])
    return len(ids) == len(set(ids)) and (not value["startAllowed"] or
                (bool(ids) and value["sessionId"] is None and all(x["readiness"]=="READY" and "readinessReason" not in x for x in value["devices"])))
