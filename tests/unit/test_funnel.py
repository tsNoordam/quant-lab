"""Idea funnel (project 4, step F1): card schema, hard stops, append-only register, budget.

Spec: research/specs/funnel/requirements.md.
"""

from __future__ import annotations

import json

import pytest

from quant_lab.funnel.cards import card_text, load_cards, parse_card
from quant_lab.funnel.kill import FAIL, PASS, UNKNOWN, load_profile, screen
from quant_lab.funnel.registry import (
    CARDS_DIR,
    LOG_FILE,
    LogError,
    append,
    build_index,
    counted_tests,
    read_log,
    replay,
    t_hurdle,
)
from quant_lab.funnel.schema import EVIDENCE_FIELDS, Card, Field

PROFILE = load_profile()


def make_card(**over) -> Card:
    """A card that passes every hard stop; override fields to break one rule at a time."""
    base = {
        "mechanism": Field("flow", "ASSUMPTION", "reason"),
        "instruments": Field("ZN", "OWN-TEST", where="r.md"),
        "entry_rule": Field("short 5d before", "OWN-TEST", where="r.md"),
        "exit_rule": Field("cover at close", "OWN-TEST", where="r.md"),
        "holding_period": Field("5d", "OWN-TEST", where="r.md"),
        "gross_effect_bps_per_trade": Field(10.0, "OWN-TEST", where="r.md"),
        "cost_bps_round_trip": Field(2.0, "OWN-TEST", where="r.md"),
        "events_per_year": Field(24, "OWN-TEST", where="r.md"),
        "sample": Field("2010-2026", "OWN-TEST", where="r.md"),
        "data_source": Field("Databento", "OWN-TEST", where="r.md"),
        "data_cost_usd": Field(38, "OWN-TEST", where="r.md"),
        "requires_print": Field(False, "OWN-TEST", where="r.md"),
        "post_publication_evidence": Field(True, "OWN-TEST", where="r.md"),
    }
    market = over.pop("market_class", "cme_futures")
    print_type = over.pop("print_type", None)
    base.update(over)
    return Card("Q9999", "test idea", market, "paper", "ref", "2013", base, print_type)


def results(card):
    verdict, res, _ = screen(card, PROFILE)
    return verdict, {r.rule.split()[0]: r for r in res}


# ------------------------------------------------------------------ schema
def test_field_validation_refuses_invented_values():
    assert Field("x", "SOURCE", "quote", "p. 3").problems("m") == []
    assert Field("x", "SOURCE").problems("m")  # a source claim needs quote and where
    assert Field("x", "MISSING").problems("m")  # value without evidence
    assert Field(None, "OWN-TEST", where="r.md").problems("m")  # label without value
    assert Field("x", "ASSUMPTION").problems("m")  # assumption needs its reasoning
    assert Field("x", "GUESS").problems("m")
    assert Field("ten", "OWN-TEST", where="r").problems("gross_effect_bps_per_trade")


def test_card_round_trip():
    c = make_card()
    again = parse_card(card_text(c))
    assert again.fields == {n: c.f(n) for n in EVIDENCE_FIELDS}
    assert again.problems() == []


def test_requires_print_needs_a_named_print():
    c = make_card(requires_print=Field(True, "OWN-TEST", where="r.md"))
    assert any("print_type" in p for p in c.problems())


# ------------------------------------------------------------------ hard stops
def test_all_pass():
    verdict, r = results(make_card())
    assert verdict == PASS and all(x.result == PASS for x in r.values())


def test_k1_no_rules_in_source_fails_missing_is_unknown():
    assert results(make_card(entry_rule=Field(None, "NOT-IN-SOURCE")))[1]["K1"].result == FAIL
    assert results(make_card(entry_rule=Field()))[1]["K1"].result == UNKNOWN


def test_k2_data_budget():
    assert (
        results(make_card(data_cost_usd=Field(500, "ASSUMPTION", "quote")))[1]["K2"].result == FAIL
    )
    assert results(make_card(data_cost_usd=Field()))[1]["K2"].result == UNKNOWN
    assert results(make_card(data_source=Field(None, "NOT-IN-SOURCE")))[1]["K2"].result == FAIL


