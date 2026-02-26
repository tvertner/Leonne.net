#!/usr/bin/env python3
"""
Leonne's Daily Post — RSS Feed Scraper
Pulls articles from curated RSS feeds, deduplicates, categorizes,
and outputs a structured JSON file for the editorial pass.

Usage:
    python3 scraper.py                    # Output to stdout
    python3 scraper.py -o articles.json   # Output to file
    python3 scraper.py --hours 48         # Look back 48 hours instead of 24
"""

import argparse
import json
import re
import hashlib
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from html import unescape

try:
    import feedparser
except ImportError:
    print("feedparser not installed. Run: pip3 install feedparser")
    sys.exit(1)

# ---------------------------------------------------------------------------
# FEED CONFIGURATION
# ---------------------------------------------------------------------------
# Each feed has a URL, a default category, and an optional source name override.
# Categories: world, us, science, tech, environment, local, libraries, longform
#
# To add or remove feeds, just edit this list.
# ---------------------------------------------------------------------------

FEEDS = [
    # ── WORLD NEWS ──────────────────────────────────────────────────────
    {
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "world",
        "source": "BBC News"
    },
    {
        "url": "https://feeds.npr.org/1004/rss.xml",
        "category": "world",
        "source": "NPR World"
    },

    # ── U.S. NEWS ───────────────────────────────────────────────────────
    {
        "url": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
        "category": "us",
        "source": "BBC U.S."
    },
    {
        "url": "https://feeds.npr.org/1014/rss.xml",
        "category": "us",
        "source": "NPR Politics"
    },
    {
        "url": "https://feeds.npr.org/1003/rss.xml",
        "category": "us",
        "source": "NPR U.S."
    },

    # ── SCIENCE ─────────────────────────────────────────────────────────
    {
        "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "category": "science",
        "source": "BBC Science"
    },
    {
        "url": "https://feeds.npr.org/1007/rss.xml",
        "category": "science",
        "source": "NPR Science"
    },
    {
        "url": "https://api.quantamagazine.org/feed/",
        "category": "science",
        "source": "Quanta Magazine"
    },
    {
        "url": "https://www.nature.com/nature.rss",
        "category": "science",
        "source": "Nature"
    },

    # ── TECHNOLOGY ──────────────────────────────────────────────────────
    {
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "category": "tech",
        "source": "Ars Technica"
    },
    {
        "url": "https://www.theverge.com/rss/index.xml",
        "category": "tech",
        "source": "The Verge"
    },
    {
        "url": "https://feeds.npr.org/1019/rss.xml",
        "category": "tech",
        "source": "NPR Technology"
    },
    {
        "url": "https://www.wired.com/feed/rss",
        "category": "tech",
        "source": "Wired"
    },

    # ── ENVIRONMENT ─────────────────────────────────────────────────────
    {
        "url": "https://grist.org/feed/",
        "category": "environment",
        "source": "Grist"
    },
    {
        "url": "https://insideclimatenews.org/feed/",
        "category": "environment",
        "source": "Inside Climate News"
    },
    {
        "url": "https://e360.yale.edu/feed.xml",
        "category": "environment",
        "source": "Yale E360"
    },

    # ── LOCAL (Omaha / Bellevue / Nebraska) ─────────────────────────────
    {
        "url": "https://www.ketv.com/topstories-rss",
        "category": "local",
        "source": "KETV Omaha"
    },
    {
        "url": "https://nebraskaexaminer.com/feed/",
        "category": "local",
        "source": "Nebraska Examiner"
    },
    {
        "url": "https://flatwaterfreepress.org/feed/",
        "category": "local",
        "source": "Flatwater Free Press"
    },

    # ── LIBRARIES & INFORMATION SCIENCE ─────────────────────────────────
    {
        "url": "https://americanlibrariesmagazine.org/feed/",
        "category": "libraries",
        "source": "American Libraries"
    },
    {
        "url": "https://lisnews.org/feed/",
        "category": "libraries",
        "source": "LISNews"
    },
    {
        "url": "https://librarian.net/feed/",
        "category": "libraries",
        "source": "librarian.net"
    },
    {
        "url": "https://librarytechnology.org/rss",
        "category": "libraries",
        "source": "Library Technology Guides"
    },

    # ── U.S. POLITICS & POLICY ──────────────────────────────────────────
    {
        "url": "https://thehill.com/homenews/feed/",
        "category": "us",
        "source": "The Hill"
    },
    {
        "url": "https://www.pbs.org/newshour/feeds/rss/headlines",
        "category": "us",
        "source": "PBS NewsHour"
    },

    # ── WORLD / INTERNATIONAL ───────────────────────────────────────────
    {
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "category": "world",
        "source": "Al Jazeera"
    },

    # ── LONG-FORM / INVESTIGATIVE ───────────────────────────────────────
    {
        "url": "https://www.theatlantic.com/feed/all/",
        "category": "longform",
        "source": "The Atlantic"
    },
    {
        "url": "https://www.newyorker.com/feed/everything",
        "category": "longform",
        "source": "The New Yorker"
    },
    {
        "url": "https://www.bellingcat.com/feed/",
        "category": "longform",
        "source": "Bellingcat"
    },
    {
        "url": "https://www.propublica.org/feeds/propublica/main",
        "category": "longform",
        "source": "ProPublica"
    },
    {
        "url": "https://www.foreignaffairs.com/rss.xml",
        "category": "longform",
        "source": "Foreign Affairs"
    },
    {
        "url": "https://foreignpolicy.com/feed/",
        "category": "longform",
        "source": "Foreign Policy"
    },
]

