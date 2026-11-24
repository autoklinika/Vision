"""Synthetic-only fixtures using the real Workflow and Journal classes."""
from vision_core import Context, Evidence, ECUProfile, Journal, Profile, Workflow
from vision_core.profiles import PROFILE_KINDS
from vision_core.workflow import CHECKS

NOW = 1000.0
SESSION = "synthetic-api02"


def make_engine(journal):
    profiles = {k: Profile(k, k, "1", "r1", True, frozenset({"basic", "raw", "af", "depth"}),
                           frozenset({"basic"}), {"cal": "v1"}) for k in PROFILE_KINDS}
    profiles["ecu"] = ECUProfile("ecu", "synthetic", "1", "r1", True, {"basic"}, {"basic"},
                                 {"cal": "v1"}, "example", "a", (10, 20), 5,
                                 ((0, 0, 10, 20),), ((1, 2, 3),), (0.5,))
    context = Context(SESSION, {k: "r1" for k in PROFILE_KINDS}, "scene1", NOW, "synthetic_frame")
    return Workflow(journal, context, profiles, {"cal": "v1"}, {}, 10, lambda: NOW)


def populate(engine, acknowledgements=60):
    engine.start("S01", "synthetic-req-S01")
    engine.complete(Evidence(SESSION, "S01", "synthetic-req-S01", engine.context, NOW,
                             True, True, frozenset(CHECKS["S01"]), "synthetic-reference"))
    engine.start("S02", "synthetic-req-S02")
    for _ in range(acknowledgements):
        engine.ack("S02", "synthetic-req-S02")


def memory_fixture(acknowledgements=60):
    journal = Journal(":memory:")
    engine = make_engine(journal)
    populate(engine, acknowledgements)
    return journal, engine