def test_k3_market_must_be_traded():
    r = results(make_card(market_class="other"))[1]["K3"]
    assert r.result == FAIL and r.reason == "not_tradable"
    assert results(make_card(market_class="polymarket"))[1]["K3"].result == PASS


def test_k4_cost_ratio_and_profile_default():
    # London: 1.24 bps gross vs 2.6 bps cost
    r = results(
        make_card(
            gross_effect_bps_per_trade=Field(1.24, "OWN-TEST", where="r"),
            cost_bps_round_trip=Field(2.6, "OWN-TEST", where="r"),
        )
    )[1]["K4"]
    assert r.result == FAIL and r.reason == "cost_ratio"
    # no cost on the card -> profile default for the market class (1.5 bps for futures)
    r = results(
        make_card(
            gross_effect_bps_per_trade=Field(4.4, "OWN-TEST", where="r"),
            cost_bps_round_trip=Field(),
        )
    )[1]["K4"]
    assert r.result == FAIL and "profile default" in r.detail
    r = results(
        make_card(
            gross_effect_bps_per_trade=Field(4.6, "OWN-TEST", where="r"),
            cost_bps_round_trip=Field(),
        )
    )[1]["K4"]
    assert r.result == PASS
    r = results(make_card(gross_effect_bps_per_trade=Field(None, "NOT-IN-SOURCE")))[1]["K4"]
    assert r.result == FAIL and r.reason == "no_effect_size"


def test_k5_events_per_year():
    r = results(make_card(events_per_year=Field(1, "OWN-TEST", where="r")))[1]["K5"]
    assert r.result == FAIL and r.reason == "too_few_events"


def test_k6_print_access():
    fix = make_card(
        requires_print=Field(True, "OWN-TEST", where="r"), print_type="wm_reuters_4pm_fix"
    )
    assert results(fix)[1]["K6"].result == FAIL
    moc = make_card(
        requires_print=Field(True, "OWN-TEST", where="r"), print_type="stock_closing_auction"
    )
    assert results(moc)[1]["K6"].result == PASS


def test_verdict_fail_beats_unknown():
    c = make_card(entry_rule=Field(), market_class="other")
    assert screen(c, PROFILE)[0] == FAIL
    assert screen(make_card(entry_rule=Field()), PROFILE)[0] == UNKNOWN


# ------------------------------------------------------------------ register
@pytest.fixture
def log(tmp_path):
    return tmp_path / "log.jsonl"


def _inbox(log, idea="Q1"):
    append({"idea": idea, "type": "status", "to": "inbox", "actor": "human"}, log)


def test_first_status_must_be_inbox(log):
    with pytest.raises(LogError):
        append({"idea": "Q1", "type": "status", "to": "hypothesis", "actor": "human"}, log)


def test_illegal_transition_and_terminal(log):
    _inbox(log)
    with pytest.raises(LogError):
        append({"idea": "Q1", "type": "status", "to": "candidate", "actor": "human"}, log)
    append(
        {
            "idea": "Q1",
            "type": "status",
            "to": "rejected_screen",
            "reason": "cost_ratio",
            "actor": "human",
        },
        log,
    )
    with pytest.raises(LogError):
        append({"idea": "Q1", "type": "status", "to": "inbox", "actor": "human"}, log)


def test_rejection_needs_a_reason(log):
    _inbox(log)
    with pytest.raises(LogError):
        append({"idea": "Q1", "type": "status", "to": "rejected_screen", "actor": "human"}, log)


def test_judge_may_not_change_status_or_record_tests(log):
    _inbox(log)
    with pytest.raises(LogError):
        append({"idea": "Q1", "type": "status", "to": "needs_info", "actor": "judge"}, log)
    with pytest.raises(LogError):
        append(
            {"idea": "Q1", "type": "test", "kind": "screen", "verdict": "pass", "actor": "judge"},
            log,
        )


def test_hypothesis_needs_screen_pass_or_human_override(log):
    _inbox(log)
    with pytest.raises(LogError):
        append({"idea": "Q1", "type": "status", "to": "hypothesis", "actor": "human"}, log)
    append(
        {"idea": "Q1", "type": "test", "kind": "screen", "verdict": "fail", "actor": "code"}, log
    )
    with pytest.raises(LogError):
        append(
            {"idea": "Q1", "type": "status", "to": "hypothesis", "actor": "code", "override": "x"},
            log,
        )
    append(
        {
            "idea": "Q1",
            "type": "status",
            "to": "hypothesis",
            "actor": "human",
            "override": "accepted knowingly",
        },
        log,
    )


