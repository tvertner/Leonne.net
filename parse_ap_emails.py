#!/usr/bin/env python3
"""
Leonne's Daily Post — AP Email Parser
Connects to Gmail via IMAP and extracts news stories from AP emails:
  - AP News Alerts (single-story breaking news)
  - AP Morning Wire / Afternoon Wire (multi-story digests)

Outputs JSON in the same format as scraper.py articles, which gets
merged into the article pool before the Haiku editorial pass.

Usage:
    python3 parse_ap_emails.py                    # Output to stdout
    python3 parse_ap_emails.py -o ap_articles.json
    python3 parse_ap_emails.py --hours 28         # Look back 28 hours

Environment variables:
    IMAP_USER   — Gmail address for receiving AP alerts
    IMAP_TOKEN  — Gmail App Password
"""

import argparse
import base64
import email
import email.header
import email.utils
import hashlib
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import urlparse, parse_qs, unquote


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993

# AP sender addresses we care about
AP_SENDERS = {
    "alerts@apnews.com": "alert",
    "morningwire@apnews.com": "wire",
    "afternoonwire@apnews.com": "wire",
}

# File to track already-processed Message-IDs (one per line)
PROCESSED_IDS_FILE = os.environ.get(
    "AP_PROCESSED_IDS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ap_processed_ids")
)

# Category labels matching scraper.py
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
# URL EXTRACTION
# ---------------------------------------------------------------------------

def decode_sailthru_url(tracked_url):
    """
    Decode a Sailthru tracking redirect URL to get the real AP article URL.

    Sailthru URLs look like:
        https://link.apnews.com/click/44179595.478365/<base64blob>/...
    The base64 blob decodes to the real URL with UTM params appended.
    """
    if not tracked_url:
        return None

    # Pattern: /click/<id>/<base64>/<suffix>
    match = re.search(r'/click/[\d.]+/([A-Za-z0-9+/=_-]+)/', tracked_url)
    if not match:
        # Try without trailing slash
        match = re.search(r'/click/[\d.]+/([A-Za-z0-9+/=_-]+)$', tracked_url)
    if not match:
        return None

    b64_chunk = match.group(1)

    # Fix URL-safe base64 variants
    b64_chunk = b64_chunk.replace('-', '+').replace('_', '/')

    # Add padding if needed
    padding = 4 - (len(b64_chunk) % 4)
    if padding != 4:
        b64_chunk += '=' * padding

    try:
        decoded = base64.b64decode(b64_chunk).decode('utf-8', errors='replace')
    except Exception:
        return None

    # Strip UTM and user_email params
    if '?' in decoded:
        base_url = decoded.split('?')[0]
    else:
        base_url = decoded

    # Only return apnews.com article URLs
    if 'apnews.com' in base_url:
        return base_url

    return None


def extract_apnews_urls(html_content):
    """Extract all AP News article URLs from email HTML."""
    # Find all Sailthru tracking URLs
    tracked_urls = re.findall(
        r'https://link\.apnews\.com/click/[\d.]+/[A-Za-z0-9+/=_-]+/[A-Za-z0-9+/=_-]+',
        html_content
    )

    urls = set()
    for tracked in tracked_urls:
        real_url = decode_sailthru_url(tracked)
        if real_url and '/article/' in real_url:
            urls.add(real_url)

    return list(urls)


# ---------------------------------------------------------------------------
# HTML TEXT EXTRACTION
# ---------------------------------------------------------------------------

def strip_html(text):
    """Remove HTML tags and decode entities."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def decode_quoted_printable_html(raw_body):
    """Decode quoted-printable email body to clean HTML."""
    # Replace =\n (soft line breaks)
    text = re.sub(r'=\r?\n', '', raw_body)
    # Decode =XX hex sequences
    text = re.sub(
        r'=([0-9A-Fa-f]{2})',
        lambda m: chr(int(m.group(1), 16)),
        text
    )
    return text


def get_html_body(msg):
    """Extract HTML body from an email.message.Message object."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/html':
                charset = part.get_content_charset() or 'utf-8'
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(charset, errors='replace')
    else:
        ct = msg.get_content_type()
        if ct == 'text/html':
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(charset, errors='replace')
    return ""


# ---------------------------------------------------------------------------
# ALERT PARSER
# ---------------------------------------------------------------------------