# Category display labels (used by the HTML template)
CATEGORY_LABELS = {
    "world": "World",
    "us": "U.S.",
    "science": "Science",
    "tech": "Tech",
    "environment": "Environment",
    "local": "Local",
    "libraries": "Libraries",
    "longform": "Long Read",
}


# ---------------------------------------------------------------------------
# CUSTOM SOURCE SCRAPERS (AP, Reuters, Lawfare)
# ---------------------------------------------------------------------------

def fetch_ap_articles(hours_back=24):
    """
    Fetch AP articles via Google News RSS proxy.
    The old S3 RSS mirror is unreliable, so we use Google News with
    allinurl:apnews.com to get recent AP articles. These supplement
    the IMAP email parser which provides editorially curated stories.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    articles = []

    when_hours = min(hours_back, 72)
    url = (
        f"https://news.google.com/rss/search?"
        f"q=when:{when_hours}h+allinurl:apnews.com"
        f"&ceid=US:en&hl=en-US&gl=US"
    )

    try:
        parsed = feedparser.parse(url)
        if not parsed.entries:
            print(f"⚠ AP: Google News proxy returned no entries", file=sys.stderr)
            return []

        for entry in parsed.entries:
            title = clean_html(getattr(entry, "title", ""))
            if not title:
                continue

            # Google News appends " - The Associated Press" or similar
            title = re.sub(r"\s*[-\u2013\u2014]\s*(?:The\s+)?Associated Press\s*$", "", title).strip()
            title = re.sub(r"\s*[-\u2013\u2014]\s*AP News\s*$", "", title).strip()

            if not title or len(title) < 15:
                continue

            pub_date = parse_date(entry)
            if pub_date and pub_date < cutoff:
                continue

            link = getattr(entry, "link", "")

            # Categorize based on URL path or headline keywords
            url_lower = link.lower()
            if '/science' in url_lower:
                category = 'science'
            elif '/technology' in url_lower:
                category = 'tech'
            elif '/entertainment' in url_lower or '/sports' in url_lower:
                category = 'us'
            else:
                category = guess_ap_category(title)

            excerpt = clean_html(getattr(entry, "summary", "") or "")
            excerpt = re.sub(r'<[^>]+>', '', excerpt).strip()

            articles.append({
                "title": title,
                "link": link,
                "source": "Associated Press",
                "category": category,
                "category_label": CATEGORY_LABELS.get(category, category),
                "excerpt": excerpt,
                "published": pub_date.isoformat() if pub_date else None,
                "fingerprint": fingerprint(title),
            })

    except Exception as e:
        print(f"⚠ Error fetching AP via Google News: {e}", file=sys.stderr)
        return []

    # Deduplicate
    seen_fps = set()
    unique = []
    for a in articles:
        if a["fingerprint"] not in seen_fps:
            seen_fps.add(a["fingerprint"])
            unique.append(a)
    articles = unique

    if articles:
        print(f"  AP: fetched {len(articles)} articles via Google News", file=sys.stderr)
    else:
        print(f"⚠ AP: no articles found", file=sys.stderr)

    return articles


def guess_ap_category(title):
    """Guess category for an AP article from its headline."""
    text = title.lower()
    science_kw = ['study finds', 'researchers', 'nasa', 'space', 'vaccine',
                  'medical', 'scientific', 'asteroid', 'telescope']
    tech_kw = ['ai ', 'artificial intelligence', 'cyber', 'tech ',
               'software', 'crypto', 'robot', 'data breach',
               'tesla', 'apple ', 'google ', 'microsoft']
    env_kw = ['climate', 'emission', 'wildfire', 'renewable', 'solar',
              'carbon', 'pollution', 'epa ']
    world_kw = ['ukraine', 'russia', 'china', 'nato', 'gaza', 'israel',
                'iran', 'north korea', 'europe', 'india', 'africa',
                'middle east', 'united nations', 'greenland']
    for kw in science_kw:
        if kw in text:
            return 'science'
    for kw in tech_kw:
        if kw in text:
            return 'tech'
    for kw in env_kw:
        if kw in text:
            return 'environment'
    for kw in world_kw:
        if kw in text:
            return 'world'
    return 'us'


def fetch_reuters_articles(hours_back=24):
    """
    Fetch Reuters articles via Google News RSS proxy.
    Reuters killed their own RSS feeds in 2020 and blocks sitemap scraping,
    so we use Google News with allinurl:reuters.com to get recent articles.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    articles = []

    # Google News RSS: fetch Reuters articles from the last 24h
    # The 'when' param only supports whole hours, cap at our lookback
    when_hours = min(hours_back, 72)
    url = (
        f"https://news.google.com/rss/search?"
        f"q=when:{when_hours}h+allinurl:reuters.com"
        f"&ceid=US:en&hl=en-US&gl=US"
    )

    try:
        parsed = feedparser.parse(url)
        if not parsed.entries:
            print(f"⚠ Reuters: Google News proxy returned no entries", file=sys.stderr)
            return []

        for entry in parsed.entries:
            title = clean_html(getattr(entry, "title", ""))
            if not title:
                continue

            # Google News appends " - Reuters" to titles; strip it
            title = re.sub(r"\s*[-–—]\s*Reuters\s*$", "", title).strip()

            if not title or len(title) < 15:
                continue

            pub_date = parse_date(entry)
            if pub_date and pub_date < cutoff:
                continue

            # Google News wraps the real URL in a redirect; the actual
            # Reuters link is in entry.link (Google redirects to it)
            link = getattr(entry, "link", "")

            # Try to get the real Reuters URL from the source element
            # Google News entries sometimes have the original URL
            if hasattr(entry, "source") and hasattr(entry.source, "href"):
                pass  # source.href is the publication, not the article

            # Categorize based on URL path or headline keywords
            url_lower = link.lower()
            if "/technology/" in url_lower:
                category = "tech"
            elif "/science/" in url_lower:
                category = "science"
            elif "/sustainability/" in url_lower or "/environment/" in url_lower:
                category = "environment"
            elif "/legal/" in url_lower:
                category = "us"
            elif any(s in url_lower for s in ("/world/us", "/us-")):
                category = "us"
            else:
                category = guess_reuters_category(title)

            excerpt = clean_html(getattr(entry, "summary", "") or "")
            # Google News summaries often contain HTML source attribution; clean it
            excerpt = re.sub(r'<[^>]+>', '', excerpt).strip()

            articles.append({
                "title": title,
                "link": link,
                "source": "Reuters",
                "category": category,
                "category_label": CATEGORY_LABELS.get(category, category),
                "excerpt": excerpt,
                "published": pub_date.isoformat() if pub_date else None,
                "fingerprint": fingerprint(title),
            })

    except Exception as e:
        print(f"⚠ Error fetching Reuters via Google News: {e}", file=sys.stderr)
        return []

    # Deduplicate
    seen_fps = set()
    unique = []
    for a in articles:
        if a["fingerprint"] not in seen_fps:
            seen_fps.add(a["fingerprint"])
            unique.append(a)
    articles = unique

    if articles:
        print(f"  Reuters: fetched {len(articles)} articles via Google News", file=sys.stderr)
    else:
        print(f"⚠ Reuters: no articles found", file=sys.stderr)

    return articles