def test_code_cannot_promote_past_hypothesis(log):
    _inbox(log)
    append(
        {"idea": "Q1", "type": "test", "kind": "screen", "verdict": "pass", "actor": "code"}, log
    )
    append({"idea": "Q1", "type": "status", "to": "hypothesis", "actor": "code"}, log)
    with pytest.raises(LogError):
        append({"idea": "Q1", "type": "status", "to": "quick_test", "actor": "code"}, log)


def test_promotion_needs_a_passed_test_with_spec(log):
    _inbox(log)
    append(
        {"idea": "Q1", "type": "test", "kind": "screen", "verdict": "pass", "actor": "code"}, log
    )
    append({"idea": "Q1", "type": "status", "to": "hypothesis", "actor": "code"}, log)
    append({"idea": "Q1", "type": "status", "to": "quick_test", "actor": "human"}, log)
    with pytest.raises(LogError):
        append({"idea": "Q1", "type": "status", "to": "full_research", "actor": "human"}, log)
    with pytest.raises(LogError):  # counted test without a pre-written spec
        append(
            {"idea": "Q1", "type": "test", "kind": "quick", "verdict": "pass", "actor": "human"},
            log,
        )
    append(
        {
            "idea": "Q1",
            "type": "test",
            "kind": "quick",
            "verdict": "pass",
            "actor": "human",
            "spec": "spec.md",
        },
        log,
    )
    append({"idea": "Q1", "type": "status", "to": "full_research", "actor": "human"}, log)


def test_append_never_rewrites(log):
    _inbox(log)
    before = log.read_text(encoding="utf-8")
    append({"idea": "Q1", "type": "note", "actor": "human", "note": "x"}, log)
    assert log.read_text(encoding="utf-8").startswith(before)
    with pytest.raises(LogError):  # a refused entry leaves the file untouched
        append({"idea": "Q1", "type": "status", "to": "live", "actor": "human"}, log)
    assert len(read_log(log)) == 2


def test_t_hurdle():
    assert t_hurdle(1) == 3.0
    assert t_hurdle(100) == pytest.approx(3.48, abs=0.01)
    assert t_hurdle(1000) > t_hurdle(100)


# ------------------------------------------------------------------ the seeded register
def test_seeded_register_is_valid_and_complete():
    cards = load_cards(CARDS_DIR)
    assert all(c.problems() == [] for c in cards.values())
    states = replay(read_log(LOG_FILE))
    assert set(states) == set(cards)


def test_seeded_register_known_outcomes():
    """Golden outcomes of the ideas judged before the funnel existed."""
    states = replay(read_log(LOG_FILE))
    expect = {
        "Q0002": "rejected_screen",
        "Q0003": "rejected_screen",
        "Q0004": "rejected_screen",
        "Q0005": "candidate",
        "Q0007": "rejected_screen",
        "Q0008": "rejected_screen",
        "Q0009": "rejected_screen",
        "Q0010": "rejected_screen",
        "Q0006": "needs_info",
    }
    for idea, status in expect.items():
        assert states[idea].status == status, idea
    reasons = {
        e["idea"]: e.get("reason")
        for e in read_log(LOG_FILE)
        if e["type"] == "status" and e["to"] == "rejected_screen"
    }
    assert reasons["Q0002"] == "cost_ratio" and reasons["Q0008"] == "no_rules"
    assert reasons["Q0009"] == "too_few_events" and reasons["Q0007"] == "no_effect_size"
    # every rejection's current screen still reproduces from the card
    cards = load_cards(CARDS_DIR)
    for idea in reasons:
        assert screen(cards[idea], PROFILE)[0] == FAIL, idea


def test_log_lines_are_valid_json_and_counted_tests(tmp_path):
    entries = read_log(LOG_FILE)
    assert all(json.dumps(e) for e in entries)
    assert counted_tests(entries) >= 7
    db = build_index(db_path=tmp_path / "idx.sqlite")
    assert db.exists()
