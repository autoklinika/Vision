"""Explicit reference registrations with immutable snapshots and exact selection."""
from .codec import canonical_json, content_sha256
from .models import ReferenceProfile

class ReferenceLibrary:
    def __init__(self): self._records = {}
    def register(self, profile):
        if not isinstance(profile, ReferenceProfile): raise ValueError('reference profile required')
        m = profile.data['metadata']; key = (m['family_id'], m['variant_id'], m['profile_revision'])
        if any(not isinstance(x, str) or not x for x in key): raise ValueError('complete key required')
        encoded = canonical_json(profile); digest = content_sha256(profile)
        if key in self._records and self._records[key][1:] != (encoded, digest): raise ValueError('revision already registered')
        self._records[key] = (profile, encoded, digest)
    def select(self, family_id, variant_id, profile_revision):
        try: profile, encoded, digest = self._records[(family_id, variant_id, profile_revision)]
        except KeyError as exc: raise ValueError('exact reference not registered') from exc
        if canonical_json(profile) != encoded or content_sha256(profile) != digest: raise ValueError('reference changed')
        return profile
    def list_profiles(self):
        return tuple(self.select(*key) for key in sorted(self._records))
    def preview(self, family_id, variant_id, profile_revision):
        p = self.select(family_id, variant_id, profile_revision); d = p.data
        return (d['metadata'], d['physical_states'], d['inspection_workflows']['recipes'])
