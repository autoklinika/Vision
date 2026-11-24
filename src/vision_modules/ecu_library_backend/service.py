"""Transport-independent ECU catalog and unsigned reference-draft service."""
import ast
import copy
import json
import os
from dataclasses import asdict
from pathlib import Path

from vision_modules.ecu_profiles import ECUCatalog, load_json as load_catalog
from vision_modules.ecu_reference import load_json, evaluate_readiness
from vision_modules.ecu_reference.models import thaw
from .storage import DraftStore, REPO, identifier, _check_path

TEMPLATE = REPO / 'docs/templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json'
SCOPES = ('browse_and_select', 'verify_identity', 'localize', 'photo_inspection', 'thermal_relative', 'thermal_radiometric')


def _document(value):
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False, allow_nan=False)
    return load_json(value)


class ECULibraryService:
    """Operate on a private store; constructing this object initializes that store."""
    def __init__(self, data_root, catalog_dir=None):
        self.store = DraftStore(data_root)
        self.catalog = ECUCatalog()
        directories = [REPO / 'config/ecu_profiles']
        if catalog_dir is not None:
            directories.append(Path(catalog_dir))
        for directory in directories:
            directory = _check_path(directory)
            if not directory.is_dir():
                raise ValueError('catalog directory required')
            for path in sorted(directory.glob('*.json')):
                _check_path(path)
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    import stat
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise ValueError('catalog must be regular file')
                    with os.fdopen(fd, 'rb', closefd=False) as f:
                        data = f.read(512 * 1024 + 1)
                    if len(data) > 512 * 1024:
                        raise ValueError('catalog too large')
                    self.catalog.register(load_catalog(data))
                finally:
                    os.close(fd)

    def list_catalog(self, query=''):
        if not isinstance(query, str): raise ValueError('query must be a string')
        items = []
        for record in self.catalog.list_records():
            d = asdict(record)
            item = {'type': 'ecu_catalog', 'family': record.family, 'variant': record.variant,
                    'revision': record.revision, 'display_name': record.declared_type,
                    'status': record.status, 'readiness': 'NOT_READY', 'connectors': d['connectors'],
                    'envelope': d['envelope'], 'field_notes': d['field_notes'], 'field_notes_verified': False}
            if query.casefold() in json.dumps(item, ensure_ascii=False).casefold(): items.append(item)
        return items

    def catalog_detail(self, family, variant, revision):
        for value in (family, variant, revision): identifier(value)
        try: record = self.catalog.get(family, variant, revision)
        except KeyError as exc: raise FileNotFoundError('catalog selection not found') from exc
        return {'type': 'ecu_catalog', 'record': asdict(record), 'readiness': {'status': 'NOT_READY', 'blockers': ['Catalog record is not an approved reference profile']}, 'field_notes_verified': False}

    def list_profiles(self, query='', status=None):
        if not isinstance(query, str) or (status is not None and not isinstance(status, str)):
            raise ValueError('invalid filter')
        result = []
        for key in self.store.keys():
            profile, etag = self.store.get(key)
            m = profile.data['metadata']
            item = {'type': 'reference_draft', 'key': key, 'profile_id': key, 'family': m['family_id'], 'variant': m['variant_id'], 'revision': m['profile_revision'], 'display_name': m['display_name'], 'status': m['status'], 'readiness': 'NOT_READY', 'etag': etag}
            if (status is None or status == m['status']) and query.casefold() in json.dumps(item, ensure_ascii=False).casefold(): result.append(item)
        return result

    def create_draft(self, family, variant, catalog_revision, profile_id, revision, display_name):
        self.catalog_detail(family, variant, catalog_revision)
        identifier(profile_id); identifier(revision)
        if not isinstance(display_name, str) or not display_name.strip(): raise ValueError('display_name required')
        d = json.loads(TEMPLATE.read_text(encoding='utf-8'))
        d['metadata'].update(schema_version='1', template_only=False, profile_id=profile_id, family_id=family, variant_id=variant, profile_revision=revision, display_name=display_name, status='DRAFT')
        p = _document(d)
        with self.store.transaction(): etag = self.store.save(profile_id, p, create=True)
        return {'key': profile_id, 'profile': thaw(p.data), 'etag': etag}

    def get_draft(self, profile_id):
        p, etag = self.store.get(profile_id)
        return {'key': profile_id, 'profile': thaw(p.data), 'etag': etag}

    def update_draft(self, profile_id, document, expected_etag):
        p = _document(document)
        with self.store.transaction(): etag = self.store.save(profile_id, p, expected_etag)
        return {'key': profile_id, 'profile': thaw(p.data), 'etag': etag}

    def clone_draft(self, profile_id, new_profile_id, new_revision):
        identifier(new_profile_id); identifier(new_revision)
        with self.store.transaction():
            old = self.get_draft(profile_id)['profile']; m = old['metadata']
            if m['status'] != 'DRAFT' or m['template_only'] or m['content_sha256'] or m['approval_scopes'] or old['provenance_release']['release_approval'] or old['provenance_release']['released_snapshot_sha256']:
                raise ValueError('source must be an unsigned draft')
            if new_revision == m['profile_revision']: raise ValueError('new revision required')
            m.update(profile_id=new_profile_id, profile_revision=new_revision)
            p = _document(old)
            etag = self.store.save(new_profile_id, p, create=True)
        return {'key': new_profile_id, 'profile': thaw(p.data), 'etag': etag}

    def history(self, profile_id):
        return self.store.history(profile_id)

    def validate_profile(self, document, state_id, recipe_id, scope, capabilities=None, calibrations=None, asset_ids_verified=None):
        try: p = _document(document)
        except (ValueError, TypeError, OverflowError, RecursionError) as exc:
            return {'valid': False, 'status': 'PARSE_ERROR', 'diagnostic_kind': 'parse_error', 'errors': [str(exc)], 'blockers': []}
        if scope not in SCOPES or not isinstance(state_id, str) or not isinstance(recipe_id, str):
            return {'valid': False, 'status': 'INPUT_ERROR', 'diagnostic_kind': 'input_error', 'errors': ['invalid state, recipe or scope'], 'blockers': []}
        try:
            report = evaluate_readiness(p, state_id, recipe_id, scope, capabilities=capabilities or set(), calibrations=calibrations or {}, asset_ids_verified=asset_ids_verified or set())
        except (ValueError, TypeError, KeyError) as exc:
            return {'valid': False, 'status': 'INPUT_ERROR', 'diagnostic_kind': 'input_error', 'errors': [str(exc)], 'blockers': []}
        return {'valid': True, 'status': report.status, 'diagnostic_kind': 'ready' if report.status == 'PASS' else 'missing_requirements', 'errors': [], 'blockers': list(report.blockers)}

    def section_schema(self):
        template = json.loads(TEMPLATE.read_text(encoding='utf-8'))
        # Extract the declarative row field contracts from the existing validator,
        # keeping the editor's nested templates aligned with the accepted parser.
        from vision_modules.ecu_reference import validation
        tree = ast.parse(Path(validation.__file__).read_text(encoding='utf-8'))
        rows = {}
        aliases = {'m': 'metadata', 'c': 'coordinate_systems', 'g': 'geometry', 'cl': 'connectors_landmarks', 'a': 'reference_assets', 'r': 'recognition_rules', 'l': 'localization_rules', 'pcb': 'pcb_definition', 'ph': 'photography_recipes', 't': 'thermal_recipes', 'w': 'inspection_workflows', 'p': 'validation_policies', 'pr': 'provenance_release'}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_rows' and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)): continue
            target = node.args[0]
            if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                section = aliases.get(target.value.id) if isinstance(target.value, ast.Name) else None
                if isinstance(target.value, ast.Subscript) and isinstance(target.value.slice, ast.Constant): section = target.value.slice.value
                if isinstance(target.value, ast.Name) and target.value.id == 'd' and target.slice.value == 'physical_states':
                    section = 'physical_states'
                if section in template: rows.setdefault(section, {})[target.slice.value] = {field: None for field in node.args[1].value.split()}
        rows.setdefault('photography_recipes', {})['views'] = {'view_id': None, 'roi_refs': [], 'camera_goal': {'frame': 'ecu_local', 'translation_mm': None, 'quaternion_xyzw': None}, 'aim_point_mm': None, 'working_distance_range_mm': None, 'required_capabilities': [], 'quality_policy_ref': None, 'required': False, 'source_id': None}
        return {'sections': [{'name': k, 'fields': copy.deepcopy(v), 'field_templates': rows.get(k, {})} for k, v in template.items()], 'template': template, 'enums': {'status': ['DRAFT', 'REVIEW_READY', 'APPROVED'], 'editable_status': ['DRAFT'], 'scope': list(SCOPES), 'source_status': ['FIELD_NOTE', 'MEASURED', 'VERIFIED'], 'recognition_method': ['rgb_landmark', 'rgbd_landmark', 'depth_geometry', 'visual_marking'], 'localization_method': ['rgbd_pose', 'depth_geometry', 'landmark_registration'], 'thermal_mode': ['relative_intensity', 'radiometric']}}

    def ingest_reference_image(self, data):
        if not isinstance(data, bytes): raise ValueError('image bytes required')
        with self.store.transaction(): return self.store.put_asset(data)

    def read_reference_image(self, sha):
        return self.store.get_asset(sha)


LibraryService = ECULibraryService
