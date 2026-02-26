#!/usr/bin/env python3
"""
Leonne's Daily Post — Article Merger
Takes the main scraper articles.json and merges in supplemental article
files (e.g., from AP email parser). Deduplicates across sources using
title fingerprints and title similarity.

Usage:
    python3 merge_articles.py articles.json ap_articles.json -o articles.json

The first positional argument is the primary file; additional files are
merged in. The output overwrites the primary file (or a separate -o path).
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone


def fingerprint(title):
    """Matches scraper.py fingerprint function."""
    normalized = re.sub(r"[^\w\s]", "", title.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def titles_similar(t1, t2, threshold=0.6):
    """Check if two titles are similar enough to be duplicates."""
    words1 = set(re.sub(r"[^\w\s]", "", t1.lower()).split())
    words2 = set(re.sub(r"[^\w\s]", "", t2.lower()).split())
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2)
    shorter = min(len(words1), len(words2))
    return (overlap / shorter) >= threshold


def main():
    parser = argparse.ArgumentParser(
        description="Merge article JSON files for Leonne's Daily Post"
    )
    parser.add_argument(
        "files", nargs="+",
        help="JSON files to merge (first is primary)"
    )
    parser.add_argument(
        "-o", "--output", required=True,
        help="Output file path"
    )
    args = parser.parse_args()

    # Load primary file
    with open(args.files[0], 'r') as f:
        primary = json.load(f)

    all_articles = list(primary.get("articles", []))
    print(f"  Primary: {len(all_articles)} articles", file=sys.stderr)

    # Load and merge supplemental files
    for filepath in args.files[1:]:
        try:
            with open(filepath, 'r') as f:
                supplemental = json.load(f)
            supp_articles = supplemental.get("articles", [])
            print(f"  Supplemental ({filepath}): {len(supp_articles)} articles",
                  file=sys.stderr)

            # Deduplicate against existing articles
            added = 0
            for new_article in supp_articles:
                new_title = new_article.get("title", "")
                new_fp = new_article.get("fingerprint", fingerprint(new_title))

                is_dup = False
                for existing in all_articles:
                    existing_fp = existing.get("fingerprint", "")
                    if new_fp == existing_fp:
                        is_dup = True
                        break
                    if titles_similar(new_title, existing.get("title", "")):
                        is_dup = True
                        break

                if not is_dup:
                    all_articles.append(new_article)
                    added += 1

            print(f"    Added {added} new articles (skipped {len(supp_articles) - added} duplicates)",
                  file=sys.stderr)

        except Exception as e:
            print(f"  ⚠ Error loading {filepath}: {e}", file=sys.stderr)
            continue

    # Rebuild output with updated article list
    primary["articles"] = all_articles
    primary["article_count"] = len(all_articles)
    primary["merged_at"] = datetime.now(timezone.utc).isoformat()

    with open(args.output, 'w') as f:
        json.dump(primary, f, indent=2, ensure_ascii=False)

    print(f"  Merged total: {len(all_articles)} articles → {args.output}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
