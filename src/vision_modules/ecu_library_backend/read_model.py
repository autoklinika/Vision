"""Closed, immutable read views of an explicitly supplied ECU library owner.

The view contains catalog declarations and unsigned reference drafts. It never
loads assets, initializes a data root, evaluates station readiness, or publishes
a reference release. A section's row count describes declared structure only;
``NOT_EVALUATED`` never means complete, reviewed, or ready for execution.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import time
import unicodedata

from .service import ECULibraryService
from .storage import DraftReadUnavailable, SavedRevision
from .basic_profile import STATES

LibraryReadUnavailable = DraftReadUnavailable
MAX_CATALOG_RECORDS = 256
MAX_STATE_ROWS = 128
MAX_WORKFLOW_ROWS = 128
MAX_CONNECTORS = 64
MAX_DISPLAY_NAME = 160
_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z', re.ASCII)
_SCOPES = frozenset({'browse_and_select', 'verify_identity', 'localize',
                     'photo_inspection', 'thermal_relative', 'thermal_radiometric'})

# Only explicit row collections are counted. Scalar and mixed scalar sections
# deliberately use None, rather than inventing a completeness calculation.
SECTION_ROWS = (
    ('metadata', None),
    ('identity', None),
    ('physical_states', ('physical_states',)),
    ('coordinate_systems', ('state_transforms',)),
    ('geometry', ('per_physical_state',)),
    ('connectors_landmarks', ('connectors', 'landmarks')),
    ('reference_assets', ('assets',)),
    ('recognition_rules', ('features_to_check',)),
    ('localization_rules', None),
    ('pcb_definition', ('boards', 'regions_of_interest')),
    ('photography_recipes', ('recipes',)),
    ('thermal_recipes', ('recipes',)),
    ('inspection_workflows', ('recipes',)),
    ('validation_policies', ('policies', 'readiness_by_scope_and_physical_state')),
    ('provenance_release', ('measurement_sources', 'calibration_dependencies', 'asset_hashes')),
)


@dataclass(frozen=True)
class CatalogSummary:
    profile_id: str
    family: str
    variant: str
    revision: str
    display_name: str
    status: str
    readiness: str = 'NOT_READY'
    reason_code: str = 'CATALOG_ONLY'


@dataclass(frozen=True)
class CatalogConnector:
    connector_id: str
    color: str


@dataclass(frozen=True)
class CatalogDetail:
    summary: CatalogSummary
    connectors: tuple[CatalogConnector, ...]
    field_note_count: int
    field_notes_verified: bool
    envelope_present: bool


@dataclass(frozen=True)
class ProfileSummary:
    profile_id: str
    family: str
    variant: str
    revision: str
    display_name: str
    status: str
    etag: str
    readiness: str = 'NOT_READY'
    reason_code: str = 'UNSIGNED_DRAFT'
    lifecycle: str = 'ACTIVE'
    search_terms: str = ''
    search_complete: bool = True
    release_digest: str | None = None
    simplified: bool = False


@dataclass(frozen=True)
class SectionSummary:
    name: str
    row_count: int | None
    status: str = 'NOT_EVALUATED'


@dataclass(frozen=True)
class PhysicalStateSummary:
    state_id: str
    display_name: str
    declared_verified: bool


@dataclass(frozen=True)
class WorkflowSummary:
    recipe_id: str
    state_id: str
    scope: str


@dataclass(frozen=True)
class ProfileDetail:
    summary: ProfileSummary
    sections: tuple[SectionSummary, ...]
    physical_states: tuple[PhysicalStateSummary, ...]
    workflows: tuple[WorkflowSummary, ...]
    history: tuple[SavedRevision, ...]


@dataclass(frozen=True)
class LibrarySnapshot:
    view_id: str
    captured_at: float
    catalog: tuple[CatalogDetail, ...]
    profiles: tuple[ProfileDetail, ...]


def _identifier(value):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise LibraryReadUnavailable('LIBRARY_INCONSISTENT')
    return value


def _display_name(value):
    # Names are the only allowed free-text values. Unexpected labels reject
    # the complete view instead of truncating or exporting private paths.
    if (not isinstance(value, str) or not value.strip()
            or len(value) > MAX_DISPLAY_NAME or '/' in value or '\\' in value
            or any(unicodedata.category(c).startswith('C') for c in value)):
        raise LibraryReadUnavailable('LIBRARY_INCONSISTENT')
    return value


def _catalog_detail(record):
    if record.status not in ('DRAFT', 'READY_FOR_REVIEW', 'APPROVED'):
        raise LibraryReadUnavailable('LIBRARY_INCONSISTENT')
    if len(record.connectors) > MAX_CONNECTORS:
        raise LibraryReadUnavailable('LIBRARY_LIMIT_EXCEEDED')
    summary = CatalogSummary(*(_identifier(value) for value in
        (record.profile_id, record.family, record.variant, record.revision)),
        _display_name(record.declared_type), record.status)
    connectors = []
    for connector in record.connectors:
        if connector.color not in ('black', 'gray', 'other'):
            raise LibraryReadUnavailable('LIBRARY_INCONSISTENT')
        connectors.append(CatalogConnector(_identifier(connector.connector_id), connector.color))
    return CatalogDetail(summary, tuple(connectors), len(record.field_notes),
                         False, record.envelope is not None)


def identity_search_terms(document):
    identity = document['identity']
    values = ([identity['manufacturer']] if identity['manufacturer'] else []) + list(identity['manufacturer_part_numbers']) + list(identity['oem_part_numbers'])
    # The existing 50-row / 128 KiB report budget is retained. Legacy
    # records with overlong identity fields remain readable; incomplete
    # indexing is explicit, never silently claimed to cover every term.
    terms = []
    complete = True
    for value in values:
        if any(unicodedata.category(c).startswith('C') for c in value):
            complete = False
            continue
        next_value = ' '.join(terms + [value])
        if len(json.dumps(next_value,ensure_ascii=True)) > 1024:
            complete = False
            continue
        terms.append(value)
    return ' '.join(terms), complete


def _profile_detail(snapshot):
    document = snapshot.profile.data
    metadata = document['metadata']
    terms, complete = identity_search_terms(document)
    summary = ProfileSummary(*(_identifier(metadata[k]) for k in
        ('profile_id', 'family_id', 'variant_id', 'profile_revision')),
        _display_name(metadata['display_name']),
        metadata['status'], snapshot.etag, lifecycle=snapshot.lifecycle, search_terms=terms, search_complete=complete, release_digest=snapshot.release_digest, simplified=snapshot.declaration is not None)
    states = document['physical_states']
    workflows = document['inspection_workflows']['recipes']
    if len(states) > MAX_STATE_ROWS or len(workflows) > MAX_WORKFLOW_ROWS:
        raise LibraryReadUnavailable('LIBRARY_LIMIT_EXCEEDED')
    state_rows = tuple(PhysicalStateSummary(
        _identifier(row['state_id']),
        _display_name(row['display_name']), row['verified'])
        for row in states)
    if snapshot.declaration is not None:
        state_rows=tuple(PhysicalStateSummary(s["stateId"],STATES[s["stateId"]],False)
                         for s in snapshot.declaration["states"])
    recipe_rows = []
    for row in workflows:
        if row['approval_scope'] not in _SCOPES:
            raise LibraryReadUnavailable('LIBRARY_INCONSISTENT')
        recipe_rows.append(WorkflowSummary(_identifier(row['recipe_id']),
            _identifier(row['state_id']), row['approval_scope']))
    sections = []
    for name, collections in SECTION_ROWS:
        if collections is None:
            count = None
        elif name == 'physical_states':
            count = len(states)
        else:
            count = sum(len(document[name][collection]) for collection in collections)
        sections.append(SectionSummary(name, count))
    return ProfileDetail(summary, tuple(sections), state_rows,
                         tuple(recipe_rows), snapshot.history)


class LibraryReadModel:
    """Project an existing backend; construction never creates a service/store."""
    def __init__(self, service):
        if not isinstance(service, ECULibraryService):
            raise ValueError('an existing ECU library service is required')
        self._service = service

    def _catalog(self):
        # ECUCatalog is an append-only in-memory registry loaded by the owner.
        # Check its size before list_records() would materialize every record.
        registry = self._service.catalog
        if len(registry._records) > MAX_CATALOG_RECORDS:
            raise LibraryReadUnavailable('LIBRARY_LIMIT_EXCEEDED')
        records = registry.list_records()
        if len(records) > MAX_CATALOG_RECORDS:
            raise LibraryReadUnavailable('LIBRARY_LIMIT_EXCEEDED')
        return tuple(_catalog_detail(record) for record in records)

    def capture(self):
        try:
            catalog = self._catalog()
            drafts = self._service.store.read_snapshot()
            # Appends to the separate catalog owner during draft extraction
            # invalidate the entire view; partial mixed captures never escape.
            if catalog != self._catalog():
                raise LibraryReadUnavailable('LIBRARY_BUSY')
            profiles = tuple(_profile_detail(snapshot) for snapshot in drafts)
            captured_at = time.time()
            if not math.isfinite(captured_at):
                raise LibraryReadUnavailable('LIBRARY_INCONSISTENT')
            content = json.dumps({'catalog': [asdict(row) for row in catalog],
                                  'profiles': [asdict(row) for row in profiles]},
                sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
            digest = hashlib.sha256(b'vision-library-read-v1\0' + content.encode('ascii')).hexdigest()
            return LibrarySnapshot(digest, captured_at, catalog, profiles)
        except LibraryReadUnavailable:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
            raise LibraryReadUnavailable('LIBRARY_UNAVAILABLE') from exc
