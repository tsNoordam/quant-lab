"""Idea funnel command line (spec: research/specs/funnel/requirements.md).

uv run python -m quant_lab.funnel new --title "..." --market fx_cfd --source paper --ref URL
uv run python -m quant_lab.funnel screen Q0012            # hard stops K1-K6, moves the status
uv run python -m quant_lab.funnel screen Q0012 --record-only
uv run python -m quant_lab.funnel move Q0012 hypothesis --note "..." [--override "reason"]
uv run python -m quant_lab.funnel move Q0012 rejected_full --reason decayed --note "..."
uv run python -m quant_lab.funnel test Q0012 --kind quick --verdict fail --spec FILE --result FILE
uv run python -m quant_lab.funnel note Q0012 "free text"
uv run python -m quant_lab.funnel list [--status hypothesis]
uv run python -m quant_lab.funnel show Q0012
uv run python -m quant_lab.funnel status                   # counts, overrides, test budget
uv run python -m quant_lab.funnel check                    # validate every card and the log
uv run python -m quant_lab.funnel index                    # rebuild the SQLite index
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from .cards import load_card, load_cards, new_card, save_card
from .kill import FAIL, PASS, cost_used, load_profile, screen
from .registry import (
    CARDS_DIR,
    LogError,
    append,
    build_index,
    counted_tests,
    read_log,
    replay,
    t_hurdle,
)
from .schema import EVIDENCE_FIELDS, MARKET_CLASSES, REJECT_REASONS, SOURCE_TYPES, STATUSES


def _next_id() -> str:
    ids = [int(p.stem[1:]) for p in CARDS_DIR.glob("Q*.md") if p.stem[1:].isdigit()]
    return f"Q{(max(ids) + 1) if ids else 1:04d}"


def cmd_new(a) -> None:
    cid = _next_id()
    card = new_card(cid, a.title, a.market, a.source, a.ref, a.published, a.note or "")
    path = save_card(card, CARDS_DIR)
    append(
        {
            "idea": cid,
            "type": "status",
            "to": "inbox",
            "stage": "phenomenon",
            "actor": "human",
            "note": "new idea",
        }
    )
    print(
        f"{cid} aangemaakt: {path}\nVul de velden in (elk met label en bewijs) en draai daarna: "
        f"uv run python -m quant_lab.funnel screen {cid}"
    )


def cmd_screen(a) -> None:
    card = load_card(CARDS_DIR / f"{a.id}.md")
    problems = card.problems()
    if problems:
        sys.exit("De kaart is ongeldig, eerst oplossen:\n- " + "\n- ".join(problems))
    verdict, results, flags = screen(card, load_profile())
    for r in results:
        print(f"  {r.result:7s} {r.rule:14s} {r.detail}")
    for f in flags:
        print(f"  FLAG    {f}")
    v = {"PASS": "pass", "FAIL": "fail", "UNKNOWN": "inconclusive"}[verdict]
    detail = "; ".join(f"{r.rule}: {r.result}" for r in results)
    append(
        {
            "idea": a.id,
            "type": "test",
            "kind": "screen",
            "verdict": v,
            "actor": "code",
            "note": detail + ("; flags: " + " | ".join(flags) if flags else ""),
        }
    )
    print(f"\nOordeel: {verdict}")
    if a.record_only:
        return
    states = replay(read_log())
    cur = states[a.id].status
    if cur not in ("inbox", "needs_info"):
        print(f"(status {cur} blijft staan: screen verplaatst alleen vanuit inbox/needs_info)")
        return
    if verdict == FAIL:
        reason = next(r.reason for r in results if r.result == FAIL)
        append(
            {
                "idea": a.id,
                "type": "status",
                "to": "rejected_screen",
                "reason": reason,
                "actor": "code",
                "note": detail,
            }
        )
        print(f"-> rejected_screen ({reason})")
    elif verdict == PASS:
        append(
            {
                "idea": a.id,
                "type": "status",
                "to": "hypothesis",
                "stage": "hypothesis",
                "actor": "code",
                "note": "all hard stops passed",
            }
        )
        print("-> hypothesis")
    else:
        append(
            {"idea": a.id, "type": "status", "to": "needs_info", "actor": "code", "note": detail}
        )
        print("-> needs_info")


def cmd_move(a) -> None:
    e = {"idea": a.id, "type": "status", "to": a.status, "actor": "human", "note": a.note or ""}
    if a.reason:
        e["reason"] = a.reason
    if a.stage:
        e["stage"] = a.stage
    if a.override:
        e["override"] = a.override
    append(e)
    print(f"{a.id} -> {a.status}")


def cmd_test(a) -> None:
    e = {
        "idea": a.id,
        "type": "test",
        "kind": a.kind,
        "verdict": a.verdict,
        "actor": "human",
        "note": a.note or "",
    }
    if a.spec:
        e["spec"] = a.spec
    if a.result:
        e["result"] = a.result
    if a.t is not None:
        e["t_stat"] = a.t
    append(e)
    entries = read_log()
    n = counted_tests(entries)
    print(f"test vastgelegd. Getelde tests: {n}; drempel voor de volgende: t > {t_hurdle(n):.2f}")


def cmd_note(a) -> None:
    append({"idea": a.id, "type": "note", "actor": "human", "note": a.text})
    print("notitie vastgelegd")


def cmd_list(a) -> None:
    cards = load_cards(CARDS_DIR)
    states = replay(read_log())
    for cid, c in cards.items():
        s = states.get(cid)
        status = s.status if s else "-"
        if a.status and status != a.status:
            continue
        print(
            f"{cid}  {status:16s} {(s.stage if s and s.stage else '-'):18s} "
            f"{c.market_class:12s} {c.title}"
        )


def cmd_show(a) -> None:
    card = load_card(CARDS_DIR / f"{a.id}.md")
    st = replay(read_log()).get(a.id)
    print(
        f"{card.id}  {card.title}\n  markt: {card.market_class} | bron: {card.source_type} "
        f"{card.source_ref} ({card.published})\n  status: {st.status if st else '-'} | "
        f"stadium: {st.stage if st and st.stage else '-'}"
    )
    for n in EVIDENCE_FIELDS:
        f = card.f(n)
        print(f"  {n:28s} {f.label:13s} {'' if f.value is None else f.value}")
    cost, how = cost_used(card, load_profile())
    print(f"  kosten gebruikt in K4: {cost:g} bps ({how})")
    if st:
        print("  geschiedenis:")
        for e in st.events:
            what = (
                e.get("to") or f"{e.get('kind')} {e.get('verdict')}"
                if e["type"] != "note"
                else "notitie"
            )
            extra = f" [override: {e['override']}]" if e.get("override") else ""
            note = e.get("note", "")[:90]
            print(f"    {e['ts'][:10]} {e['actor']:5s} {e['type']:6s} {what}{extra}  {note}")


def cmd_status(a) -> None:
    entries = read_log()
    states = replay(entries)
    counts = Counter(s.status for s in states.values())
    print("Ideeën per status:")
    for st in STATUSES:
        if counts.get(st):
            print(f"  {st:16s} {counts[st]}")
    overrides = [e for e in entries if e.get("override")]
    print(f"\nOverrides door de gebruiker: {len(overrides)}")
    for e in overrides:
        print(f"  {e['idea']} -> {e.get('to')}: {e['override']}")
    n = counted_tests(entries)
    print(
        f"\nGetelde tests (quick/full/demo): {n}; een nieuw resultaat moet t > "
        f"{t_hurdle(n, load_profile().get('t_floor', 3.0)):.2f} halen"
    )


def cmd_check(a) -> None:
    cards = load_cards(CARDS_DIR)
    bad = {cid: c.problems() for cid, c in cards.items() if c.problems()}
    states = replay(read_log())
    orphans = sorted(set(states) - set(cards))
    no_log = sorted(set(cards) - set(states))
    for cid, p in bad.items():
        print(f"{cid}:\n  - " + "\n  - ".join(p))
    if orphans:
        print(f"log zonder kaart: {orphans}")
    if no_log:
        print(f"kaart zonder log: {no_log}")
    if bad or orphans or no_log:
        sys.exit(1)
    print(f"OK: {len(cards)} kaarten, {len(read_log())} logregels")


def cmd_index(a) -> None:
    print(f"index: {build_index()}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        prog="python -m quant_lab.funnel",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--title", required=True)
    n.add_argument("--market", required=True, choices=MARKET_CLASSES)
    n.add_argument("--source", required=True, choices=SOURCE_TYPES)
    n.add_argument("--ref", required=True)
    n.add_argument("--published")
    n.add_argument("--note")
    n.set_defaults(func=cmd_new)
    s = sub.add_parser("screen")
    s.add_argument("id")
    s.add_argument("--record-only", action="store_true", help="record the screen, do not move")
    s.set_defaults(func=cmd_screen)
    m = sub.add_parser("move")
    m.add_argument("id")
    m.add_argument("status", choices=STATUSES)
    m.add_argument("--reason", choices=sorted(REJECT_REASONS))
    m.add_argument("--stage")
    m.add_argument("--note")
    m.add_argument("--override", help="explicit reason for overriding a hard stop")
    m.set_defaults(func=cmd_move)
    t = sub.add_parser("test")
    t.add_argument("id")
    t.add_argument("--kind", required=True, choices=("quick", "full", "demo"))
    t.add_argument("--verdict", required=True, choices=("pass", "fail", "inconclusive"))
    t.add_argument("--spec", help="spec file written before the test ran")
    t.add_argument("--result")
    t.add_argument("--t", type=float, help="headline t-stat")
    t.add_argument("--note")
    t.set_defaults(func=cmd_test)
    o = sub.add_parser("note")
    o.add_argument("id")
    o.add_argument("text")
    o.set_defaults(func=cmd_note)
    li = sub.add_parser("list")
    li.add_argument("--status", choices=STATUSES)
    li.set_defaults(func=cmd_list)
    sh = sub.add_parser("show")
    sh.add_argument("id")
    sh.set_defaults(func=cmd_show)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("index").set_defaults(func=cmd_index)
    a = p.parse_args(argv)
    try:
        a.func(a)
    except LogError as e:
        sys.exit(f"Geweigerd: {e}")


if __name__ == "__main__":
    main()
