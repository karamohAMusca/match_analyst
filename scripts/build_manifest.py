"""Regenerate corpus/manifest.json from the cards' front matter.

Run it after adding or editing a card:

    python -m scripts.build_manifest
"""

from __future__ import annotations

import datetime as dt
import json

from src.config import MANIFEST_PATH
from src.rag.corpus import load_cards

OPTIONAL_FIELDS = ("themes", "coach", "coaches", "formations", "phase", "winner", "date", "note")

HEADER = {
    "schema_version": "2.0",
    "release_id": "match_analyst_cards_v2",
    "project": "Match Analyst AI",
    "description": (
        "Catalogue of the RAG corpus. Every document listed here is ingested. Short single-topic cards "
        "(about 1.5-3k characters) with typed metadata. "
        "document_id is the key used by retriever metadata, citations and eval/gold_set.json."
    ),
    "categories": {
        "match_case": "a recent final (2022-2026): how the winner won, with numbers",
        "game_situation": "an in-game or preparation problem: options, risks, real cases",
        "coach_profile": "one file per coach, merging every source that describes that coach",
        "thesis_note": "a concept from the theses, not tied to a match moment",
        "glossary": "definitions of metrics and formations",
    },
    "fields": {
        "origin_type": "derived = written by the project from the cited sources",
        "reliability": (
            "project_synthesis_cited = every fact cites a source with page; "
            "sections marked 'interpretazione del progetto' are the project's reading"
        ),
        "sources": "upstream documents (thesis + pages, Wikipedia revision, FIFA/StatsBomb data) or other card ids",
    },
    "upstream_not_ingested": {
        "references/theses/": "FIGC theses (PDF), not redistributed",
        "references/wikipedia/": "CC BY-SA 4.0 extracts with revision ids",
        "references/data/statsbomb/": "StatsBomb Open Data (no redistribution)",
        "references/data/fifa/": "FIFA public match reports",
        "references/SOURCES.md": "provenance, licences and card-writing rules",
    },
}


def build_manifest() -> dict:
    cards = load_cards()
    ids = [c.document_id for c in cards]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise SystemExit(f"duplicate document_id: {sorted(duplicates)}")

    documents = []
    for card in cards:
        m = card.metadata
        doc = {
            "document_id": m["document_id"],
            "title": m["title"],
            "category": m["category"],
            "origin_type": m["origin_type"],
            "modality": m["modality"],
            "reliability": m["reliability"],
            "language": "it",
            "sources": m["sources"],
            "file_records": [
                {"path": card.relative_path, "sha256": card.sha256, "bytes": len(card.raw)}
            ],
        }
        doc.update({k: m[k] for k in OPTIONAL_FIELDS if m.get(k)})
        documents.append(doc)

    return {
        **HEADER,
        "generated": dt.date.today().isoformat(),
        "stats": {"documents": len(cards), "total_chars": sum(len(c.raw.decode("utf-8")) for c in cards)},
        "documents": documents,
    }


def main() -> None:
    manifest = build_manifest()
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {manifest['stats']['documents']} documents, {manifest['stats']['total_chars']} chars")


if __name__ == "__main__":
    main()