def parse_alert_email(msg, html_body):
    """
    Parse an AP News Alert email. These are simple single-story emails.

    Structure:
        - Subject = headline
        - Body has: headline (linked), date, 2-3 sentence summary, "Read more" button
    """
    raw_subject = msg.get('Subject', '')
    if not raw_subject:
        return []

    # Decode MIME-encoded subject and clean it (it IS the headline)
    headline = strip_html(decode_mime_header(raw_subject)).strip()

    # Get the date
    date_str = msg.get('Date', '')
    pub_date = None
    if date_str:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed:
            pub_date = parsed.astimezone(timezone.utc)

    # Extract article URL
    urls = extract_apnews_urls(html_body)
    article_url = urls[0] if urls else None

    # Extract summary text from the body
    # In alerts, the summary is in a block-4 text element after the headline
    # Look for the main body paragraph (18px font-size text)
    summary_match = re.search(
        r'font-size:\s*18px[^>]*>([^<]+(?:<[^>]*>[^<]*)*?)</p>',
        html_body,
        re.DOTALL
    )
    summary = ""
    if summary_match:
        summary = strip_html(summary_match.group(1)).strip()
        # Clean up artifacts
        summary = re.sub(r'\s+', ' ', summary).strip()

    if not summary:
        # Fallback: try to get any substantial text block
        text_blocks = re.findall(
            r'font-size:\s*1[68]px[^>]*>(.+?)</(?:p|div)>',
            html_body,
            re.DOTALL
        )
        for block in text_blocks:
            cleaned = strip_html(block).strip()
            if len(cleaned) > 50 and headline.lower() not in cleaned.lower()[:30]:
                summary = cleaned
                break

    return [{
        "title": headline,
        "link": article_url or "",
        "source": "Associated Press",
        "category": guess_category(headline, summary, article_url),
        "excerpt": summary,
        "published": pub_date.isoformat() if pub_date else None,
        "fingerprint": fingerprint(headline),
        "ap_email_type": "alert",
        "ap_priority": 7,  # Alerts are breaking news, high priority
    }]


# ---------------------------------------------------------------------------
# WIRE DIGEST PARSER
# ---------------------------------------------------------------------------

def parse_wire_email(msg, html_body):
    """
    Parse an AP Morning Wire or Afternoon Wire digest email.

    Structure:
        UP FIRST — Lead story: image, headline, summary, related links
        TOP STORIES — 2-3 stories: headline, summary, related links
        IN OTHER NEWS — Quick-hit one-liners: bold label + linked headline
        TRENDING — 1 story: image, headline, summary
    """
    articles = []

    date_str = msg.get('Date', '')
    pub_date = None
    if date_str:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed:
            pub_date = parsed.astimezone(timezone.utc)

    pub_iso = pub_date.isoformat() if pub_date else None

    # --- UP FIRST section ---
    # The lead story follows the "UP FIRST" section header
    up_first = extract_section_stories(html_body, "UP FIRST", "TOP STORIES")
    for i, story in enumerate(up_first):
        story["ap_email_type"] = "wire_lead"
        story["ap_priority"] = 9  # Lead story, highest priority
        story["published"] = pub_iso
        articles.append(story)

    # --- TOP STORIES section ---
    top_stories = extract_section_stories(html_body, "TOP STORIES", "IN OTHER NEWS")
    for story in top_stories:
        story["ap_email_type"] = "wire_top"
        story["ap_priority"] = 8
        story["published"] = pub_iso
        articles.append(story)

    # --- IN OTHER NEWS section ---
    other_news = extract_other_news(html_body)
    for story in other_news:
        story["ap_email_type"] = "wire_other"
        story["ap_priority"] = 6
        story["published"] = pub_iso
        articles.append(story)

    # --- TRENDING section ---
    trending = extract_section_stories(html_body, "TRENDING", None)
    for story in trending:
        story["ap_email_type"] = "wire_trending"
        story["ap_priority"] = 7
        story["published"] = pub_iso
        articles.append(story)

    return articles


