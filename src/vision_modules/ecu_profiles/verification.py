"""Compare an explicit declaration with separately supplied, session-bound evidence."""
from dataclasses import dataclass
import math
from .models import identifier, frame_identifier, text, number, vector
from .promotion import release_errors

@dataclass(frozen=True)
class Declaration:
    family: str
    variant: str
    revision: str
    operator_id: str
    def __post_init__(self):
        for v in (self.family, self.variant, self.revision, self.operator_id): identifier(v)

@dataclass(frozen=True)
class ObservedConnector:
    connector_id: str
    color: str
    position_mm: tuple | None
    def __post_init__(self):
        identifier(self.connector_id)
        if self.color not in ('black', 'gray', 'other'): raise ValueError('invalid color')
        if self.position_mm is not None: object.__setattr__(self, 'position_mm', vector(self.position_mm, 3))

@dataclass(frozen=True)
class ECUObservation:
    source: str
    reference: str
    frame_id: str
    session_id: str
    scene_revision: str
    profile_revision: str
    timestamp: float
    connectors: tuple[ObservedConnector, ...]
    quality: bool
    verified: bool
    def __post_init__(self):
        for v in (self.source, self.session_id, self.scene_revision, self.profile_revision): identifier(v)
        frame_identifier(self.frame_id)
        text(self.reference)
        if type(self.timestamp) not in (int, float) or not math.isfinite(self.timestamp): raise ValueError('invalid timestamp')
        if type(self.quality) is not bool or type(self.verified) is not bool: raise ValueError('invalid observation quality')
        if not isinstance(self.connectors, (tuple, list)) or len(self.connectors) > 128 or any(not isinstance(c, ObservedConnector) for c in self.connectors): raise ValueError('invalid connectors')
        object.__setattr__(self, 'connectors', tuple(self.connectors))
        if len({c.connector_id for c in self.connectors}) != len(self.connectors): raise ValueError('duplicate observed connector')

@dataclass(frozen=True)
class VerificationResult:
    status: str
    reasons: tuple[str, ...]


def verify_declared_ecu(record, declaration, observation, *, session_id, frame_id, scene_revision, now, max_age, calibrations, catalog=None):
    if not isinstance(declaration, Declaration) or not isinstance(observation, ECUObservation): raise ValueError('typed declaration and observation required')
    if type(now) not in (int, float) or not math.isfinite(now): raise ValueError('invalid current time')
    number(max_age, True)
    errors = []
    if (declaration.family, declaration.variant, declaration.revision) != (record.family, record.variant, record.revision): errors.append('declaration mismatch')
    if (observation.session_id, observation.frame_id, observation.scene_revision, observation.profile_revision) != (session_id, frame_id, scene_revision, record.revision): errors.append('observation context mismatch')
    if not 0 <= now - observation.timestamp <= max_age: errors.append('stale observation')
    if not observation.quality or not observation.verified: errors.append('unverified observation')
    if observation.source == declaration.operator_id: errors.append('observation source must be independent of declarer')
    expected = {c.connector_id: c for c in record.connectors}
    observed = {c.connector_id: c for c in observation.connectors}
    if set(expected) != set(observed) or any(observed[k].color != c.color for k, c in expected.items() if k in observed): errors.append('connector pattern mismatch')
    if errors: return VerificationResult('REJECTED', tuple(errors))
    if record.status != 'APPROVED': return VerificationResult('PRELIMINARY', ('connector pattern matches; not ready',))
    errors.extend(release_errors(record, calibrations))
    if errors: return VerificationResult('REJECTED', tuple(errors))
    from .catalog import ECUCatalog
    if not isinstance(catalog, ECUCatalog): return VerificationResult('NOT_READY', ('registered catalog required',))
    try:
        if catalog.select(declaration) != record: return VerificationResult('REJECTED', ('registered record mismatch',))
    except (KeyError, ValueError):
        return VerificationResult('REJECTED', ('record not registered',))
    def fits(candidate):
        expected = {c.connector_id: c for c in candidate.connectors}
        if set(expected) != set(observed) or any(observed[k].color != c.color for k, c in expected.items()): return False
        for c in candidate.connectors:
            if c.identity_required:
                o = observed[c.connector_id]
                if c.position is None or o.position_mm is None or c.position.provenance.uncertainty_mm is None or math.dist(c.position.values, o.position_mm) > c.position.provenance.uncertainty_mm: return False
        return True
    if not fits(record): return VerificationResult('REJECTED', ('identity landmark mismatch',))
    def physically_compatible(candidate):
        # Connector IDs are internal labels, NOT independently observable
        # physical features across different ECU variant catalog records.
        # Build an injective color + measured-position correspondence
        # without relying on variant-specific connector_id strings.
        features = tuple(candidate.connectors)
        samples = tuple(observation.connectors)
        if len(features) != len(samples):
            return False

        def compatible(feature, sample):
            if feature.color != sample.color:
                return False
            if not feature.identity_required:
                return True
            if (feature.position is None or sample.position_mm is None
                    or feature.position.provenance.uncertainty_mm is None):
                return False
            return (math.dist(feature.position.values, sample.position_mm)
                    <= feature.position.provenance.uncertainty_mm)

        edges = [
            tuple(i for i, sample in enumerate(samples) if compatible(feature, sample))
            for feature in features
        ]
        if any(not choices for choices in edges):
            return False
        matched = [-1] * len(samples)

        def assign(feature_index, visited):
            for sample_index in edges[feature_index]:
                if sample_index in visited:
                    continue
                visited.add(sample_index)
                prior = matched[sample_index]
                if prior == -1 or assign(prior, visited):
                    matched[sample_index] = feature_index
                    return True
            return False

        return all(assign(i, set()) for i in range(len(features)))

    for candidate in catalog.list_records(record.family):
        if candidate.variant != record.variant and candidate.status == 'APPROVED':
            if release_errors(candidate, calibrations):
                return VerificationResult('NOT_READY', ('other approved variant cannot be evaluated',))
            if physically_compatible(candidate):
                return VerificationResult('AMBIGUOUS', ('observation matches another approved variant',))
    return VerificationResult('ACCEPTED', ())
