"""Fail-closed review and explicit conversion to the existing Core contract."""
from .models import ECURecord, record_sha256


def validate_draft(record):
    if not isinstance(record, ECURecord): raise ValueError('record required')
    errors = []
    def verified(m):
        return (m is not None and m.provenance.status == 'VERIFIED' and bool(m.provenance.instrument)
                and m.provenance.datum == 'ecu_local' and m.provenance.uncertainty_mm is not None
                and bool(m.provenance.reference))
    def verified_provenance(p):
        return p is not None and p.status == 'VERIFIED' and bool(p.instrument) and p.datum == 'ecu_local' and p.uncertainty_mm is not None and bool(p.reference)
    if not record.envelope or not verified(record.envelope) or any(x <= 0 for x in record.envelope.values): errors.append('verified body envelope required')
    if not record.pcb_regions or any(not verified(r) or r.values[2] <= 0 or r.values[3] <= 0 for r in record.pcb_regions): errors.append('verified PCB regions required')
    if record.envelope and all(x > 0 for x in record.envelope.values):
        w, h, z = record.envelope.values
        if any(x < 0 or y < 0 or x + rw > w or y + rh > h for x, y, rw, rh in (r.values for r in record.pcb_regions)): errors.append('PCB region outside envelope')
        if any(c.position and any(v < 0 or v > bound for v, bound in zip(c.position.values, (w, h, z))) for c in record.connectors): errors.append('connector outside envelope')
    if not record.views or any(not verified(v.position) or v.quaternion_xyzw is None or not verified_provenance(v.orientation_provenance) for v in record.views): errors.append('verified views and orientations required')
    if not record.connectors or not any(c.identity_required for c in record.connectors) or any(c.identity_required and not verified(c.position) for c in record.connectors): errors.append('verified identity landmarks required')
    if not record.calibration_dependencies: errors.append('calibration dependencies required')
    if not set(record.required_capabilities).issubset(record.capabilities): errors.append('required capabilities unavailable')
    categories = [
        {record.envelope.provenance.reference} if record.envelope else set(),
        {r.provenance.reference for r in record.pcb_regions},
        {v.position.provenance.reference for v in record.views} | {v.orientation_provenance.reference for v in record.views if v.orientation_provenance},
        {c.position.provenance.reference for c in record.connectors if c.identity_required and c.position},
    ]
    if any(not c for c in categories) or any(categories[i] & categories[j] for i in range(len(categories)) for j in range(i)):
        errors.append('independent geometry evidence required')
    if {v.orientation_provenance.reference for v in record.views if v.orientation_provenance} & {v.position.provenance.reference for v in record.views}:
        errors.append('independent orientation evidence required')
    return tuple(errors)


def release_errors(record, calibrations):
    errors = list(validate_draft(record))
    if record.status != 'APPROVED': errors.append('approved review status required')
    a = record.approval
    if a is None or a.profile_id != record.profile_id or a.revision != record.revision or a.digest != record_sha256(record): errors.append('matching human approval required')
    if not isinstance(calibrations, dict) or any(calibrations.get(k) != v for k, v in record.calibration_dependencies): errors.append('matching calibrations required')
    return tuple(errors)


def to_core_ecu_profile(record, calibrations, *, catalog):
    from .catalog import ECUCatalog
    if not isinstance(catalog, ECUCatalog): raise ValueError('registered catalog required')
    try:
        registered = catalog.get(record.family, record.variant, record.revision)
    except KeyError as exc:
        raise ValueError('record not registered') from exc
    if registered != record: raise ValueError('registered record mismatch')
    errors = release_errors(record, calibrations)
    if errors: raise ValueError('NOT_READY: ' + '; '.join(errors))
    from vision_core.profiles import ECUProfile
    return ECUProfile('ecu', record.profile_id, '1', record.revision, True,
                      frozenset(record.capabilities), frozenset(record.required_capabilities), dict(record.calibration_dependencies),
                      record.declared_type, record.variant, record.envelope.values[:2], record.envelope.values[2],
                      tuple(r.values for r in record.pcb_regions), tuple(v.position.values for v in record.views),
                      tuple(v.tolerance_mm for v in record.views), tuple(v.quaternion_xyzw for v in record.views))
