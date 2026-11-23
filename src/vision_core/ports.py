"""Adapter boundaries. Mocks only record requests; they never generate success."""
from dataclasses import dataclass, field
from typing import Protocol
from .models import Context


@dataclass(frozen=True)
class Request:
    step_id: str
    request_id: str
    context: Context


class SensorPort(Protocol):
    def observe(self, request: Request) -> None: ...


class ScenePort(Protocol):
    def update_scene(self, request: Request) -> None: ...


class MotionPort(Protocol):
    def plan(self, request: Request) -> None: ...
    def execute(self, request: Request) -> None: ...


class CapturePort(Protocol):
    def capture(self, request: Request) -> None: ...


@dataclass
class InertMock:
    requests: list[Request] = field(default_factory=list)

    def observe(self, request: Request) -> None: self.requests.append(request)
    def update_scene(self, request: Request) -> None: self.requests.append(request)
    def plan(self, request: Request) -> None: self.requests.append(request)
    def execute(self, request: Request) -> None: self.requests.append(request)
    def capture(self, request: Request) -> None: self.requests.append(request)