def extract_section_stories(html_body, section_start, section_end):
    """
    Extract stories from a named section of the Wire email.
    Each story has a bold headline followed by summary text.
    """
    stories = []

    # Find section boundaries
    start_pattern = re.compile(
        rf'<strong>\s*{re.escape(section_start)}\s*</strong>',
        re.IGNORECASE
    )
    start_match = start_pattern.search(html_body)
    if not start_match:
        return stories

    start_pos = start_match.end()

    if section_end:
        end_pattern = re.compile(
            rf'<strong>\s*{re.escape(section_end)}\s*</strong>',
            re.IGNORECASE
        )
        end_match = end_pattern.search(html_body, start_pos)
        end_pos = end_match.start() if end_match else len(html_body)
    else:
        end_pos = len(html_body)

    section_html = html_body[start_pos:end_pos]

    # Find headlines: bold text in 20px+ font, often linked
    # Pattern: font-size: 20px ... <strong>HEADLINE TEXT</strong>
    headline_pattern = re.compile(
        r'font-size:\s*(?:2[0-9]|3[0-9])px[^>]*>'
        r'\s*<strong>(.*?)</strong>',
        re.DOTALL
    )

    for h_match in headline_pattern.finditer(section_html):
        raw_headline = h_match.group(1)
        headline = strip_html(raw_headline).strip()
        if not headline or len(headline) < 10:
            continue

        # Skip section headers that leaked in
        if headline.upper() in ("UP FIRST", "TOP STORIES", "IN OTHER NEWS",
                                "TRENDING", "RELATED COVERAGE ➤",
                                "RELATED COVERAGE"):
            continue

        # Find URLs near this headline
        nearby_html = section_html[max(0, h_match.start() - 200):
                                    min(len(section_html), h_match.end() + 2000)]
        urls = extract_apnews_urls(nearby_html)
        article_url = urls[0] if urls else ""

        # Find summary: the paragraph(s) following the headline with 18px font
        after_headline = section_html[h_match.end():h_match.end() + 3000]
        summary_match = re.search(
            r'font-size:\s*18px[^>]*>(.*?)(?:Read more\.|</p>)',
            after_headline,
            re.DOTALL
        )
        summary = ""
        if summary_match:
            summary = strip_html(summary_match.group(1)).strip()
            # Clean up
            summary = re.sub(r'\s+', ' ', summary).strip()

        stories.append({
            "title": headline,
            "link": article_url,
            "source": "Associated Press",
            "category": guess_category(headline, summary, article_url),
            "category_label": "",  # Will be filled in later
            "excerpt": summary,
            "fingerprint": fingerprint(headline),
        })

    return stories


def extract_other_news(html_body):
    """
    Extract the IN OTHER NEWS one-liner stories.
    Format: <strong>Label:</strong> <a href="...">Headline text</a>
    """
    stories = []

    # Find the IN OTHER NEWS section
    start_match = re.search(
        r'<strong>\s*IN OTHER NEWS\s*</strong>',
        html_body, re.IGNORECASE
    )
    if not start_match:
        return stories

    # Find the end (TRENDING section or end of content area)
    end_match = re.search(
        r'<strong>\s*TRENDING\s*</strong>',
        html_body[start_match.end():], re.IGNORECASE
    )
    if end_match:
        section_html = html_body[start_match.end():start_match.end() + end_match.start()]
    else:
        section_html = html_body[start_match.end():start_match.end() + 10000]

    # Pattern: <strong>Label:</strong> <a href="tracked_url">Headline</a>
    # These appear in 18px text blocks with line-height:1.8
    item_pattern = re.compile(
        r'<strong>([^<]+?)\s*:?\s*</strong>\s*'
        r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>',
        re.DOTALL
    )

    for match in item_pattern.finditer(section_html):
        label = strip_html(match.group(1)).strip().rstrip(':')
        tracked_url = match.group(2)
        headline_text = strip_html(match.group(3)).strip()

        if not headline_text or len(headline_text) < 10:
            continue

        # Skip non-story labels
        if label.upper() in ("RELATED COVERAGE", "RELATED COVERAGE ➤",
                             "WATCH", "LISTEN"):
            # WATCH entries are still stories, keep them
            if label.upper() == "WATCH":
                pass
            else:
                continue

        real_url = decode_sailthru_url(tracked_url) or ""
        full_headline = headline_text

        stories.append({
            "title": full_headline,
            "link": real_url,
            "source": "Associated Press",
            "category": guess_category(full_headline, "", real_url),
            "category_label": "",
            "excerpt": "",  # One-liners don't have summaries
            "fingerprint": fingerprint(full_headline),
        })

    return stories


# ---------------------------------------------------------------------------
# RELATED COVERAGE EXTRACTION
# ---------------------------------------------------------------------------

