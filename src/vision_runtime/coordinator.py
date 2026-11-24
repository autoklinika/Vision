"""Offline S01–S04 coordinator; trust is supplied by an external verifier."""
from dataclasses import dataclass
import hashlib
import json
import math
import re
from vision_core import Context, Evidence, State
from vision_core.workflow import Workflow, CHECKS, _canonical
from vision_core.ports import Request
from vision_modules.ecu_profiles import (Declaration, ECUCatalog, ReleaseStore,
    ECUObservation, ObservedConnector, record_sha256, verify_declared_ecu)
from vision_modules.ecu_reference import compile_profile
from .validation import validate_readiness, validate_observation
from .reference_rules import evaluate_reference


def digest(value):
    return hashlib.sha256(json.dumps(_canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _hash_reference(value):
    if not isinstance(value, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
        raise ValueError('sensor reference must be a SHA-256 reference')


@dataclass(frozen=True)
class RuntimeResult:
    stage: str
    status: str
    reasons: tuple[str, ...] = ()
    reference: str = ''
    operator_id: str = ''
    record_sha256: str = ''
    reference_sha256: str = ''


class VisionRuntimeCoordinator:
    def __init__(self, journal, context, profiles, calibrations, requirements, max_age, *,
                 declaration, record, catalog, release_store, reference_profile,
                 physical_state, recipe, capabilities, asset_store, reference_release_store,
                 trust_verifier, sensor_frame, scene_frame, known_transforms, max_skew,
                 clock, library=None):
        if not isinstance(declaration, Declaration) or not isinstance(catalog, ECUCatalog) or not isinstance(release_store, ReleaseStore):
            raise ValueError('typed declaration, catalog and release store required')
        if not callable(trust_verifier): raise ValueError('external trust verifier required')
        if context.scene_revision or context.frame_id or context.observation_timestamp is not None: raise ValueError('initial context must not contain a scene')
        self.declaration, self.record, self.catalog, self.release_store = declaration, record, catalog, release_store
        self.reference_profile, self.physical_state, self.recipe = reference_profile, physical_state, recipe
        self.calibrations, self.capabilities = dict(calibrations), frozenset(capabilities)
        self.sensor_frame, self.scene_frame = sensor_frame, scene_frame
        self.known_transforms, self.max_skew = frozenset(known_transforms), max_skew
        self.trust_verifier, self.clock, self.max_age = trust_verifier, clock, max_age
        self.asset_store, self.reference_release_store, self.library = asset_store, reference_release_store, library
        self._selection_check()
        self.bundle = self._compile()
        if profiles.get('ecu') != self.bundle.core_profile: raise ValueError('Core ECU profile must match compiled selection')
        self.engine = Workflow(journal, context, profiles, calibrations, requirements, max_age, clock)
        self._observation = None
        history = journal.replay(context.session_id)
        selections = [e for e in history if e.step_id == 'S02' and e.kind == 'result_accepted']
        if selections and selections[-1].data['evidence']['reference'] != self._ref(self.declaration):
            self.engine.invalidate('runtime selection changed')
            raise ValueError('runtime selection changed')

    def _selection_check(self):
        if (self.declaration.family, self.declaration.variant, self.declaration.revision) != (self.record.family, self.record.variant, self.record.revision): raise ValueError('declaration mismatch')
        if self.catalog.select(self.declaration) != self.record: raise ValueError('catalog mismatch')
        self.release_store.require(self.record)

    def _compile(self):
        return compile_profile(self.reference_profile, self.physical_state, self.recipe, self.record, self.catalog, self.release_store, self.calibrations, capabilities=self.capabilities, asset_store=self.asset_store, reference_release_store=self.reference_release_store, library=self.library)

    def begin(self, stage, request):
        """Dispatch a stage before acquiring an externally produced receipt."""
        if stage not in ('S01', 'S02', 'S03', 'S04'): raise ValueError('unsupported stage')
        if not isinstance(request, Request) or request.step_id != stage or request.context != self.engine.context: raise ValueError('correlated Core request required')
        self.engine.start(stage, request.request_id)

    def _start(self, stage, request):
        if not isinstance(request, Request) or request.step_id != stage or request.context != self.engine.context: raise ValueError('correlated Core request required')
        if self.engine.states[stage] == State.RUNNING and self.engine.requests.get(stage) == request.request_id: return
        self.begin(stage, request)

    def _run(self, stage, request, validate):
        self._start(stage, request)
        try:
            context, stamp, ref, details = validate()
            self.engine.complete(Evidence(context.session_id, stage, request.request_id, context, stamp, True, True, frozenset(CHECKS[stage]), ref))
            return RuntimeResult(stage, 'SUCCEEDED', reference=ref, operator_id=self.declaration.operator_id, record_sha256=self.bundle.record_sha256, reference_sha256=self.bundle.reference_sha256, **details)
        except (ValueError, KeyError, OSError) as exc:
            if self.engine.states[stage] == State.RUNNING: self.engine.stop(stage, State.FAILED, str(exc) or 'validation failed')
            return RuntimeResult(stage, 'FAILED', (str(exc),))

    def _trusted(self, kind, receipt):
        before = self._ref(receipt)
        accepted = self.trust_verifier(kind, receipt)
        if self._ref(receipt) != before: raise ValueError('runtime payload changed during independent verification')
        if accepted is not True: raise ValueError('independent source verification failed')
        if receipt.source == self.declaration.operator_id: raise ValueError('source must be independent of operator')

    def _ref(self, value):
        return 'sha256:' + digest({'record': self.record, 'reference': self.reference_profile, 'declaration': self.declaration, 'bundle': self.bundle, 'receipt': value})

    def prepare_station(self, receipt, request):
        def check():
            validate_readiness(receipt, self.engine.context, self.calibrations, now=self.clock(), max_age=self.max_age)
            if receipt.request_id != request.request_id or receipt.timestamp < self.engine.dispatch_times['S01']: raise ValueError('readiness request or dispatch mismatch')
            if not {'rgb','depth','camera_info','tf'} <= receipt.capabilities or not receipt.capabilities <= self.capabilities: raise ValueError('capability mismatch')
            _hash_reference(receipt.reference); _hash_reference(receipt.device_state_reference)
            self._trusted('readiness', receipt)
            validate_readiness(receipt, self.engine.context, self.calibrations, now=self.clock(), max_age=self.max_age)
            return self.engine.context, receipt.timestamp, self._ref(receipt), {}
        return self._run('S01', request, check)

    def confirm_selection(self, request):
        def check():
            self._selection_check()
            if self._compile() != self.bundle: raise ValueError('compiled selection changed')
            return self.engine.context, self.clock(), self._ref(self.declaration), {}
        return self._run('S02', request, check)

    def _validate_observation(self, receipt, request_id=None):
        def structure():
            validate_observation(receipt, self.engine.context, self.calibrations, now=self.clock(), max_age=self.max_age, max_skew=self.max_skew, sensor_frame=self.sensor_frame, scene_frame=self.scene_frame, known_transforms=self.known_transforms, capabilities=self.capabilities)
        structure()
        stamps = (receipt.rgb, receipt.depth, receipt.camera_info, receipt.tf) + tuple(s for s in (receipt.depth_camera_info, receipt.depth_to_rgb_tf) if s is not None)
        if request_id is not None and (receipt.request_id != request_id or min(s.timestamp for s in stamps) < self.engine.dispatch_times['S03']): raise ValueError('observation request or dispatch mismatch')
        for ref in (receipt.reference, *(s.reference for s in stamps), *(c.reference for c in receipt.connectors), *receipt.pcb_references, *receipt.obstacle_references): _hash_reference(ref)
        for ref in (receipt.geometry_reference, receipt.source_proof, receipt.binding_reference):
            _hash_reference(ref)
        self._trusted('observation', receipt)
        # A slow verifier may expire an older depth/TF sample while the RGB
        # timestamp used by Core remains fresh. Recheck every source timestamp.
        structure()
        expected = self.record.envelope
        if expected is None or expected.provenance.uncertainty_mm is None or not 1e-9 <= receipt.envelope_uncertainty_mm <= expected.provenance.uncertainty_mm or any(abs(a-b) > expected.provenance.uncertainty_mm for a,b in zip(expected.values, receipt.envelope_mm)): raise ValueError('envelope mismatch')
        expected_connectors = {c.connector_id:c for c in self.record.connectors}
        if set(expected_connectors) != {c.connector_id for c in receipt.connectors}: raise ValueError('connector count mismatch')
        for c in receipt.connectors:
            e = expected_connectors[c.connector_id]
            if c.color != e.color or e.position is None or e.position.provenance.uncertainty_mm is None or not 1e-9 <= c.uncertainty_mm <= e.position.provenance.uncertainty_mm or math.dist(c.position_mm, e.position.values) > e.position.provenance.uncertainty_mm: raise ValueError('connector landmark mismatch')
        evaluate_reference(self.reference_profile, self.physical_state, self.record, receipt)

    def accept_localization(self, observation, request):
        def check():
            self._validate_observation(observation, request.request_id)
            ctx = Context(observation.session_id, observation.profile_revisions, observation.scene_revision, observation.rgb.timestamp, observation.frame_id)
            self._observation = observation
            return ctx, max(s.timestamp for s in (observation.rgb, observation.depth, observation.camera_info, observation.tf)), self._ref(observation), {}
        result = self._run('S03', request, check)
        if result.status != 'SUCCEEDED': self._observation = None
        return result

    def verify_selected_ecu(self, request):
        def check():
            receipt = self._observation
            if receipt is None: raise ValueError('original localization receipt required after restart')
            self._selection_check()
            if self._compile() != self.bundle: raise ValueError('compiled selection changed')
            self._validate_observation(receipt)
            ctx = self.engine.context
            if (receipt.scene_revision, receipt.frame_id, receipt.rgb.timestamp) != (ctx.scene_revision, ctx.frame_id, ctx.observation_timestamp): raise ValueError('scene mismatch')
            accepted = [e for e in self.engine.journal.replay(ctx.session_id)
                        if e.step_id == 'S03' and e.kind == 'localization_accepted']
            if len(accepted) != 1 or accepted[0].data['evidence']['reference'] != self._ref(receipt):
                raise ValueError('localization receipt differs from accepted S03 evidence')
            obs = ECUObservation(receipt.source, receipt.reference, receipt.frame_id, receipt.session_id, receipt.scene_revision, self.record.revision, receipt.rgb.timestamp, tuple(ObservedConnector(c.connector_id,c.color,c.position_mm) for c in receipt.connectors), receipt.quality, True)
            result = verify_declared_ecu(self.record, self.declaration, obs, session_id=ctx.session_id, frame_id=ctx.frame_id, scene_revision=ctx.scene_revision, now=self.clock(), max_age=self.max_age, calibrations=self.calibrations, catalog=self.catalog)
            if result.status != 'ACCEPTED': raise ValueError(result.status + ': ' + '; '.join(result.reasons))
            return ctx, self.clock(), self._ref(receipt), {}
        return self._run('S04', request, check)
