"""Injected server authorization boundary; no built-in users, tokens or login."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Credentials:
    # Raw credentials are passed only to the trusted server-side authorizer.
    # They never enter reports, error bodies, logs or the journal.
    authorization: str | None = None
    cookie: str | None = None


@dataclass(frozen=True)
class ReadGrant:
    session_id: str
    scopes: frozenset[str]

    def __post_init__(self):
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("invalid grant")
        scopes = frozenset(self.scopes)
        if not scopes or not scopes <= {"session:read", "events:read"}:
            raise ValueError("invalid grant")
        object.__setattr__(self, "scopes", scopes)


Authorizer = Callable[[Credentials], ReadGrant | None]


@dataclass(frozen=True)
class LibraryReadGrant:
    """Library authority is independent of any specimen/session authority."""
    library_id: str
    scopes: frozenset[str]

    def __post_init__(self):
        if not isinstance(self.library_id, str) or not self.library_id:
            raise ValueError("invalid grant")
        scopes = frozenset(self.scopes)
        if scopes != frozenset({"library:read"}):
            raise ValueError("invalid grant")
        object.__setattr__(self, "scopes", scopes)


LibraryAuthorizer = Callable[[Credentials], LibraryReadGrant | None]


class AccessDenied(Exception):
    """No valid, appropriately scoped server-side grant."""


class ReportUnavailable(Exception):
    """No consistent report available; never expose an inner exception."""


class CursorRejected(Exception):
    """Cursor does not belong to this read view or journal interval."""
