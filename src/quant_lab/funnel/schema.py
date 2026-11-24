"""Idea card schema, labels, statuses, stages and allowed transitions.

Spec: research/specs/funnel/requirements.md. The card says what an idea is; the event log
says what happened to it (status and stage live only in the log).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ------------------------------------------------------------------ evidence labels
SOURCE = "SOURCE"  # stated in the source: needs a verbatim quote and where
OWN_TEST = "OWN-TEST"  # measured by our own test: where = report file
ASSUMPTION = "ASSUMPTION"  # our explicit assumption: quote = the reasoning
NOT_IN_SOURCE = "NOT-IN-SOURCE"  # the source was checked and does not give it
MISSING = "MISSING"  # not filled in yet
LABELS = (SOURCE, OWN_TEST, ASSUMPTION, NOT_IN_SOURCE, MISSING)
EMPTY_LABELS = (NOT_IN_SOURCE, MISSING)

MARKET_CLASSES = ("fx_cfd", "cme_futures", "stocks_etfs", "crypto", "polymarket", "other")
SOURCE_TYPES = ("paper", "tip", "repo", "feed", "course", "video", "own_research")

# ------------------------------------------------------------------ lifecycle
STATUSES = (
    "inbox",
    "needs_info",
    "rejected_screen",
    "hypothesis",
    "quick_test",
    "rejected_quick",
    "full_research",
    "rejected_full",
    "candidate",
    "demo",
    "rejected_live",
    "live",
    "parked",
    "duplicate",
)
TERMINAL = ("rejected_screen", "rejected_quick", "rejected_full", "rejected_live", "duplicate")

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "inbox": ("needs_info", "rejected_screen", "hypothesis", "duplicate", "parked"),
    "needs_info": ("rejected_screen", "hypothesis", "parked", "duplicate"),
    "hypothesis": ("quick_test", "full_research", "parked", "rejected_screen"),
    "quick_test": ("full_research", "rejected_quick", "parked"),
    "full_research": ("candidate", "rejected_full", "parked"),
    "candidate": ("demo", "rejected_full", "parked"),
    "demo": ("live", "rejected_live", "parked"),
    "live": ("rejected_live", "parked"),
    "parked": ("inbox", "needs_info", "hypothesis"),
}

STAGES = (
    "phenomenon",
    "hypothesis",
    "historical_anomaly",
    "robust_anomaly",
    "executable_edge",
    "live_validated",
)

REJECT_REASONS = {
    "no_rules": "no trading rule can be derived (K1)",
    "no_data": "no data can be had within the budget (K2)",
    "not_tradable": "not a market the user trades (K3)",
    "cost_ratio": "gross effect below the cost multiple (K4)",
    "too_few_events": "too few events or trades per year (K5)",
    "single_print": "needs a fill at a benchmark print the user cannot get (K6)",
    "no_effect_size": "the source gives no effect size (K4)",
    "failed_replication": "the effect does not reproduce in our data",
    "decayed": "the effect is gone or below costs after publication",
    "failed_oos": "fails out of sample",
    "insufficient_evidence": "test inconclusive at the current significance bar",
    "duplicate": "same idea as another card",
    "other": "other (explained in the note)",
}

ACTORS = ("human", "code", "judge")
CODE_MAY = {
    "inbox": ("needs_info", "rejected_screen", "hypothesis"),
    "needs_info": ("needs_info", "rejected_screen", "hypothesis"),
}
TEST_KINDS = ("screen", "quick", "full", "demo")
COUNTED_KINDS = ("quick", "full", "demo")  # screens do not look at returns
VERDICTS = ("pass", "fail", "inconclusive")
# promotion -> test kind that must have passed
PROMOTION_NEEDS = {
    ("quick_test", "full_research"): "quick",
    ("full_research", "candidate"): "full",
    ("demo", "live"): "demo",
}

# ------------------------------------------------------------------ card fields
# Fields of the card (front matter) that carry labelled evidence.
EVIDENCE_FIELDS = (
    "mechanism",
    "instruments",
    "entry_rule",
    "exit_rule",
    "holding_period",
    "gross_effect_bps_per_trade",
    "cost_bps_round_trip",
    "events_per_year",
    "sample",
    "data_source",
    "data_cost_usd",
    "requires_print",
    "post_publication_evidence",
)
NUMERIC_FIELDS = (
    "gross_effect_bps_per_trade",
    "cost_bps_round_trip",
    "events_per_year",
    "data_cost_usd",
)


@dataclass(frozen=True)
class Field:
    value: Any = None
    label: str = MISSING
    quote: str | None = None
    where: str | None = None

    @classmethod
    def from_dict(cls, d: Any) -> Field:
        if d is None:
            return cls()
        if not isinstance(d, dict):
            raise ValueError(f"field must be a mapping with value/label/quote/where, got {d!r}")
        return cls(d.get("value"), d.get("label", MISSING), d.get("quote"), d.get("where"))

    @property
    def known(self) -> bool:
        return self.label not in EMPTY_LABELS and self.value is not None

    def problems(self, name: str) -> list[str]:
        """Why this field is invalid (empty list = valid). Nothing may be invented."""
        p = []
        if self.label not in LABELS:
            return [f"{name}: unknown label {self.label!r}"]
        if self.label in EMPTY_LABELS:
            if self.value is not None:
                p.append(f"{name}: label {self.label} but a value is given")
            return p
        if self.value is None:
            p.append(f"{name}: label {self.label} needs a value")
        if self.label == SOURCE and not (self.quote and self.where):
            p.append(f"{name}: SOURCE needs a verbatim quote and where it is")
        if self.label == OWN_TEST and not self.where:
            p.append(f"{name}: OWN-TEST needs the report file in 'where'")
        if self.label == ASSUMPTION and not self.quote:
            p.append(f"{name}: ASSUMPTION needs its reasoning in 'quote'")
        if name in NUMERIC_FIELDS and self.value is not None:
            try:
                float(self.value)
            except (TypeError, ValueError):
                p.append(f"{name}: value must be a number")
        return p


@dataclass(frozen=True)
class Card:
    id: str
    title: str
    market_class: str
    source_type: str
    source_ref: str
    published: str | None
    fields: dict[str, Field]
    print_type: str | None = None
    tags: tuple[str, ...] = ()
    body: str = ""

    def f(self, name: str) -> Field:
        return self.fields.get(name, Field())

    def problems(self) -> list[str]:
        p = []
        if not self.id or not self.title:
            p.append("id and title are required")
        if self.market_class not in MARKET_CLASSES:
            p.append(f"market_class must be one of {MARKET_CLASSES}")
        if self.source_type not in SOURCE_TYPES:
            p.append(f"source_type must be one of {SOURCE_TYPES}")
        unknown = set(self.fields) - set(EVIDENCE_FIELDS)
        if unknown:
            p.append(f"unknown fields: {sorted(unknown)}")
        for name in EVIDENCE_FIELDS:
            p += self.f(name).problems(name)
        rp = self.f("requires_print")
        if rp.known and rp.value is True and not self.print_type:
            p.append("requires_print is true: name the print in print_type")
        return p
