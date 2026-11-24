"""Hard stops K1-K6 and soft flags: deterministic code, never an LLM.

Each rule returns PASS, FAIL or UNKNOWN. Any FAIL rejects an idea; any UNKNOWN keeps it in
needs_info. Spec: research/specs/funnel/requirements.md, settings: conf/funnel/profile.yaml.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from .schema import NOT_IN_SOURCE, Card

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
PROFILE = Path(__file__).resolve().parents[3] / "conf" / "funnel" / "profile.yaml"


def load_profile(path: Path = PROFILE) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RuleResult:
    rule: str
    result: str
    detail: str
    reason: str | None = None  # reject reason code when FAIL


def _num(card: Card, name: str) -> float | None:
    f = card.f(name)
    return float(f.value) if f.known else None


def _absent(card: Card, name: str) -> bool:
    return card.f(name).label == NOT_IN_SOURCE


def k1_rules(card: Card, profile: dict) -> RuleResult:
    names = ("entry_rule", "exit_rule", "instruments")
    if any(_absent(card, n) for n in names):
        missing = [n for n in names if _absent(card, n)]
        return RuleResult("K1 rules", FAIL, f"not in the source: {', '.join(missing)}", "no_rules")
    if all(card.f(n).known for n in names):
        return RuleResult("K1 rules", PASS, "entry, exit and instrument given")
    missing = [n for n in names if not card.f(n).known]
    return RuleResult("K1 rules", UNKNOWN, f"not filled in: {', '.join(missing)}")


def k2_data(card: Card, profile: dict) -> RuleResult:
    budget = float(profile["data_budget_usd"])
    if _absent(card, "data_source"):
        return RuleResult("K2 data", FAIL, "no data source can be had", "no_data")
    if not card.f("data_source").known:
        return RuleResult("K2 data", UNKNOWN, "data source not filled in")
    cost = _num(card, "data_cost_usd")
    if cost is None:
        return RuleResult(
            "K2 data", UNKNOWN, f"data source {card.f('data_source').value!r}, cost unknown"
        )
    if cost > budget:
        return RuleResult(
            "K2 data", FAIL, f"data costs ${cost:,.0f} > budget ${budget:,.0f}", "no_data"
        )
    return RuleResult(
        "K2 data", PASS, f"{card.f('data_source').value} (${cost:,.0f} <= ${budget:,.0f})"
    )


def k3_tradable(card: Card, profile: dict) -> RuleResult:
    if card.market_class in profile["markets"]:
        return RuleResult("K3 tradable", PASS, f"{card.market_class} is traded")
    return RuleResult(
        "K3 tradable", FAIL, f"{card.market_class} is not in the user's markets", "not_tradable"
    )


def cost_used(card: Card, profile: dict) -> tuple[float, str]:
    c = _num(card, "cost_bps_round_trip")
    if c is not None:
        return c, f"card ({card.f('cost_bps_round_trip').label})"
    d = profile["default_cost_bps_round_trip"]
    return float(d.get(card.market_class, d["other"])), "profile default [ASSUMPTION]"


def k4_cost_ratio(card: Card, profile: dict) -> RuleResult:
    mult = float(profile["cost_multiple"])
    if _absent(card, "gross_effect_bps_per_trade"):
        return RuleResult(
            "K4 cost ratio", FAIL, "the source gives no effect size", "no_effect_size"
        )
    gross = _num(card, "gross_effect_bps_per_trade")
    if gross is None:
        return RuleResult("K4 cost ratio", UNKNOWN, "gross effect not filled in")
    cost, how = cost_used(card, profile)
    ratio = gross / cost if cost > 0 else float("inf")
    detail = f"gross {gross:g} bps / cost {cost:g} bps ({how}) = {ratio:.2f}x, need >= {mult:g}x"
    if ratio >= mult:
        return RuleResult("K4 cost ratio", PASS, detail)
    return RuleResult("K4 cost ratio", FAIL, detail, "cost_ratio")


def k5_events(card: Card, profile: dict) -> RuleResult:
    need = float(profile["min_events_per_year"])
    n = _num(card, "events_per_year")
    if n is None:
        if _absent(card, "events_per_year"):
            return RuleResult("K5 events", UNKNOWN, "the source gives no frequency")
        return RuleResult("K5 events", UNKNOWN, "events per year not filled in")
    if n >= need:
        return RuleResult("K5 events", PASS, f"{n:g} per year >= {need:g}")
    return RuleResult("K5 events", FAIL, f"{n:g} per year < {need:g}", "too_few_events")


def k6_print(card: Card, profile: dict) -> RuleResult:
    f = card.f("requires_print")
    if not f.known:
        return RuleResult("K6 print", UNKNOWN, "not filled in whether a benchmark print is needed")
    if f.value is not True:
        return RuleResult("K6 print", PASS, "no fill at a benchmark print needed")
    if card.print_type in profile.get("print_access", []):
        return RuleResult("K6 print", PASS, f"needs {card.print_type}, which the user can access")
    return RuleResult(
        "K6 print", FAIL, f"needs a fill at {card.print_type}, not accessible", "single_print"
    )


RULES = (k1_rules, k2_data, k3_tradable, k4_cost_ratio, k5_events, k6_print)


def screen(card: Card, profile: dict | None = None) -> tuple[str, list[RuleResult], list[str]]:
    """Return (verdict, rule results, soft flags). verdict: FAIL, UNKNOWN or PASS."""
    profile = profile or load_profile()
    results = [r(card, profile) for r in RULES]
    verdict = (
        FAIL
        if any(r.result == FAIL for r in results)
        else (UNKNOWN if any(r.result == UNKNOWN for r in results) else PASS)
    )
    return verdict, results, soft_flags(card, profile)


def soft_flags(card: Card, profile: dict, today: date | None = None) -> list[str]:
    today = today or date.today()
    flags = []
    if card.published:
        try:
            year = int(str(card.published)[:4])
        except ValueError:
            year = None
        post = card.f("post_publication_evidence")
        if (
            year
            and today.year - year > profile["flag_publication_age_years"]
            and not (post.known and post.value is True)
        ):
            flags.append(f"published {year}: no evidence after publication yet")
    s = card.f("sample")
    if s.known:
        yrs = [int(x) for x in re.findall(r"(19\d{2}|20\d{2})", str(s.value))]
        if len(yrs) >= 2 and max(yrs) - min(yrs) + 1 < profile["flag_min_sample_years"]:
            flags.append(f"sample {s.value}: shorter than {profile['flag_min_sample_years']} years")
    return flags
