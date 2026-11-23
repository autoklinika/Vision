"""Versioned profile metadata and capability checks; no station geometry."""
from dataclasses import dataclass
from typing import Mapping
from types import MappingProxyType
import math

PROFILE_KINDS = frozenset({'station', 'sensor', 'capture', 'tool', 'robot', 'ecu'})


@dataclass(frozen=True)
class Profile:
    kind: str
    identifier: str
    schema_version: str
    revision: str
    approved: bool
    capabilities: frozenset[str]
    required_capabilities: frozenset[str]
    calibration_dependencies: Mapping[str, str]

    def __post_init__(self):
        object.__setattr__(self, 'capabilities', frozenset(self.capabilities))
        object.__setattr__(self, 'required_capabilities', frozenset(self.required_capabilities))
        object.__setattr__(self, 'calibration_dependencies', MappingProxyType(dict(self.calibration_dependencies)))


@dataclass(frozen=True)
class ECUProfile(Profile):
    declared_type: str = ''
    variant: str = ''
    nominal_dimensions: tuple[float, float] = ()
    max_height: float = 0
    pcb_regions: tuple[tuple[float, float, float, float], ...] = ()
    view_targets: tuple[tuple[float, float, float], ...] = ()
    tolerances: tuple[float, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        for name in ('nominal_dimensions', 'pcb_regions', 'view_targets', 'tolerances'):
            value = getattr(self, name)
            object.__setattr__(self, name, tuple(tuple(x) if isinstance(x, (list, tuple)) else x for x in value))


def _valid_ecu(p):
    def numbers(values, length, positive=False):
        return len(values) == length and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and (not positive or v > 0) for v in values)
    return (isinstance(p, ECUProfile) and bool(p.declared_type and p.variant)
            and numbers(p.nominal_dimensions, 2, True) and numbers((p.max_height,), 1, True)
            and bool(p.pcb_regions) and all(numbers(r, 4) and r[2] > 0 and r[3] > 0 for r in p.pcb_regions)
            and bool(p.view_targets) and all(numbers(t, 3) for t in p.view_targets)
            and bool(p.tolerances) and numbers(p.tolerances, len(p.tolerances), True))


def validate_profiles(profiles: Mapping[str, Profile], available_calibrations: Mapping[str, str], requirements: Mapping[str, frozenset[str]]) -> list[str]:
    errors = []
    for kind in sorted(PROFILE_KINDS):
        p = profiles.get(kind)
        if p is None:
            errors.append(f'{kind}: missing profile')
            continue
        if p.kind != kind or not all((p.identifier, p.schema_version, p.revision)) or not p.approved:
            errors.append(f'{kind}: incomplete, mismatched or unapproved profile')
        if kind == 'ecu' and not _valid_ecu(p):
            errors.append('ecu: missing or invalid local view geometry')
        missing = (p.required_capabilities | requirements.get(kind, frozenset())) - p.capabilities
        if missing:
            errors.append(f'{kind}: missing capabilities {sorted(missing)}')
        if not p.calibration_dependencies or any(not name or not revision or available_calibrations.get(name) != revision for name, revision in p.calibration_dependencies.items()):
            errors.append(f'{kind}: missing or mismatched calibration')
    if set(profiles) != PROFILE_KINDS or set(requirements) - PROFILE_KINDS:
        errors.append('unknown or missing profile kind')
    return errors