def guess_reuters_category(title):
    """Guess category for a Reuters article from its headline."""
    text = title.lower()
    science_kw = ['study', 'researchers', 'nasa', 'space', 'vaccine',
                  'medical', 'clinical', 'asteroid', 'physicist']
    tech_kw = ['ai ', 'artificial intelligence', 'cyber', 'tech ',
               'software', 'crypto', 'robot', 'data breach', 'chip',
               'tesla', 'apple ', 'google ', 'microsoft']
    env_kw = ['climate', 'emission', 'wildfire', 'renewable', 'solar',
              'carbon', 'pollution', 'epa ']
    world_kw = ['ukraine', 'russia', 'china', 'nato', 'gaza', 'israel',
                'iran', 'north korea', 'europe', 'india', 'africa',
                'middle east', 'united nations']
    for kw in science_kw:
        if kw in text:
            return 'science'
    for kw in tech_kw:
        if kw in text:
            return 'tech'
    for kw in env_kw:
        if kw in text:
            return 'environment'
    for kw in world_kw:
        if kw in text:
            return 'world'
    return 'world'  # Reuters defaults to world news


def fetch_lawfare_weekly():
    """
    Fetch Lawfare's 'The Week That Was' if it was published today (Friday).
    URL pattern: https://www.lawfaremedia.org/article/the-week-that-was-M-D-YYYY
    Only includes if the URL actually responds (200 OK).
    """
    now = datetime.now(timezone.utc)

    # Only check on Fridays and Saturdays (in case pipeline runs late)
    if now.weekday() not in (4, 5):  # 4=Friday, 5=Saturday
        return []

    # Try this Friday's date (if today is Saturday, try yesterday)
    if now.weekday() == 5:  # Saturday
        friday = now - timedelta(days=1)
    else:
        friday = now

    # Lawfare URL format: the-week-that-was-M-D-YYYY (no zero-padding)
    month = friday.month
    day = friday.day
    year = friday.year
    url = f"https://www.lawfaremedia.org/article/the-week-that-was-{month}-{day}-{year}"

    # Check if the page exists
    try:
        req = urllib.request.Request(url, method="HEAD", headers={
            "User-Agent": "Mozilla/5.0 (compatible; LeonneBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                print(f"  Lawfare: weekly page not ready yet ({resp.status})", file=sys.stderr)
                return []
    except urllib.error.HTTPError as e:
        print(f"  Lawfare: weekly page not found ({e.code})", file=sys.stderr)
        return []
    except Exception as e:
        print(f"⚠ Lawfare: error checking weekly page: {e}", file=sys.stderr)
        return []

    date_str = friday.strftime("%B %d, %Y").replace(" 0", " ")
    print(f"  Lawfare: found weekly roundup for {date_str}", file=sys.stderr)

    return [{
        "title": f"The Week That Was — {date_str}",
        "link": url,
        "source": "Lawfare",
        "category": "longform",
        "category_label": "Long Read",
        "excerpt": "Lawfare's weekly roundup: a comprehensive summary of the week's national security law and policy coverage.",
        "published": friday.replace(hour=18, minute=0, second=0).isoformat(),
        "fingerprint": fingerprint(f"lawfare week that was {month} {day} {year}"),
    }]


# ---------------------------------------------------------------------------
# SCRAPING & PROCESSING
# ---------------------------------------------------------------------------

def clean_html(text):
    """Strip HTML tags and decode entities."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_excerpt(entry, max_chars=800):
    """Extract a usable excerpt from the feed entry."""
    # Try content:encoded first, then summary, then description
    content = ""
    if hasattr(entry, "content") and entry.content:
        content = entry.content[0].get("value", "")
    elif hasattr(entry, "summary"):
        content = entry.summary or ""
    elif hasattr(entry, "description"):
        content = entry.description or ""

    cleaned = clean_html(content)
    if len(cleaned) > max_chars:
        # Cut at last sentence boundary before max_chars
        truncated = cleaned[:max_chars]
        last_period = truncated.rfind(".")
        if last_period > max_chars // 2:
            cleaned = truncated[: last_period + 1]
        else:
            cleaned = truncated.rsplit(" ", 1)[0] + "…"

    return cleaned


def parse_date(entry):
    """Extract published date as a UTC datetime."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                from time import mktime
                dt = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
                return dt
            except (ValueError, OverflowError, OSError):
                continue
    return None


def fingerprint(title):
    """Create a simple fingerprint for deduplication."""
    # Normalize: lowercase, strip punctuation, collapse whitespace
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


def fetch_feeds(feeds, hours_back=24):
    """Fetch all feeds and return a list of article dicts."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    articles = []

    for feed_config in feeds:
        url = feed_config["url"]
        category = feed_config["category"]
        source = feed_config["source"]

        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"⚠ Error fetching {source}: {e}", file=sys.stderr)
            continue

        if not parsed.entries:
            print(f"⚠ No entries from {source}", file=sys.stderr)
            continue

        for entry in parsed.entries:
            title = clean_html(getattr(entry, "title", ""))
            if not title:
                continue

            pub_date = parse_date(entry)
            # If no date, include it (better to have it than miss it)
            if pub_date and pub_date < cutoff:
                continue

            link = getattr(entry, "link", "")
            excerpt = get_excerpt(entry)

            articles.append({
                "title": title,
                "link": link,
                "source": source,
                "category": category,
                "category_label": CATEGORY_LABELS.get(category, category),
                "excerpt": excerpt,
                "published": pub_date.isoformat() if pub_date else None,
                "fingerprint": fingerprint(title),
            })

    return articles


def deduplicate(articles):
    """Remove duplicate/near-duplicate articles, preferring neutral sources."""
    # Source preference order (higher = preferred)
    source_priority = {
        "BBC News": 10, "BBC U.S.": 10, "BBC Science": 10,
        "Reuters": 9, "Associated Press": 9,
        "NPR World": 8, "NPR U.S.": 8, "NPR Politics": 8,
        "NPR Science": 8, "NPR Technology": 8,
    }

    # Sort by source priority (highest first)
    articles.sort(
        key=lambda a: source_priority.get(a["source"], 5), reverse=True
    )

    seen = []
    deduped = []

    for article in articles:
        is_dup = False
        for seen_article in seen:
            if titles_similar(article["title"], seen_article["title"]):
                is_dup = True
                break
        if not is_dup:
            deduped.append(article)
            seen.append(article)

    return deduped


def sort_articles(articles):
    """Sort articles: by category grouping, then by date (newest first)."""
    # Category display order
    cat_order = [
        "local", "us", "world", "science", "tech",
        "environment", "libraries", "longform"
    ]
    cat_rank = {c: i for i, c in enumerate(cat_order)}

    articles.sort(key=lambda a: (
        cat_rank.get(a["category"], 99),
        -(datetime.fromisoformat(a["published"]).timestamp() if a.get("published") else 0)
    ))

    return articles


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape RSS feeds for Leonne's Daily Post"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Look back this many hours (default: 24)"
    )
    parser.add_argument(
        "--max-per-category", type=int, default=12,
        help="Max articles per category (default: 12)"
    )
    args = parser.parse_args()

    print(f"Fetching feeds (last {args.hours} hours)...", file=sys.stderr)

    # Fetch standard RSS feeds
    articles = fetch_feeds(FEEDS, hours_back=args.hours)

    # Fetch custom sources (AP, Reuters, Lawfare)
    articles.extend(fetch_ap_articles(hours_back=args.hours))
    articles.extend(fetch_reuters_articles(hours_back=args.hours))
    articles.extend(fetch_lawfare_weekly())

    print(f"  Found {len(articles)} raw articles", file=sys.stderr)

    articles = deduplicate(articles)
    print(f"  After dedup: {len(articles)}", file=sys.stderr)

    # Cap per category
    category_counts = {}
    capped = []
    for article in articles:
        cat = article["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if category_counts[cat] <= args.max_per_category:
            capped.append(article)
    articles = capped

    articles = sort_articles(articles)
    print(f"  Final count: {len(articles)}", file=sys.stderr)

    # Build output
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours_back": args.hours,
        "article_count": len(articles),
        "categories": CATEGORY_LABELS,
        "articles": articles,
    }

    json_str = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"  Written to {args.output}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
