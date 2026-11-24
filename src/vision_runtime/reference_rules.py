"""Fail-closed evaluation of approved metric reference features."""
import math


def evaluate_reference(profile, state, record, receipt):
    d = profile.data
    sources = {s['source_id']: s for s in d['provenance_release']['measurement_sources']}
    policies = {p['policy_id']: p for p in d['validation_policies']['policies']}
    def source(sid, limit):
        s = sources.get(sid)
        if not s or s['status'] != 'VERIFIED' or not 1e-9 <= s['uncertainty_mm'] <= limit:
            raise ValueError('reference source uncertainty not verified or exceeds tolerance')
    for pid in (d['recognition_rules']['accepted_policy_ref'], d['localization_rules']['pose_quality_policy_ref']):
        p = policies.get(pid)
        if not p or not p['verified'] or p['kind'] != 'quality': raise ValueError('required quality policy missing')
        source(p['source_id'], float('inf'))
    rules = [r for r in d['recognition_rules']['features_to_check'] if r['state_id'] == state and r['required']]
    if not rules or not d['localization_rules']['required_features']: raise ValueError('required reference features missing')
    by_id = {r['feature_id']: r for r in rules}
    if not set(d['localization_rules']['required_features']) <= set(by_id): raise ValueError('localization feature lacks required recognition rule')
    features = {f['feature_id']: f for f in (*d['connectors_landmarks']['connectors'], *d['connectors_landmarks']['landmarks']) if f['state_id'] == state}
    observed = {c.connector_id: c for c in receipt.connectors}
    expected = {c.connector_id: c for c in record.connectors}
    for rule in rules:
        if rule['method'] != 'rgbd_landmark': raise ValueError('unsupported reference feature method')
        tol = rule['tolerance_mm']
        if not 1e-9 <= tol < float('inf'): raise ValueError('invalid reference tolerance')
        f = features.get(rule['feature_id']); c = observed.get(rule['feature_id']); e = expected.get(rule['feature_id'])
        if not f or not f['verified'] or f['position_mm'] is None or f['uncertainty_mm'] is None or not 1e-9 <= f['uncertainty_mm'] <= tol:
            raise ValueError('required reference feature not measurable')
        source(f['source_id'], tol); source(rule['source_id'], tol)
        if not c or not e or e.position is None or e.position.provenance.uncertainty_mm is None:
            raise ValueError('required feature correspondence missing')
        limit = e.position.provenance.uncertainty_mm
        if not 1e-9 <= limit <= tol or c.uncertainty_mm < 1e-9 or c.uncertainty_mm > min(tol, limit): raise ValueError('connector uncertainty exceeds approved limit')
        if f.get('color') != e.color or c.color != e.color or math.dist(f['position_mm'], e.position.values) > min(tol, limit) or math.dist(c.position_mm, f['position_mm']) > tol:
            raise ValueError('reference connector geometry mismatch')
