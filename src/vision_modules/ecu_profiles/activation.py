"""Trusted adapter gate for binding verified identity to an offline Core plan."""
from dataclasses import dataclass
from .models import record_sha256
from .promotion import to_core_ecu_profile
from .releases import ReleaseStore
from .verification import Declaration, ECUObservation, verify_declared_ecu


@dataclass(frozen=True)
class IdentityReceipt:
    record_sha256: str
    declaration: Declaration
    observation: ECUObservation
    plan_digest: str


def to_core_approved(record, calibrations, *, catalog, release_store):
    if not isinstance(release_store, ReleaseStore): raise ValueError('release store required')
    profile = to_core_ecu_profile(record, calibrations, catalog=catalog)
    release_store.require(record)
    return profile


def select_and_plan_verified(declaration, observation, context, observed_ecu, profiles, calibrations, requirements, now, max_age, *, catalog, release_store, min_coverage, require_raw, extra_kinds=()):
    from vision_core import Context
    from vision_core.repeatability import ObservedECU, create_plan
    if not isinstance(declaration, Declaration) or not isinstance(observation, ECUObservation) or not isinstance(context, Context) or not isinstance(observed_ecu, ObservedECU):
        raise ValueError('typed identity and context required')
    try: record = catalog.select(declaration)
    except (AttributeError, KeyError) as exc: raise ValueError('exact registered record required') from exc
    profile = to_core_approved(record, calibrations, catalog=catalog, release_store=release_store)
    if (context.profile_revisions.get('ecu') != record.revision or context.observation_timestamp != observation.timestamp
        or observed_ecu.timestamp != observation.timestamp or observed_ecu.reference != observation.reference
        or observed_ecu.frame_id != observation.frame_id or observed_ecu.scene_revision != observation.scene_revision
        or observed_ecu.ecu_revision != record.revision or observed_ecu.declared_type != record.declared_type
        or observed_ecu.variant != record.variant):
        raise ValueError('identity observation mismatch')
    result = verify_declared_ecu(record, declaration, observation, session_id=context.session_id, frame_id=context.frame_id,
                                 scene_revision=context.scene_revision, now=now, max_age=max_age, calibrations=calibrations, catalog=catalog)
    if result.status != 'ACCEPTED': raise ValueError('identity not accepted: ' + '; '.join(result.reasons))
    selected = dict(profiles); selected['ecu'] = profile
    plan = create_plan(context, selected, calibrations, requirements, observed_ecu, now, max_age,
                       min_coverage=min_coverage, require_raw=require_raw, extra_kinds=extra_kinds)
    return plan, IdentityReceipt(record_sha256(record), declaration, observation, plan.digest)