def extract_related_links(html_body):
    """
    Extract RELATED COVERAGE links from Wire emails.
    These are bulleted lists of additional story links.
    Returns a list of {title, url} dicts.
    """
    related = []

    # Find all RELATED COVERAGE sections
    sections = re.split(
        r'<strong>\s*RELATED COVERAGE\s*➤?\s*</strong>',
        html_body, flags=re.IGNORECASE
    )

    for section in sections[1:]:  # Skip everything before first RELATED COVERAGE
        # Limit to the list that follows
        end = re.search(r'(?:divider_block|<strong>(?:UP FIRST|TOP STORIES|IN OTHER NEWS|TRENDING))', section)
        chunk = section[:end.start()] if end else section[:5000]

        # Find list items with links
        link_pattern = re.compile(
            r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>',
            re.DOTALL
        )

        for match in link_pattern.finditer(chunk):
            tracked_url = match.group(1)
            title = strip_html(match.group(2)).strip()

            if not title or len(title) < 15:
                continue

            real_url = decode_sailthru_url(tracked_url) or ""
            if real_url:
                related.append({
                    "title": title,
                    "link": real_url,
                    "source": "Associated Press",
                    "category": guess_category(title, "", real_url),
                    "category_label": "",
                    "excerpt": "",
                    "fingerprint": fingerprint(title),
                    "ap_email_type": "wire_related",
                    "ap_priority": 5,  # Lower priority than main stories
                })

    return related


# ---------------------------------------------------------------------------
# CATEGORY GUESSING
# ---------------------------------------------------------------------------

def guess_category(headline, summary, url):
    """
    Guess article category from headline, summary, and URL path.
    AP articles span many topics; this does a best-effort classification.
    """
    text = f"{headline} {summary}".lower()
    url_lower = (url or "").lower()

    # Check URL path for section hints
    if '/science' in url_lower:
        return 'science'
    if '/technology' in url_lower:
        return 'tech'
    if '/entertainment' in url_lower or '/sports' in url_lower:
        return 'us'  # General interest, fits U.S. bucket

    # Keyword-based classification
    science_kw = ['study finds', 'researchers', 'nasa', 'space', 'climate',
                  'species', 'fossil', 'vaccine', 'genome', 'medical',
                  'scientific', 'asteroid', 'telescope', 'physicist']
    tech_kw = ['ai ', 'artificial intelligence', 'cyber', 'app ', 'tech ',
               'software', 'silicon valley', 'crypto', 'blockchain', 'robot',
               'data breach', 'social media', 'tesla', 'apple ', 'google ',
               'microsoft', 'amazon ']
    env_kw = ['climate change', 'emission', 'wildfire', 'flooding',
              'drought', 'renewable', 'solar', 'carbon', 'deforestation',
              'endangered', 'pollution', 'epa ']
    world_kw = ['ukraine', 'russia', 'china', 'europe', 'nato', 'un ',
                'united nations', 'middle east', 'israel', 'gaza', 'iran',
                'north korea', 'brazil', 'india', 'africa', 'greenland',
                'peru', 'cuba', 'congress removes']

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

    # Default to U.S. news for AP (they're a U.S.-based wire service,
    # and most of their alerts/wire stories are domestic)
    return 'us'


# ---------------------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------------------

def decode_mime_header(raw_header):
    """Decode a MIME-encoded email header (e.g. =?utf-8?B?...?=) to plain text."""
    if not raw_header:
        return ""
    decoded_parts = email.header.decode_header(raw_header)
    parts = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            parts.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            parts.append(part)
    return ' '.join(parts)


