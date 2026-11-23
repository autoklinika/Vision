"""Neutral contracts for offline workflow coordination."""
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping
from types import MappingProxyType


class State(StrEnum):
    PENDING = 'PENDING'
    READY = 'READY'
    RUNNING = 'RUNNING'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    BLOCKED = 'BLOCKED'
    TIMED_OUT = 'TIMED_OUT'


@dataclass(frozen=True)
class Context:
    session_id: str
    profile_revisions: Mapping[str, str]
    scene_revision: str = ""
    observation_timestamp: float | None = None
    frame_id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "profile_revisions", MappingProxyType(dict(self.profile_revisions)))

    def to_dict(self):
        return {"session_id": self.session_id, "profile_revisions": dict(self.profile_revisions),
                "scene_revision": self.scene_revision, "observation_timestamp": self.observation_timestamp,
                "frame_id": self.frame_id}


@dataclass(frozen=True)
class Evidence:
    session_id: str
    step_id: str
    request_id: str
    context: Context
    timestamp: float
    quality: bool
    terminal_success: bool
    checks: frozenset[str]
    reference: str


@dataclass(frozen=True)
class Event:
    sequence: int
    session_id: str
    step_id: str
    request_id: str
    kind: str
    data: dict
    timestamp: float


class GateError(ValueError):
    """A transition or verified-evidence gate was denied."""
