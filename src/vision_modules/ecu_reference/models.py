"""Immutable reference profile snapshots, independent of inspection sessions."""
from dataclasses import dataclass
from types import MappingProxyType


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value):
    if isinstance(value, MappingProxyType):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True, init=False)
class ReferenceProfile:
    """A validated snapshot; construct through :func:`load_json`."""
    data: object

    def __init__(self, *args, **kwargs):
        raise TypeError('use load_json')

    @classmethod
    def _validated(cls, data):
        obj = object.__new__(cls)
        object.__setattr__(obj, 'data', freeze(data))
        return obj