def fingerprint(title):
    """Create a fingerprint for deduplication (matches scraper.py)."""
    normalized = re.sub(r"[^\w\s]", "", title.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def load_processed_ids():
    """Load set of already-processed Message-IDs."""
    try:
        with open(PROCESSED_IDS_FILE, 'r') as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_processed_ids(ids):
    """Save processed Message-IDs. Keeps only the most recent 500."""
    ids_list = sorted(ids)[-500:]  # Keep last 500 to avoid unbounded growth
    with open(PROCESSED_IDS_FILE, 'w') as f:
        for mid in ids_list:
            f.write(mid + '\n')


# ---------------------------------------------------------------------------
# IMAP FETCHING
# ---------------------------------------------------------------------------

def fetch_ap_emails(hours_back=28):
    """
    Connect to Gmail via IMAP and fetch AP emails from the given time window.
    Returns a list of article dicts ready for merging with scraper output.
    """
    imap_user = os.environ.get('IMAP_USER')
    imap_token = os.environ.get('IMAP_TOKEN')

    if not imap_user or not imap_token:
        print("⚠ IMAP_USER and IMAP_TOKEN not set, skipping email parsing",
              file=sys.stderr)
        return []

    # Calculate the IMAP SINCE date (IMAP only supports date, not datetime)
    since_date = (datetime.now(timezone.utc) - timedelta(hours=hours_back))
    since_str = since_date.strftime("%d-%b-%Y")

    articles = []
    processed_ids = load_processed_ids()
    new_processed_ids = set(processed_ids)

    try:
        print(f"  Connecting to {IMAP_SERVER}...", file=sys.stderr)
        conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        conn.login(imap_user, imap_token)
        conn.select('INBOX', readonly=True)

        # Search for AP emails since the cutoff date
        # We search for each sender separately to be precise
        all_uids = set()
        for sender in AP_SENDERS:
            search_criteria = f'(FROM "{sender}" SINCE {since_str})'
            status, data = conn.search(None, search_criteria)
            if status == 'OK' and data[0]:
                uids = data[0].split()
                all_uids.update(uids)
                print(f"    {sender}: {len(uids)} emails found", file=sys.stderr)

        if not all_uids:
            print("  No AP emails found in timeframe", file=sys.stderr)
            conn.logout()
            return []

        print(f"  Processing {len(all_uids)} AP emails...", file=sys.stderr)

        for uid in sorted(all_uids):
            try:
                # Fetch the email
                status, msg_data = conn.fetch(uid, '(RFC822)')
                if status != 'OK':
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Check Message-ID to skip already-processed emails
                message_id = msg.get('Message-ID', '').strip()
                if message_id in processed_ids:
                    continue

                # Determine email type from sender
                from_addr = email.utils.parseaddr(msg.get('From', ''))[1].lower()
                email_type = AP_SENDERS.get(from_addr)
                if not email_type:
                    continue

                # Check date is actually within our window
                date_str = msg.get('Date', '')
                if date_str:
                    msg_date = email.utils.parsedate_to_datetime(date_str)
                    if msg_date:
                        msg_date_utc = msg_date.astimezone(timezone.utc)
                        if msg_date_utc < since_date:
                            continue

                # Get HTML body
                html_body = get_html_body(msg)
                if not html_body:
                    continue

                # Parse based on email type
                if email_type == 'alert':
                    extracted = parse_alert_email(msg, html_body)
                elif email_type == 'wire':
                    extracted = parse_wire_email(msg, html_body)
                    # Also grab related coverage links from Wire
                    related = extract_related_links(html_body)
                    extracted.extend(related)
                else:
                    extracted = []

                # Fill in category labels
                for article in extracted:
                    if not article.get("category_label"):
                        article["category_label"] = CATEGORY_LABELS.get(
                            article.get("category", "us"), "U.S."
                        )

                articles.extend(extracted)
                new_processed_ids.add(message_id)

                subject = decode_mime_header(msg.get('Subject', ''))[:60]
                print(f"    ✓ {email_type}: {subject}... ({len(extracted)} stories)",
                      file=sys.stderr)

            except Exception as e:
                print(f"    ⚠ Error processing email {uid}: {e}", file=sys.stderr)
                continue

        conn.logout()

    except imaplib.IMAP4.error as e:
        print(f"⚠ IMAP error: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"⚠ Email fetch error: {e}", file=sys.stderr)
        return []

    # Save updated processed IDs
    save_processed_ids(new_processed_ids)

    # Deduplicate within our results (same story might appear in alert + wire)
    seen_fps = set()
    unique = []
    for a in articles:
        fp = a.get("fingerprint", "")
        if fp and fp not in seen_fps:
            seen_fps.add(fp)
            unique.append(a)

    print(f"  AP emails: {len(unique)} unique stories extracted", file=sys.stderr)
    return unique


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Parse AP emails for Leonne's Daily Post"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--hours", type=int, default=28,
        help="Look back this many hours (default: 28)"
    )
    args = parser.parse_args()

    print(f"Fetching AP emails (last {args.hours} hours)...", file=sys.stderr)
    articles = fetch_ap_emails(hours_back=args.hours)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours_back": args.hours,
        "article_count": len(articles),
        "source": "ap_email_parser",
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
