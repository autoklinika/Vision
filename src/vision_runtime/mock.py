"""Inert sensor port: records requests and produces no receipts."""
from dataclasses import dataclass, field
from vision_core.ports import Request


@dataclass
class MockSensorPort:
    requests: list[Request] = field(default_factory=list)

    def observe(self, request: Request) -> None:
        if not isinstance(request, Request):
            raise ValueError('Core request required')
        self.requests.append(request)
