"""Read and write idea cards: Markdown files with YAML front matter."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .schema import EVIDENCE_FIELDS, MISSING, Card, Field

FRONT = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def parse_card(text: str) -> Card:
    m = FRONT.match(text.replace("\r\n", "\n"))
    if not m:
        raise ValueError("card must start with a YAML front matter block between --- lines")
    meta = yaml.safe_load(m.group(1)) or {}
    fields = {k: Field.from_dict(v) for k, v in (meta.get("fields") or {}).items()}
    src = meta.get("source") or {}
    return Card(
        id=str(meta.get("id", "")),
        title=str(meta.get("title", "")),
        market_class=str(meta.get("market_class", "")),
        source_type=str(src.get("type", "")),
        source_ref=str(src.get("ref", "")),
        published=None if src.get("published") is None else str(src.get("published")),
        fields=fields,
        print_type=meta.get("print_type"),
        tags=tuple(meta.get("tags") or ()),
        body=m.group(2).strip(),
    )


def load_card(path: Path) -> Card:
    return parse_card(Path(path).read_text(encoding="utf-8"))


def load_cards(folder: Path) -> dict[str, Card]:
    cards = {}
    for p in sorted(Path(folder).glob("*.md")):
        c = load_card(p)
        if c.id in cards:
            raise ValueError(f"duplicate card id {c.id} in {p.name}")
        if p.stem != c.id:
            raise ValueError(f"{p.name}: file name must equal the card id {c.id}")
        cards[c.id] = c
    return cards


def card_text(card: Card) -> str:
    fields = {}
    for name in EVIDENCE_FIELDS:
        f = card.f(name)
        d = {"value": f.value, "label": f.label}
        if f.quote:
            d["quote"] = f.quote
        if f.where:
            d["where"] = f.where
        fields[name] = d
    meta = {
        "id": card.id,
        "title": card.title,
        "market_class": card.market_class,
        "source": {"type": card.source_type, "ref": card.source_ref, "published": card.published},
        "print_type": card.print_type,
        "tags": list(card.tags),
        "fields": fields,
    }
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=100)
    return f"---\n{front}---\n\n{card.body.strip()}\n"


def new_card(
    card_id: str,
    title: str,
    market_class: str,
    source_type: str,
    source_ref: str,
    published: str | None = None,
    note: str = "",
) -> Card:
    body = note or "Free text: the idea in your own words, links, open questions."
    return Card(
        card_id,
        title,
        market_class,
        source_type,
        source_ref,
        published,
        {n: Field(None, MISSING) for n in EVIDENCE_FIELDS},
        body=body,
    )


def save_card(card: Card, folder: Path) -> Path:
    path = Path(folder) / f"{card.id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card_text(card), encoding="utf-8", newline="\n")
    return path
