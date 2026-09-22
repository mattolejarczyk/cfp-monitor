"""The verification-method registry is the one vocabulary for how a fact was verified. Every
method is well-formed and categorised, so the data can be sliced by source, match, or cost.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import verify_methods as vm  # noqa: E402

SOURCES = {"plain-http", "real-browser", "grounded-search", "upstream"}
MATCHES = {"date-context-regex", "llm-verbatim", "none"}
COSTS = {"free", "llm", "grounded"}


def test_every_method_is_well_formed_and_categorised():
    assert vm.METHODS, "the registry is not empty"
    for mid, m in vm.METHODS.items():
        assert m.id == mid
        assert m.source in SOURCES and m.match in MATCHES and m.cost in COSTS
        assert m.label and m.note                      # every method explains itself


def test_the_named_constants_are_registered():
    for mid in (vm.FETCH_PLAIN, vm.BROWSER_LADDER, vm.LLM_VERBATIM, vm.GROUNDED, vm.UPSTREAM):
        assert vm.is_method(mid)


def test_cost_buckets_partition_the_registry():
    assert vm.FETCH_PLAIN in vm.FREE_METHODS and vm.BROWSER_LADDER in vm.FREE_METHODS
    assert vm.GROUNDED in vm.GROUNDED_METHODS
    assert set(vm.FREE_METHODS).isdisjoint(vm.GROUNDED_METHODS)


def test_describe_returns_the_method_or_none():
    assert vm.describe(vm.GROUNDED).cost == "grounded"
    assert vm.describe("nope") is None
