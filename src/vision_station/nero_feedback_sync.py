"""Bounded observation history for time-aligned MoveIt state evidence.

This is read-only evidence processing. No interpolation, extrapolation,
retiming, motion commands, or change to the live feedback age limit.
"""
from collections import deque
from .nero_manual import AGE, finite, vector7


class FeedbackHistory:
    def __init__(self, *, horizon, wall):
        if not finite(horizon) or not AGE < horizon <= .65:
            raise ValueError("bounded observation history required")
        self.wall = wall
        self.horizon = horizon
        self.samples = deque(maxlen=256)

    def add(self, stamp, q, gid):
        if not finite(stamp) or not 0 <= self.wall()-stamp <= AGE:
            raise ValueError("stale feedback")
        if not vector7(q) or type(gid) is not bytes or not any(gid):
            raise ValueError("invalid feedback")
        sample = (stamp, tuple(q), gid)
        if self.samples:
            last = self.samples[-1]
            if stamp < last[0] or (stamp == last[0] and sample != last):
                raise ValueError("conflicting feedback timestamp")
            if sample == last:
                return
        self.samples.append(sample)
        while self.samples and self.wall()-self.samples[0][0] > self.horizon:
            self.samples.popleft()

    def at(self, stamp, gid):
        # Both stamps are converted by the same ROS time conversion. Do
        # not match to the nearest state or manufacture a new timestamp.
        return next((row for row in reversed(self.samples)
                     if row[0] == stamp and row[2] == gid), None)

    def service_match(self, q, gid, *, earliest, latest, max_error, extra=None):
        """Match the state returned by an un-stamped service.

        A response must contain the same positions as a recent observed
        sample in the bounded request window, within the already
        configured comparison tolerance. It is not a timestamp proof:
        stamped PSM updates are independently required during changes.
        No extrapolation or adjustment of joint positions is performed.
        """
        if not vector7(q) or not finite(earliest) or not finite(latest) or earliest > latest:
            return None
        if not finite(max_error) or not 0 < max_error <= .01:
            return None
        rows = list(self.samples)
        if extra is not None:
            rows.append(extra)
        matching = [r for r in rows if r[2] == gid and earliest <= r[0] <= latest
                    and max(abs(x-y) for x,y in zip(r[1],q)) <= max_error]
        # Prefer the smallest spatial residual, then the newest equal
        # candidate. A matching configuration is not a fresh timestamp.
        return min(matching,key=lambda r:(max(abs(x-y) for x,y in zip(r[1],q)),-r[0]),default=None)
