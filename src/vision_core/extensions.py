"""Explicit, declarative extension contracts; no discovery or code execution."""
from dataclasses import dataclass
import re
from .models import Context

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z', re.ASCII)

def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('invalid ASCII identifier')
    return value

def _ids(values):
    if isinstance(values, (str, bytes)):
        raise ValueError('identifier collection required')
    result = tuple(values)
    for value in result:
        _id(value)
    if len(set(result)) != len(result):
        raise ValueError('duplicate identifier')
    return result

@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    version: str
    profile_kind: str
    capabilities: frozenset[str]
    approved: bool
    stage_ids: tuple[str, ...]
    required_stage_ids: tuple[str, ...] = ()  # subset mandatory for selected module

    archive_required: bool = False

    def __post_init__(self):
        if type(self.archive_required) is not bool: raise ValueError('invalid archive requirement')
        for value in (self.module_id, self.version, self.profile_kind): _id(value)
        object.__setattr__(self, 'capabilities', frozenset(_ids(self.capabilities)))
        object.__setattr__(self, 'stage_ids', _ids(self.stage_ids))
        object.__setattr__(self, 'required_stage_ids', _ids(self.required_stage_ids))
        if self.approved is not True or not self.capabilities or not self.stage_ids:
            raise ValueError('approved module, capabilities and stages required')
        if not set(self.required_stage_ids).issubset(self.stage_ids):
            raise ValueError('required stages not in permitted module stages')

@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    dependencies: tuple[str, ...]
    checks: frozenset[str]
    module_id: str | None = None

    def __post_init__(self):
        _id(self.stage_id)
        object.__setattr__(self, 'dependencies', _ids(self.dependencies))
        object.__setattr__(self, 'checks', frozenset(_ids(self.checks)))
        if self.module_id is not None: _id(self.module_id)
        if self.stage_id in self.dependencies or not self.checks:
            raise ValueError('self dependency or missing checks')

@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    version: str
    stages: tuple[StageSpec, ...]
    required_module_ids: tuple[str, ...]

    def __post_init__(self):
        _id(self.scenario_id); _id(self.version)
        object.__setattr__(self, 'stages', tuple(self.stages))
        object.__setattr__(self, 'required_module_ids', _ids(self.required_module_ids))
        if len(self.stages) > 256:
            raise ValueError('too many stages')
        if not self.stages or any(not isinstance(s, StageSpec) for s in self.stages):
            raise ValueError('stage specifications required')
        ids = [s.stage_id for s in self.stages]
        if len(ids) != len(set(ids)): raise ValueError('duplicate stage')
        seen = set()
        for stage in self.stages:
            if not set(stage.dependencies) <= seen:
                raise ValueError('unknown, cyclic or out-of-order dependency')
            seen.add(stage.stage_id)

class ModuleRegistry:
    def __init__(self):
        self._modules = {}
        self._frozen = False
    def register(self, module):
        if self._frozen: raise ValueError('registry frozen')
        if not isinstance(module, ModuleSpec): raise TypeError('ModuleSpec required')
        if module.module_id in self._modules or any(m.profile_kind == module.profile_kind for m in self._modules.values()):
            raise ValueError('duplicate module or profile kind')
        self._modules[module.module_id] = module
    def resolve(self, module_id):
        try: return self._modules[module_id]
        except KeyError as exc: raise ValueError('unknown module') from exc
    def freeze(self):
        self._frozen = True
        return self

@dataclass(frozen=True)
class ModuleReceipt:
    session_id: str
    step_id: str
    request_id: str
    module_id: str
    module_version: str
    profile_revision: str
    context: Context
    timestamp: float
    payload_sha256: str
    reference: str
    terminal_success: bool
