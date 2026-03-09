#!/usr/bin/env python3
"""
Generate Academic Pages publication markdown files from a Google Scholar profile.

This is a custom helper script for Academic Pages-style sites. It fetches a
Google Scholar profile using the `scholarly` package and writes one markdown
file per publication into `_publications/`.

Example:
    python scholar.py --author-id s9IOtoMAAAAJ
    python scholar.py --author-id s9IOtoMAAAAJ --outdir _publications --max-pubs 50
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from scholarly import scholarly
except Exception as exc:  # pragma: no cover
    print(
        "Error: the 'scholarly' package is required.\n"
        "Install it with: pip install scholarly\n"
        f"Original import error: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)


def slugify(text: str) -> str:
    """Create a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text or "untitled"


def clean_text(text: Optional[str]) -> str:
    """Normalize whitespace and escape quotes for YAML strings."""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def first_author_surname(authors: str) -> str:
    """Best-effort extraction of first author's surname for citation text."""
    if not authors:
        return "Author"
    first = authors.split(" and ")[0].split(",")[0].strip()
    parts = first.split()
    return parts[-1] if parts else first


def infer_category(pub_type: str, venue: str) -> str:
    text = f"{pub_type} {venue}".lower()
    conference_keywords = [
        "conference",
        "proceedings",
        "symposium",
        "workshop",
        "congress",
    ]
    if any(k in text for k in conference_keywords):
        return "conferences"
    return "manuscripts"


def build_markdown(pub: Dict[str, Any]) -> str:
    bib = pub.get("bib", {}) or {}

    title = clean_text(bib.get("title")) or "Untitled"
    authors = clean_text(bib.get("author"))
    venue = clean_text(
        bib.get("journal")
        or bib.get("conference")
        or bib.get("booktitle")
        or bib.get("publisher")
        or "Unknown venue"
    )
    year_text = clean_text(bib.get("pub_year") or bib.get("year") or "")
    year = year_text if year_text.isdigit() else "1900"
    month = "01"
    day = "01"
    pub_type = clean_text(bib.get("pub_type"))
    abstract = clean_text(pub.get("abstract") or bib.get("abstract"))
    url = clean_text(pub.get("pub_url"))
    citations = pub.get("num_citations", 0)
    category = infer_category(pub_type, venue)
    permalink = f"/publication/{slugify(title)}"
    file_stub = f"{year}-{slugify(title)}"

    if not abstract:
        abstract = f"Publication in {venue}."

    citation_text = authors if authors else first_author_surname(authors)
    yaml_lines = [
        "---",
        f'title: "{title.replace(chr(34), chr(92) + chr(34))}"',
        "collection: publications",
        f"category: {category}",
        f"permalink: {permalink}",
        f'excerpt: "{abstract.replace(chr(34), chr(92) + chr(34))}"',
        f"date: {year}-{month}-{day}",
        f'venue: "{venue.replace(chr(34), chr(92) + chr(34))}"',
        f'paperurl: "{url}"' if url else 'paperurl: ""',
        (
            f'citation: "{citation_text.replace(chr(34), chr(92) + chr(34))}, '
            f'{title.replace(chr(34), chr(92) + chr(34))}, {venue.replace(chr(34), chr(92) + chr(34))}, {year}."'
        ),
        f"scholar_citations: {citations}",
        "---",
        "",
    ]

    body = []
    if authors:
        body.append(f"**Authors:** {authors}")
    body.append(f"**Venue:** {venue} ({year})")
    body.append(f"**Google Scholar citations:** {citations}")
    if url:
        body.append(f"**Link:** [Publisher / Google Scholar link]({url})")
    if abstract:
        body.extend(["", "## Abstract", "", abstract])

    return file_stub + ".md", "\n".join(yaml_lines + body) + "\n"


def fetch_publications(author_id: str, fill_limit: Optional[int] = None) -> List[Dict[str, Any]]:
    author = scholarly.search_author_id(author_id)
    if author is None:
        raise ValueError(f"Could not find Google Scholar author with id: {author_id}")

    sections = ["publications", "basics"]
    filled_author = scholarly.fill(author, sections=sections)

    pubs = filled_author.get("publications", []) or []
    results: List[Dict[str, Any]] = []

    for idx, pub in enumerate(pubs, start=1):
        try:
            filled_pub = scholarly.fill(pub)
            results.append(filled_pub)
        except Exception as exc:
            print(f"Warning: failed to fetch publication {idx}: {exc}", file=sys.stderr)
        if fill_limit is not None and len(results) >= fill_limit:
            break

    def year_key(p: Dict[str, Any]) -> int:
        bib = p.get("bib", {}) or {}
        y = str(bib.get("pub_year") or bib.get("year") or "0")
        return int(y) if y.isdigit() else 0

    results.sort(key=year_key, reverse=True)
    return results


def write_publications(pubs: Iterable[Dict[str, Any]], outdir: Path, overwrite: bool = False) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    count = 0

    for pub in pubs:
        filename, content = build_markdown(pub)
        path = outdir / filename
        if path.exists() and not overwrite:
            print(f"Skipping existing file: {path.name}")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")
        count += 1

    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Academic Pages markdown files from a Google Scholar profile."
    )
    parser.add_argument("--author-id", required=True, help="Google Scholar author id, e.g. s9IOtoMAAAAJ")
    parser.add_argument("--outdir", default="_publications", help="Output directory (default: _publications)")
    parser.add_argument("--max-pubs", type=int, default=None, help="Optional maximum number of publications to fetch")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite markdown files if they already exist",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)

    try:
        pubs = fetch_publications(args.author_id, fill_limit=args.max_pubs)
        if not pubs:
            print("No publications found.", file=sys.stderr)
            return 1
        written = write_publications(pubs, outdir, overwrite=args.overwrite)
        print(f"Done. Generated {written} markdown file(s) in {outdir}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
