"""Explicit in-memory registry; persistence and durable revision governance are external."""
from .models import ECURecord, canonical_json, record_sha256

class ECUCatalog:
    def __init__(self):
        self._records = {}
        self._ids = {}

    def register(self, record):
        if not isinstance(record, ECURecord): raise ValueError('record required')
        key = (record.family, record.variant, record.revision)
        encoded = canonical_json(record)
        prior = self._records.get(key)
        if prior and prior[1] != encoded: raise ValueError('revision already registered with different content')
        idkey = (record.profile_id, record.revision)
        if idkey in self._ids and self._ids[idkey] != key: raise ValueError('profile revision already registered')
        self._records[key] = (record, encoded, record_sha256(record))
        self._ids[idkey] = key

    def get(self, family, variant, revision):
        record, encoded, digest = self._records[(family, variant, revision)]
        if canonical_json(record) != encoded or record_sha256(record) != digest: raise ValueError('catalog record changed')
        return record

    def list_records(self, family=None):
        return tuple(self.get(*key) for key in sorted(self._records) if family is None or key[0] == family)

    def select(self, declaration):
        from .verification import Declaration
        if not isinstance(declaration, Declaration): raise ValueError('typed declaration required')
        return self.get(declaration.family, declaration.variant, declaration.revision)
