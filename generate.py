#!/usr/bin/env python3
"""
Leonne's Daily Post — HTML Generator
Takes the scraper's articles.json, sends it to the Anthropic API
for editorial selection and commentary, then assembles the final HTML.

Usage:
    python3 generate.py -i articles.json -o index.html
    python3 generate.py -i articles.json -o index.html --deploy https://leonne.net/deploy

Environment variables:
    ANTHROPIC_API_KEY  — Your Anthropic API key
    DEPLOY_TOKEN       — Token for the deploy endpoint (if using --deploy)
"""

import argparse
import glob
import html as html_lib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

try:
    import anthropic
except ImportError:
    print("anthropic SDK not installed. Run: pip3 install anthropic")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip3 install requests")
    sys.exit(1)

try:
    from config import (
        STRIPE_PRICING_TABLE_ID, STRIPE_PUBLISHABLE_KEY,
        ENRICHMENT_MODEL, SELECTION_MODEL, FALLBACK_MODEL,
        SITE_NAME, SITE_TAGLINE, READER_NAME, READER_DESCRIPTION,
        STORY_COUNT_MIN, STORY_COUNT_MAX,
    )
except ImportError:
    # Fallback defaults if config.py is not present
    STRIPE_PRICING_TABLE_ID = os.environ.get("STRIPE_PRICING_TABLE_ID", "")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    ENRICHMENT_MODEL = "claude-haiku-4-5-20251001"
    SELECTION_MODEL = "claude-sonnet-4-5-20250929"
    FALLBACK_MODEL = "claude-haiku-4-5-20251001"
    SITE_NAME = "Leonne's Daily Post"
    SITE_TAGLINE = "Curated with love for Leonne"
    READER_NAME = "Leonne"
    READER_DESCRIPTION = "a librarian with ADHD and chronic migraines"
    STORY_COUNT_MIN = 35
    STORY_COUNT_MAX = 50


# ---------------------------------------------------------------------------
# HTML TEMPLATE
# ---------------------------------------------------------------------------
# Placeholders:
#   {{DATE}}          — Today's date string
#   {{ENTRIES}}       — The generated article entries HTML
#   {{ARCHIVE_LIST}}  — Links to past editions
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Leonne's Daily Post</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,300;0,7..72,400;0,7..72,500;1,7..72,300;1,7..72,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #1a1a1f;
            --bg-surface: #222228;
            --bg-hover: #2a2a31;
            --text-primary: #d4d1cc;
            --text-secondary: #9a9790;
            --text-muted: #6b6862;
            --accent: #c4956a;
            --accent-muted: #a07a55;
            --border: #2e2e35;
            --border-light: #38383f;
            --font-body: 'DM Sans', sans-serif;
            --font-serif: 'Literata', Georgia, serif;
            --line-height: 1.7;
            --letter-spacing: 0.015em;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html { font-size: 17px; scroll-behavior: smooth; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
        body { background-color: var(--bg-primary); color: var(--text-primary); font-family: var(--font-body); line-height: var(--line-height); letter-spacing: var(--letter-spacing); min-height: 100vh; }
        .container { max-width: 960px; margin: 0 auto; padding: 0 1.5rem; }
        header { padding: 3rem 0 2rem; border-bottom: 1px solid var(--border); margin-bottom: 2rem; }
        .site-header-row { display: flex; justify-content: space-between; align-items: baseline; }
        .site-name { font-family: var(--font-serif); font-size: 1.62rem; font-weight: 400; color: var(--text-primary); letter-spacing: 0.04em; display: flex; align-items: center; gap: 0.5rem; }
        .site-logo { width: 1.5em; height: 1.5em; flex-shrink: 0; stroke: var(--accent); }
        .site-date { font-family: var(--font-body); font-size: 0.8rem; font-weight: 300; color: var(--text-muted); letter-spacing: 0.02em; }
        .topic-nav { display: flex; flex-wrap: wrap; gap: 0.25rem; padding: 1.25rem 0; }
        .topic-btn { font-family: var(--font-body); font-size: 0.78rem; font-weight: 400; color: var(--text-secondary); background: transparent; border: 1px solid var(--border); border-radius: 4px; padding: 0.35rem 0.75rem; cursor: pointer; letter-spacing: 0.02em; white-space: nowrap; }
        .topic-btn:hover { color: var(--text-primary); border-color: var(--border-light); background: var(--bg-hover); }
        .topic-btn.is-active { color: var(--accent); border-color: var(--accent-muted); background: rgba(196, 149, 106, 0.08); }
        .topic-btn:focus-visible { outline: 2px solid var(--accent-muted); outline-offset: 2px; border-radius: 4px; }
        .support-btn { font-family: var(--font-body); font-size: 0.78rem; font-weight: 400; color: var(--text-secondary); background: transparent; border: 1px solid var(--border); border-radius: 4px; padding: 0.35rem 0.75rem; cursor: pointer; letter-spacing: 0.02em; white-space: nowrap; }
        .support-btn:hover { color: var(--accent); border-color: var(--accent-muted); background: rgba(196, 149, 106, 0.08); }
        .support-btn:focus-visible { outline: 2px solid var(--accent-muted); outline-offset: 2px; border-radius: 4px; }
        .date-group { margin-bottom: 2.5rem; }
        .date-label { font-family: var(--font-body); font-size: 0.78rem; font-weight: 500; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.1em; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border); margin-bottom: 1rem; }
        .entry { padding: 1rem 1.15rem; margin-bottom: 0.35rem; border-radius: 6px; cursor: pointer; }
        .entry:hover { background-color: var(--bg-hover); }
        .entry.is-hidden { display: none; }
        .entry.is-read { opacity: 0.55; }
        .entry.is-read:hover { opacity: 0.75; }
        .date-group.is-empty { display: none; }
        .entry-top-row { display: flex; align-items: flex-start; gap: 0.75rem; }
        .read-check { flex-shrink: 0; width: 18px; height: 18px; margin-top: 0.35rem; appearance: none; -webkit-appearance: none; background: transparent; border: 1.5px solid var(--border-light); border-radius: 3px; cursor: pointer; position: relative; pointer-events: auto; z-index: 1; }
        .read-check:checked { background: var(--accent-muted); border-color: var(--accent-muted); }
        .read-check:checked::after { content: '✓'; position: absolute; top: -1px; left: 2px; font-size: 13px; color: var(--bg-primary); font-weight: 600; }
        .entry-content { flex: 1; min-width: 0; }
        .entry-tag { font-family: var(--font-body); font-size: 0.68rem; font-weight: 500; color: var(--accent-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.3rem; }
        .entry-header { }
        .entry-title { font-family: var(--font-serif); font-size: 1.05rem; font-weight: 400; color: var(--text-primary); line-height: 1.5; }
        .entry-commentary { font-family: var(--font-body); font-size: 0.9rem; font-weight: 300; color: var(--text-secondary); margin-top: 0.5rem; line-height: 1.65; }
        .read-more { display: inline-block; font-family: var(--font-body); font-size: 0.82rem; font-weight: 400; color: var(--accent); text-decoration: none; letter-spacing: 0.03em; padding: 0.3rem 0; margin-top: 0.35rem; }
        .read-more:hover { color: var(--text-primary); }
        .read-more:focus-visible { outline: 2px solid var(--accent-muted); outline-offset: 3px; border-radius: 2px; }
        .read-more span { margin-left: 0.3rem; }
        footer { margin-top: 3rem; padding: 2rem 0; border-top: 1px solid var(--border); }
        .footer-text { font-size: 0.78rem; color: var(--text-muted); font-weight: 300; }
        .footer-links { margin-top: 0.75rem; display: flex; gap: 1.25rem; flex-wrap: wrap; }
        .footer-link { font-family: var(--font-body); font-size: 0.78rem; font-weight: 400; color: var(--text-muted); background: none; border: none; cursor: pointer; padding: 0; letter-spacing: 0.02em; text-decoration: none; }
        .footer-link:hover { color: var(--accent); }
        kbd { font-family: var(--font-body); font-size: 0.72rem; color: var(--text-secondary); background: var(--bg-surface); border: 1px solid var(--border-light); border-radius: 3px; padding: 0.1rem 0.35rem; margin: 0 0.05rem; }
        .setup-overlay { display: none; position: fixed; inset: 0; background: rgba(10, 10, 12, 0.85); z-index: 100; justify-content: center; align-items: center; padding: 1.5rem; }
        .setup-overlay.is-visible { display: flex; }
        .setup-panel { background: var(--bg-surface); border: 1px solid var(--border-light); border-radius: 8px; max-width: 560px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 2rem 2.25rem; }
        .setup-panel-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 1.75rem; }
        .setup-panel-title { font-family: var(--font-serif); font-size: 1.15rem; font-weight: 400; color: var(--text-primary); }
        .setup-close { font-family: var(--font-body); font-size: 0.8rem; color: var(--text-muted); background: none; border: none; cursor: pointer; padding: 0.25rem; }
        .setup-close:hover { color: var(--text-primary); }
        .setup-section { margin-bottom: 1.75rem; }
        .setup-section:last-child { margin-bottom: 0; }
        .setup-section-title { font-family: var(--font-body); font-size: 0.82rem; font-weight: 500; color: var(--accent); margin-bottom: 0.75rem; letter-spacing: 0.02em; }
        .setup-device { margin-bottom: 1.25rem; }
        .setup-device:last-child { margin-bottom: 0; }
        .setup-device-name { font-family: var(--font-body); font-size: 0.82rem; font-weight: 500; color: var(--text-primary); margin-bottom: 0.4rem; }
        .setup-step { font-family: var(--font-body); font-size: 0.85rem; font-weight: 300; color: var(--text-secondary); line-height: 1.7; margin-bottom: 0.3rem; padding-left: 1.15rem; position: relative; }
        .setup-step::before { content: attr(data-step); position: absolute; left: 0; color: var(--text-muted); font-size: 0.75rem; }
        .setup-note { font-family: var(--font-body); font-size: 0.82rem; font-weight: 300; color: var(--text-muted); line-height: 1.65; margin-top: 0.75rem; font-style: italic; }
        .setup-divider { border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }
        .archive-list { }
        .archive-link { display: block; font-family: var(--font-body); font-size: 0.88rem; font-weight: 300; color: var(--text-secondary); text-decoration: none; padding: 0.55rem 0; border-bottom: 1px solid var(--border); }
        .archive-link:first-child { border-top: 1px solid var(--border); }
        .archive-link:hover { color: var(--accent); }
        .archive-link:focus-visible { outline: 2px solid var(--accent-muted); outline-offset: 2px; }
        .archive-empty { font-family: var(--font-body); font-size: 0.85rem; font-weight: 300; color: var(--text-muted); font-style: italic; }
        .support-link-row { text-align: center; padding: 0.35rem 0 0.1rem; }
        .support-link-row a { font-family: var(--font-body); font-size: 0.82rem; font-weight: 400; color: var(--text-muted); text-decoration: none; letter-spacing: 0.03em; }
        .support-link-row a:hover { color: var(--accent); }
        .support-link-row a:focus-visible { outline: 2px solid var(--accent-muted); outline-offset: 3px; border-radius: 2px; }
        .support-body { font-family: var(--font-body); font-size: 0.88rem; font-weight: 300; color: var(--text-secondary); line-height: 1.7; margin-bottom: 1.25rem; }
        .contact-field { margin-bottom: 1.15rem; }
        .contact-field:last-of-type { margin-bottom: 1.5rem; }
        .contact-label { display: block; font-family: var(--font-body); font-size: 0.82rem; font-weight: 400; color: var(--text-secondary); margin-bottom: 0.4rem; letter-spacing: 0.02em; }
        .contact-input, .contact-textarea { width: 100%; font-family: var(--font-body); font-size: 0.9rem; font-weight: 300; color: var(--text-primary); background: var(--bg-primary); border: 1px solid var(--border-light); border-radius: 4px; padding: 0.6rem 0.75rem; letter-spacing: 0.015em; }
        .contact-input:focus, .contact-textarea:focus { outline: none; border-color: var(--accent-muted); }
        .contact-textarea { min-height: 120px; resize: vertical; line-height: 1.6; }
        .contact-submit { font-family: var(--font-body); font-size: 0.85rem; font-weight: 400; color: var(--bg-primary); background: var(--accent); border: none; border-radius: 4px; padding: 0.6rem 1.5rem; cursor: pointer; letter-spacing: 0.02em; }
        .contact-submit:hover { background: var(--accent-muted); }
        .contact-submit:disabled { opacity: 0.5; cursor: not-allowed; }
        .contact-submit:focus-visible { outline: 2px solid var(--accent-muted); outline-offset: 2px; }
        .contact-status { font-family: var(--font-body); font-size: 0.85rem; font-weight: 300; margin-top: 0.75rem; }
        .contact-status.is-success { color: #7a9f7a; }
        .contact-status.is-error { color: #c47a6a; }
        .hp-field { position: absolute; left: -9999px; opacity: 0; height: 0; width: 0; }
        .sources-section { margin-bottom: 1.25rem; }
        .sources-section:last-child { margin-bottom: 0; }
        .sources-section-title { font-family: var(--font-body); font-size: 0.75rem; font-weight: 500; color: var(--accent-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.15rem; margin-top: 0.25rem; }
        .source-filter-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.45rem 0; border-bottom: 1px solid var(--border); }
        .source-filter-row:first-of-type { border-top: 1px solid var(--border); }
        .source-filter-check { flex-shrink: 0; width: 16px; height: 16px; appearance: none; -webkit-appearance: none; background: transparent; border: 1.5px solid var(--border-light); border-radius: 3px; cursor: pointer; position: relative; }
        .source-filter-check:checked { background: var(--accent-muted); border-color: var(--accent-muted); }
        .source-filter-check:checked::after { content: '\2713'; position: absolute; top: -1px; left: 2px; font-size: 12px; color: var(--bg-primary); font-weight: 600; }
        .source-filter-check:focus-visible { outline: 2px solid var(--accent-muted); outline-offset: 2px; }
        .source-filter-row a { flex: 1; }
        @media (max-width: 480px) { html { font-size: 16px; } .container { padding: 0 1.15rem; } header { padding: 2rem 0 1.5rem; } .entry { padding: 0.85rem 0.75rem; } }
        @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
        @media print { body { background: white; color: #222; } .entry-title { color: #222; } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="site-header-row">
                <div class="site-name"><svg class="site-logo" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="7" y1="8" x2="17" y2="8"/><line x1="7" y1="12" x2="12" y2="12"/><line x1="7" y1="16" x2="14" y2="16"/><rect x="14" y="11" width="3" height="5" rx="0.5"/></svg>Leonne's Daily Post</div>
                <div class="site-date">{{DATE}}</div>
            </div>
            <nav class="topic-nav" role="navigation" aria-label="Topic filters">
                <button class="support-btn" onclick="event.preventDefault(); document.getElementById('support-overlay').classList.add('is-visible')">Support ♡</button>
                <button class="topic-btn is-active" data-topic="all">All</button>
                <button class="topic-btn" data-topic="local">Local</button>
                <button class="topic-btn" data-topic="us">U.S.</button>
                <button class="topic-btn" data-topic="world">World</button>
                <button class="topic-btn" data-topic="science">Science</button>
                <button class="topic-btn" data-topic="tech">Tech</button>
                <button class="topic-btn" data-topic="environment">Environment</button>
                <button class="topic-btn" data-topic="libraries">Libraries</button>
                <button class="topic-btn" data-topic="longform">Long Read</button>
            </nav>
        </header>
        <main>
{{ENTRIES}}
        </main>
        <footer>
            <p class="footer-text">Curated with love for Leonne</p>
            <div class="footer-links">
                <button class="footer-link" onclick="document.getElementById('past-editions').classList.add('is-visible')">Past editions ↗</button>
                <button class="footer-link" onclick="document.getElementById('sources-list').classList.add('is-visible')">Sources ↗</button>
                <button class="footer-link" onclick="document.getElementById('setup-guide').classList.add('is-visible')">Reading setup guide ↗</button>
                <button class="footer-link" onclick="document.getElementById('privacy-policy').classList.add('is-visible')">Privacy ↗</button>
                <button class="footer-link" onclick="document.getElementById('contact-form').classList.add('is-visible')">Contact ↗</button>
                <button class="footer-link" onclick="document.getElementById('about-overlay').classList.add('is-visible')">About ↗</button>
            </div>
        </footer>
    </div>
    <div class="support-link-row">
        <a href="#" onclick="event.preventDefault(); document.getElementById('support-overlay').classList.add('is-visible')">Support this project ♡</a>
    </div>
    <div id="about-overlay" class="setup-overlay" onclick="if(event.target===this) this.classList.remove('is-visible')">
        <div class="setup-panel" role="dialog" aria-label="About">
            <div class="setup-panel-header">
                <h2 class="setup-panel-title">About</h2>
                <button class="setup-close" onclick="document.getElementById('about-overlay').classList.remove('is-visible')">Close ✕</button>
            </div>
            <p class="support-body">Leonne's Daily Post is a site I designed with the help of <a href="https://claude.ai" target="_blank" rel="noopener" style="color: var(--accent); text-decoration: none;">Claude.ai</a> for my wife — a chronic migraine sufferer with ADHD — who wanted a better way to keep up with the world without the endless doomscroll, visual clutter, and distracting ads that come with most news sites.</p>
            <p class="support-body">The result is a calm, curated daily digest: a handful of stories worth reading, presented in a clean, accessible format. No algorithms, no tracking, no noise.</p>
            <p class="support-body">I hope it benefits whoever finds it in the same way. If you have feedback, suggestions, or just want to say hello, feel free to <a href="#" style="color: var(--accent); text-decoration: none;" onclick="event.preventDefault(); document.getElementById('about-overlay').classList.remove('is-visible'); document.getElementById('contact-form').classList.add('is-visible');">contact me</a>.</p>
            <hr class="setup-divider">
            <div class="setup-section">
                <div class="setup-section-title">Open Source</div>
                <p class="support-body" style="margin-bottom: 0;">This project is open source under the <a href="https://www.gnu.org/licenses/agpl-3.0.en.html" target="_blank" rel="noopener" style="color: var(--accent); text-decoration: none;">GNU Affero General Public License v3.0</a>. You're free to use, modify, and share the code — fork it and build a Daily Post for someone you care about. View the source on <a href="https://github.com/tvertner/Leonne.net" target="_blank" rel="noopener" style="color: var(--accent); text-decoration: none;">GitHub</a>.</p>
            </div>
        </div>
    </div>
    <div id="support-overlay" class="setup-overlay" onclick="if(event.target===this) this.classList.remove('is-visible')">
        <div class="setup-panel" role="dialog" aria-label="Support this project">
            <div class="setup-panel-header">
                <h2 class="setup-panel-title">Support This Project</h2>
                <button class="setup-close" onclick="document.getElementById('support-overlay').classList.remove('is-visible')">Close ✕</button>
            </div>
            <p class="support-body">Leonne's Daily Post is a small, independent project — hand-curated news delivered in a clean, accessible format, free of ads, trackers, and algorithmic noise.</p>
            <p class="support-body">If you find value in what we're building, a contribution of any size helps cover hosting, development, and the care that goes into each edition.</p>
            <script async src="https://js.stripe.com/v3/pricing-table.js"></script>
            <stripe-pricing-table pricing-table-id="{{STRIPE_PRICING_TABLE_ID}}"
            publishable-key="{{STRIPE_PUBLISHABLE_KEY}}">
            </stripe-pricing-table>
            <p class="setup-note" style="margin-top: 1rem; text-align: center;">Processed securely by Stripe.</p>
        </div>
    </div>
    <div id="sources-list" class="setup-overlay" onclick="if(event.target===this) this.classList.remove('is-visible')">
        <div class="setup-panel" role="dialog" aria-label="Sources">
            <div class="setup-panel-header">
                <h2 class="setup-panel-title">Sources</h2>
                <button class="setup-close" onclick="document.getElementById('sources-list').classList.remove('is-visible')">Close ✕</button>
            </div>
            <p class="setup-note" style="margin-top: 0; margin-bottom: 1.25rem;">The feeds and sites this edition draws from. Uncheck a source to hide its stories.</p>
            <div class="sources-section">
                <div class="sources-section-title">World & U.S. News</div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="bbc-news" checked><a href="https://www.bbc.com/news" class="archive-link" target="_blank" rel="noopener">BBC News</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="npr" checked><a href="https://www.npr.org" class="archive-link" target="_blank" rel="noopener">NPR</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="ap" checked><a href="https://apnews.com" class="archive-link" target="_blank" rel="noopener">Associated Press</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="reuters" checked><a href="https://www.reuters.com" class="archive-link" target="_blank" rel="noopener">Reuters</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="al-jazeera" checked><a href="https://www.aljazeera.com" class="archive-link" target="_blank" rel="noopener">Al Jazeera</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="the-hill" checked><a href="https://thehill.com" class="archive-link" target="_blank" rel="noopener">The Hill</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="pbs-newshour" checked><a href="https://www.pbs.org/newshour" class="archive-link" target="_blank" rel="noopener">PBS NewsHour</a></div>
            </div>
            <div class="sources-section">
                <div class="sources-section-title">Science</div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="nature" checked><a href="https://www.nature.com" class="archive-link" target="_blank" rel="noopener">Nature</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="quanta-magazine" checked><a href="https://www.quantamagazine.org" class="archive-link" target="_blank" rel="noopener">Quanta Magazine</a></div>
            </div>
            <div class="sources-section">
                <div class="sources-section-title">Technology</div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="ars-technica" checked><a href="https://arstechnica.com" class="archive-link" target="_blank" rel="noopener">Ars Technica</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="the-verge" checked><a href="https://www.theverge.com" class="archive-link" target="_blank" rel="noopener">The Verge</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="wired" checked><a href="https://www.wired.com" class="archive-link" target="_blank" rel="noopener">Wired</a></div>
            </div>
            <div class="sources-section">
                <div class="sources-section-title">Environment</div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="grist" checked><a href="https://grist.org" class="archive-link" target="_blank" rel="noopener">Grist</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="inside-climate-news" checked><a href="https://insideclimatenews.org" class="archive-link" target="_blank" rel="noopener">Inside Climate News</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="yale-e360" checked><a href="https://e360.yale.edu" class="archive-link" target="_blank" rel="noopener">Yale E360</a></div>
            </div>
            <div class="sources-section">
                <div class="sources-section-title">Local (Omaha / Nebraska)</div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="ketv-omaha"><a href="https://www.ketv.com" class="archive-link" target="_blank" rel="noopener">KETV Omaha</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="nebraska-examiner"><a href="https://nebraskaexaminer.com" class="archive-link" target="_blank" rel="noopener">Nebraska Examiner</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="flatwater-free-press"><a href="https://flatwaterfreepress.org" class="archive-link" target="_blank" rel="noopener">Flatwater Free Press</a></div>
            </div>
            <div class="sources-section">
                <div class="sources-section-title">Libraries & Information Science</div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="american-libraries"><a href="https://americanlibrariesmagazine.org" class="archive-link" target="_blank" rel="noopener">American Libraries Magazine</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="lisnews"><a href="https://lisnews.org" class="archive-link" target="_blank" rel="noopener">LISNews</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="librarian-net"><a href="https://librarian.net" class="archive-link" target="_blank" rel="noopener">librarian.net</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="library-technology-guides"><a href="https://librarytechnology.org" class="archive-link" target="_blank" rel="noopener">Library Technology Guides</a></div>
            </div>
            <div class="sources-section">
                <div class="sources-section-title">Long-Form & Investigative</div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="the-atlantic" checked><a href="https://www.theatlantic.com" class="archive-link" target="_blank" rel="noopener">The Atlantic</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="the-new-yorker" checked><a href="https://www.newyorker.com" class="archive-link" target="_blank" rel="noopener">The New Yorker</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="bellingcat" checked><a href="https://www.bellingcat.com" class="archive-link" target="_blank" rel="noopener">Bellingcat</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="lawfare" checked><a href="https://www.lawfaremedia.org" class="archive-link" target="_blank" rel="noopener">Lawfare</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="propublica" checked><a href="https://www.propublica.org" class="archive-link" target="_blank" rel="noopener">ProPublica</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="foreign-affairs" checked><a href="https://www.foreignaffairs.com" class="archive-link" target="_blank" rel="noopener">Foreign Affairs</a></div>
                <div class="source-filter-row"><input type="checkbox" class="source-filter-check" data-source="foreign-policy" checked><a href="https://foreignpolicy.com" class="archive-link" target="_blank" rel="noopener">Foreign Policy</a></div>
            </div>
        </div>
    </div>
    <div id="past-editions" class="setup-overlay" onclick="if(event.target===this) this.classList.remove('is-visible')">
        <div class="setup-panel" role="dialog" aria-label="Past editions">
            <div class="setup-panel-header">
                <h2 class="setup-panel-title">Past Editions</h2>
                <button class="setup-close" onclick="document.getElementById('past-editions').classList.remove('is-visible')">Close ✕</button>
            </div>
            <div id="archive-list" class="archive-list">
{{ARCHIVE_LIST}}
            </div>
        </div>
    </div>
    <div id="setup-guide" class="setup-overlay" onclick="if(event.target===this) this.classList.remove('is-visible')">
        <div class="setup-panel" role="dialog" aria-label="Reading setup guide">
            <div class="setup-panel-header">
                <h2 class="setup-panel-title">Reading Setup Guide</h2>
                <button class="setup-close" onclick="document.getElementById('setup-guide').classList.remove('is-visible')">Close ✕</button>
            </div>
            <p class="setup-note" style="margin-top: 0; margin-bottom: 1.5rem;">A one-time setup to make articles you open from this site clean, dark, and distraction-free.</p>
            <div class="setup-section">
                <div class="setup-section-title">Enable Automatic Reader Mode</div>
                <p class="setup-note" style="margin-top: 0; margin-bottom: 1rem;">Reader mode strips away ads, sidebars, and visual clutter — showing only the article text and images.</p>
                <div class="setup-device">
                    <div class="setup-device-name">On Mac</div>
                    <div class="setup-step" data-step="1.">Open any article link from this site in Safari</div>
                    <div class="setup-step" data-step="2.">In the menu bar, click <strong>Safari → Settings For This Website</strong></div>
                    <div class="setup-step" data-step="3.">Check <strong>"Use Reader when available"</strong></div>
                    <div class="setup-note">Safari will remember this for each news site. You only need to do it once per domain.</div>
                </div>
                <div class="setup-device">
                    <div class="setup-device-name">On iPhone / iPad</div>
                    <div class="setup-step" data-step="1.">Open <strong>Settings → Apps → Safari → Reader</strong></div>
                    <div class="setup-step" data-step="2.">Turn on <strong>"Other Websites"</strong> to enable it everywhere</div>
                    <div class="setup-note">This turns on Reader mode globally. If a page doesn't have an article, Safari will just show it normally.</div>
                </div>
            </div>
            <hr class="setup-divider">
            <div class="setup-section">
                <div class="setup-section-title">Set Reader Mode to Dark Theme</div>
                <p class="setup-note" style="margin-top: 0; margin-bottom: 1rem;">So articles match this site's dark background — easier on the eyes, especially with migraines.</p>
                <div class="setup-device">
                    <div class="setup-device-name">On Mac</div>
                    <div class="setup-step" data-step="1.">Open any article and activate Reader mode (click the page icon in the address bar)</div>
                    <div class="setup-step" data-step="2.">Click the <strong>aA</strong> button on the right side of the address bar</div>
                    <div class="setup-step" data-step="3.">Select the <strong>dark background</strong> color option</div>
                    <div class="setup-note">You can also adjust font and size here. Safari remembers your choices.</div>
                </div>
                <div class="setup-device">
                    <div class="setup-device-name">On iPhone / iPad</div>
                    <div class="setup-step" data-step="1.">Open an article in Reader mode</div>
                    <div class="setup-step" data-step="2.">Tap the <strong>aA</strong> button in the address bar</div>
                    <div class="setup-step" data-step="3.">Choose the <strong>dark background</strong> color at the bottom</div>
                    <div class="setup-note">This setting sticks across all Reader mode pages.</div>
                </div>
            </div>
            <hr class="setup-divider">
            <div class="setup-section">
                <div class="setup-section-title">How This Site Works</div>
                <div class="setup-step" data-step="·">Each story has a synopsis and a link to the full article</div>
                <div class="setup-step" data-step="·">Click anywhere on a story to open it — it marks itself as read automatically</div>
                <div class="setup-step" data-step="·">Use topic buttons at the top to filter by category</div>
            </div>
        </div>
    </div>
    <div id="privacy-policy" class="setup-overlay" onclick="if(event.target===this) this.classList.remove('is-visible')">
        <div class="setup-panel" role="dialog" aria-label="Privacy policy">
            <div class="setup-panel-header">
                <h2 class="setup-panel-title">Privacy</h2>
                <button class="setup-close" onclick="document.getElementById('privacy-policy').classList.remove('is-visible')">Close ✕</button>
            </div>
            <div class="setup-section">
                <div class="setup-section-title">The Short Version</div>
                <p class="setup-step" data-step="·" style="padding-left: 1.15rem;">This site does not track you. There are no analytics, no user accounts, and no server-side logging of your visits beyond what Cloudflare provides as part of its CDN service.</p>
            </div>
            <hr class="setup-divider">
            <div class="setup-section">
                <div class="setup-section-title">Local Storage (Not Cookies)</div>
                <p class="setup-step" data-step="·" style="padding-left: 1.15rem;">This site uses your browser's <strong>localStorage</strong> to remember two things: which articles you've already read (so they appear dimmed) and your source filter preferences. This data lives entirely on your device — it is never sent to any server. You can clear it at any time through your browser settings.</p>
                <p class="setup-step" data-step="·" style="padding-left: 1.15rem;">Read history is automatically pruned after 30 days. Source filter preferences are kept until you clear them.</p>
            </div>
            <hr class="setup-divider">
            <div class="setup-section">
                <div class="setup-section-title">Cloudflare</div>
                <p class="setup-step" data-step="·" style="padding-left: 1.15rem;">This site is served through <strong>Cloudflare</strong>, which acts as a CDN and security layer. Cloudflare may set its own cookies and collect standard web traffic data (IP addresses, request headers, etc.) as part of its service. This is outside our control. You can read <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener" style="color: var(--accent);">Cloudflare's privacy policy</a> for details.</p>
            </div>
            <hr class="setup-divider">
            <div class="setup-section">
                <div class="setup-section-title">External Links</div>
                <p class="setup-step" data-step="·" style="padding-left: 1.15rem;">When you click through to read a full article, you leave this site and are subject to that publication's own privacy policy. All external links open in a new tab with <code style="font-size: 0.8rem; color: var(--text-secondary); background: var(--bg-surface); padding: 0.1rem 0.3rem; border-radius: 3px;">rel=&quot;noopener&quot;</code> set, which prevents the destination site from accessing this page.</p>
            </div>
            <hr class="setup-divider">
            <div class="setup-section">
                <div class="setup-section-title">Content Generation</div>
                <p class="setup-step" data-step="·" style="padding-left: 1.15rem;">Article summaries on this site are generated using AI (Anthropic's Claude). The AI reads publicly available RSS feeds and writes brief commentaries. No personal data is involved in this process.</p>
            </div>
            <hr class="setup-divider">
            <div class="setup-section">
                <div class="setup-section-title">Contact</div>
                <p class="setup-step" data-step="·" style="padding-left: 1.15rem;">Questions about this site's privacy practices? <a href="#" style="color: var(--accent);" onclick="event.preventDefault(); document.getElementById('privacy-policy').classList.remove('is-visible'); document.getElementById('contact-form').classList.add('is-visible');">Send us a message</a>.</p>
            </div>
        </div>
    </div>
    <div id="contact-form" class="setup-overlay" onclick="if(event.target===this) this.classList.remove('is-visible')">
        <div class="setup-panel" role="dialog" aria-label="Contact form">
            <div class="setup-panel-header">
                <h2 class="setup-panel-title">Contact</h2>
                <button class="setup-close" onclick="document.getElementById('contact-form').classList.remove('is-visible')">Close ✕</button>
            </div>
            <p class="setup-note" style="margin-top: 0; margin-bottom: 1.5rem;">Questions, suggestions, or feedback about the site? Send a message and we'll get back to you.</p>
            <div class="contact-field">
                <label class="contact-label" for="contact-name">Name <span style="color: var(--text-muted);">(optional)</span></label>
                <input type="text" id="contact-name" class="contact-input" autocomplete="name" placeholder="Your name">
            </div>
            <div class="contact-field">
                <label class="contact-label" for="contact-email">Email <span style="color: var(--text-muted);">(optional, for a reply)</span></label>
                <input type="email" id="contact-email" class="contact-input" autocomplete="email" placeholder="you@example.com">
            </div>
            <div class="contact-field">
                <label class="contact-label" for="contact-message">Message</label>
                <textarea id="contact-message" class="contact-textarea" placeholder="What's on your mind?"></textarea>
            </div>
            <div class="hp-field" aria-hidden="true">
                <label for="contact-website">Website</label>
                <input type="text" id="contact-website" name="website" tabindex="-1" autocomplete="off">
            </div>
            <button id="contact-send" class="contact-submit" onclick="sendContactForm()">Send message</button>
            <div id="contact-status" class="contact-status"></div>
        </div>
    </div>
    <script>
        // --- Contact Form ---
        async function sendContactForm() {
            const btn = document.getElementById('contact-send');
            const status = document.getElementById('contact-status');
            const name = document.getElementById('contact-name').value.trim();
            const email = document.getElementById('contact-email').value.trim();
            const message = document.getElementById('contact-message').value.trim();
            const website = document.getElementById('contact-website').value;

            if (!message) {
                status.textContent = 'Please write a message.';
                status.className = 'contact-status is-error';
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Sending...';
            status.textContent = '';
            status.className = 'contact-status';

            try {
                const resp = await fetch('/contact', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, email, message, website })
                });
                const data = await resp.json();
                if (resp.ok) {
                    status.textContent = 'Message sent \u2014 thank you!';
                    status.className = 'contact-status is-success';
                    document.getElementById('contact-name').value = '';
                    document.getElementById('contact-email').value = '';
                    document.getElementById('contact-message').value = '';
                } else {
                    status.textContent = data.error || 'Something went wrong. Please try again.';
                    status.className = 'contact-status is-error';
                }
            } catch (e) {
                status.textContent = 'Could not reach the server. Please try again later.';
                status.className = 'contact-status is-error';
            } finally {
                btn.disabled = false;
                btn.textContent = 'Send message';
            }
        }
    </script>
    <script>
        // --- Read Tracking (localStorage) ---
        const STORAGE_KEY = 'leonne-read-articles';
        const SOURCE_FILTER_KEY = 'leonne-source-filters';

        // Default sources that are OFF for non-Leonne visitors
        const DEFAULT_OFF_SOURCES = [
            'ketv-omaha', 'nebraska-examiner', 'flatwater-free-press',
            'american-libraries', 'lisnews', 'librarian-net', 'library-technology-guides'
        ];

        function getReadArticles() {
            try {
                return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            } catch { return {}; }
        }

        function markRead(articleId) {
            const read = getReadArticles();
            read[articleId] = Date.now();
            const cutoff = Date.now() - (30 * 24 * 60 * 60 * 1000);
            for (const key in read) {
                if (read[key] < cutoff) delete read[key];
            }
            localStorage.setItem(STORAGE_KEY, JSON.stringify(read));
        }

        // --- Source Filtering (localStorage, no expiration) ---
        function getSourceFilters() {
            try {
                const stored = localStorage.getItem(SOURCE_FILTER_KEY);
                if (stored) return JSON.parse(stored);
            } catch {}
            // First visit: build defaults from checkbox HTML state
            const defaults = {};
            document.querySelectorAll('.source-filter-check').forEach(cb => {
                defaults[cb.dataset.source] = cb.checked;
            });
            return defaults;
        }

        function saveSourceFilters(filters) {
            localStorage.setItem(SOURCE_FILTER_KEY, JSON.stringify(filters));
        }

        function applySourceFilters() {
            const filters = getSourceFilters();
            const activeTopic = document.querySelector('.topic-btn.is-active');
            const currentTopic = activeTopic ? activeTopic.dataset.topic : 'all';

            // Apply to articles
            document.querySelectorAll('.entry').forEach(entry => {
                const source = entry.dataset.source;
                const topic = entry.dataset.topic;
                const sourceHidden = source && filters[source] === false;
                const topicHidden = currentTopic !== 'all' && topic !== currentTopic;
                entry.classList.toggle('is-hidden', sourceHidden || topicHidden);
            });

            // Update date groups
            document.querySelectorAll('.date-group').forEach(group => {
                const visible = group.querySelectorAll('.entry:not(.is-hidden)');
                group.classList.toggle('is-empty', visible.length === 0);
            });

            // Update topic nav — hide buttons with zero visible articles
            document.querySelectorAll('.topic-btn').forEach(btn => {
                const topic = btn.dataset.topic;
                if (topic === 'all') {
                    btn.style.display = '';
                    return;
                }
                const hasVisible = Array.from(document.querySelectorAll(`.entry[data-topic="${topic}"]`)).some(entry => {
                    const src = entry.dataset.source;
                    return !src || filters[src] !== false;
                });
                btn.style.display = hasVisible ? '' : 'none';
            });

            // If active topic button got hidden, reset to All
            if (activeTopic && activeTopic.style.display === 'none') {
                document.querySelectorAll('.topic-btn').forEach(b => b.classList.remove('is-active'));
                document.querySelector('.topic-btn[data-topic="all"]').classList.add('is-active');
                applySourceFilters();
            }

            // Sync checkboxes in Sources overlay
            document.querySelectorAll('.source-filter-check').forEach(cb => {
                const key = cb.dataset.source;
                cb.checked = filters[key] !== false;
            });
        }

        // Restore read state on page load
        const readArticles = getReadArticles();
        document.querySelectorAll('.entry').forEach(entry => {
            const id = entry.dataset.articleId;
            const checkbox = entry.querySelector('.read-check');
            if (readArticles[id]) {
                checkbox.checked = true;
                entry.classList.add('is-read');
            }
        });

        // Apply source filters on load
        applySourceFilters();

        // Source filter checkbox changes
        document.querySelectorAll('.source-filter-check').forEach(cb => {
            cb.addEventListener('change', () => {
                const filters = getSourceFilters();
                filters[cb.dataset.source] = cb.checked;
                saveSourceFilters(filters);
                applySourceFilters();
            });
        });

        // Whole entry is clickable
        function openArticle(entry) {
            const link = entry.querySelector('.read-more');
            const url = link ? link.getAttribute('href') : null;
            const id = entry.dataset.articleId;
            const checkbox = entry.querySelector('.read-check');
            checkbox.checked = true;
            entry.classList.add('is-read');
            markRead(id);
            if (url && url !== '#') {
                window.open(url, '_blank');
                window.focus();
            }
        }

        // Checkbox click: toggle read/unread without opening article
        document.querySelectorAll('.read-check').forEach(checkbox => {
            checkbox.addEventListener('click', (e) => {
                e.stopPropagation();
                const entry = checkbox.closest('.entry');
                const id = entry.dataset.articleId;
                if (checkbox.checked) {
                    // Manually checking the box marks as read (without opening link)
                    entry.classList.add('is-read');
                    markRead(id);
                } else {
                    // Unchecking reverts to unread
                    entry.classList.remove('is-read');
                    const read = getReadArticles();
                    delete read[id];
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(read));
                }
            });
        });

        document.querySelectorAll('.entry').forEach(entry => {
            entry.addEventListener('click', (e) => {
                openArticle(entry);
            });
        });

        document.querySelectorAll('.read-more').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
            });
        });

        // Escape key closes overlays
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                document.getElementById('setup-guide').classList.remove('is-visible');
                document.getElementById('past-editions').classList.remove('is-visible');
                document.getElementById('sources-list').classList.remove('is-visible');
                document.getElementById('privacy-policy').classList.remove('is-visible');
                document.getElementById('contact-form').classList.remove('is-visible');
                document.getElementById('support-overlay').classList.remove('is-visible');
                document.getElementById('about-overlay').classList.remove('is-visible');
            }
        });

        // Topic filter buttons
        document.querySelectorAll('.topic-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.topic-btn').forEach(b => b.classList.remove('is-active'));
                btn.classList.add('is-active');
                applySourceFilters();
            });
        });
    </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# EDITORIAL PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the editor of "Leonne's Daily Post," a curated news site built for a librarian named Leonne who has ADHD and chronic migraines. The site is designed to be calm, focused, and distraction-free.

Your job is to take a JSON list of candidate articles scraped from RSS feeds and produce the article entries HTML for today's edition.

EDITORIAL GUIDELINES:
- Select 35–50 of the most interesting, important, or surprising stories
- Prioritize: stories that affect daily life, surprising findings, underreported topics, and stories relevant to librarians/information science
- Leonne prefers highly neutral coverage — favor BBC, Reuters, AP, and NPR when available
- Include at least 1–2 local stories (Omaha/Bellevue/Nebraska) if available
- Include at least 1 library/information science story if available
- Include long-form pieces from The New Yorker, The Atlantic, Bellingcat, or Lawfare when they're substantive
- Leonne is LEAST interested in celebrity news, sports, and culture/entertainment
- Skip stories that are just brief news alerts without substance

FOR EACH SELECTED STORY, produce:
1. A category tag (use the category_label from the article data)
2. The headline (use the article's title, clean up any ALL CAPS or clickbait)
3. A 1–2 sentence commentary in this voice: thoughtful, curious, understated — like a smart friend pointing out something worth reading. Not breathless, not dry. Occasionally witty. Never condescending.
4. A "Continue reading at [Source]" link

GROUP articles by date:
- Today's date group first
- Yesterday second
- Older third (if any)
- Use the article's published date to determine grouping
- Format date labels like: "Saturday, February 15"

OUTPUT FORMAT:
Return ONLY the HTML that goes between <main> and </main> tags. This means date-group sections containing article entries. No other text, explanation, or markdown. Just the raw HTML.

Each article entry MUST follow this exact structure:

<article class="entry" data-topic="CATEGORY_KEY" data-source="SOURCE_KEY" data-article-id="UNIQUE_SLUG">
    <div class="entry-top-row">
        <input type="checkbox" class="read-check" aria-label="Mark as read">
        <div class="entry-content">
            <div class="entry-tag">CATEGORY_LABEL</div>
            <div class="entry-header">
                <span class="entry-title">HEADLINE</span>
            </div>
            <p class="entry-commentary">YOUR COMMENTARY</p>
            <a href="ARTICLE_URL" class="read-more" target="_blank" rel="noopener">Continue reading at SOURCE <span>→</span></a>
        </div>
    </div>
</article>

IMPORTANT RULES:
- data-topic must use the category key (e.g., "world", "us", "local", "science", "tech", "environment", "libraries", "longform"), NOT the label
- data-source must use one of the exact source keys listed below — this is critical for filtering
- data-article-id must be a unique slug derived from the source and title (e.g., "bbc-navalny-mother", "npr-shutdown-deal"), lowercase with hyphens, no spaces
- Do NOT include an entry-source span — the source only appears in the "Continue reading at SOURCE" link
- Do NOT include excerpt paragraphs or expand/collapse markup

SOURCE KEYS (use these exact values for data-source):
- bbc-news, npr, ap, reuters, al-jazeera
- the-hill, pbs-newshour
- nature, quanta-magazine
- ars-technica, the-verge, wired
- grist, inside-climate-news, yale-e360
- ketv-omaha, nebraska-examiner, flatwater-free-press
- american-libraries, lisnews, librarian-net, library-technology-guides
- the-atlantic, the-new-yorker, bellingcat, lawfare, propublica, foreign-affairs, foreign-policy
If a story comes from a source not in this list, create a lowercase hyphenated key from the source name (e.g., "washington-post")."""


# ---------------------------------------------------------------------------
# STEP 1 PROMPT: Haiku enrichment (summaries for all candidates)
# ---------------------------------------------------------------------------

ENRICHMENT_PROMPT = """You are a newsroom assistant for "Leonne's Daily Post," a curated news site for a librarian.

Your job is to write a brief 1–2 sentence summary/commentary for each article in the input list. These summaries will help an editor decide which stories to include in today's edition.

For each article, write a summary that:
- Captures the core news or insight in 1–2 sentences
- Is written in a thoughtful, curious, understated tone — like a smart friend pointing out something worth reading
- Highlights why this story matters or what makes it interesting
- Is NOT breathless, clickbaity, or dry

OUTPUT FORMAT:
Return a JSON array where each element has:
- "index": the article's position in the input array (0-based)
- "summary": your 1–2 sentence commentary

Return ONLY valid JSON. No explanation, no markdown fences, just the array."""


# ---------------------------------------------------------------------------
# STEP 2 PROMPT: Sonnet editorial selection
# ---------------------------------------------------------------------------

SELECTION_PROMPT = """You are the editor of "Leonne's Daily Post," a curated news site built for a librarian named Leonne who has ADHD and chronic migraines.

Your job is to review a list of candidate articles (each with a summary written by your assistant) and select the 35–50 best stories for today's edition.

EDITORIAL GUIDELINES:
- Select 35–50 of the most interesting, important, or surprising stories
- Prioritize: stories that affect daily life, surprising findings, underreported topics, and stories relevant to librarians/information science
- Leonne prefers highly neutral coverage — favor BBC, Reuters, AP, NPR, and PBS NewsHour when available
- Include at least 1–2 local stories (Omaha/Bellevue/Nebraska) if available
- Include at least 1 library/information science story if available
- Include long-form pieces from The New Yorker, The Atlantic, Bellingcat, ProPublica, Foreign Affairs, Foreign Policy, or Lawfare when they're substantive
- Leonne is LEAST interested in celebrity news, sports, and culture/entertainment
- Skip stories that are just brief news alerts without substance
- Ensure good category diversity — don't let one category dominate
- When multiple sources cover the same story, pick the best source (prefer neutral wire services)

OUTPUT FORMAT:
Return a JSON array of integers — the indices (0-based) of your selected articles, ordered by editorial importance (most important first).

Example: [42, 7, 103, 15, 88, ...]

Return ONLY the JSON array. No explanation, no markdown fences."""


def strip_code_fences(text):
    """Remove markdown code fences from model output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def generate_entries(articles_json: str, api_key: str) -> str:
    """Three-step pipeline: Haiku enriches, Sonnet selects, assemble HTML."""
    client = anthropic.Anthropic(api_key=api_key)
    articles_data = json.loads(articles_json)
    articles_list = articles_data.get("articles", [])

    # --- Step 1: Haiku writes summaries for all candidates ---
    print(f"  Step 1: Haiku enriching {len(articles_list)} articles...", file=sys.stderr)

    # Build a compact version for enrichment (just index, title, source, excerpt)
    compact_articles = []
    for i, a in enumerate(articles_list):
        compact_articles.append({
            "index": i,
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "category": a.get("category", ""),
            "excerpt": a.get("excerpt", "")[:500],  # Truncate long excerpts
        })
    compact_json = json.dumps(compact_articles, ensure_ascii=False)

    enrichment_text = ""
    with client.messages.stream(
        model=ENRICHMENT_MODEL,
        max_tokens=64000,
        system=[
            {
                "type": "text",
                "text": ENRICHMENT_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Write summaries for each of these {len(compact_articles)} articles.\n\n{compact_json}"
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            enrichment_text += text

    # Parse summaries
    try:
        summaries_list = json.loads(strip_code_fences(enrichment_text))
        summary_map = {s["index"]: s["summary"] for s in summaries_list}
        print(f"  Haiku wrote {len(summary_map)} summaries", file=sys.stderr)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  ⚠ Haiku enrichment parse failed: {e}", file=sys.stderr)
        print(f"  Falling back to single-pass Haiku...", file=sys.stderr)
        return generate_entries_fallback(articles_json, api_key)

    # --- Step 2: Sonnet selects the best stories ---
    print("  Step 2: Sonnet editorial selection...", file=sys.stderr)

    # Build enriched article list for Sonnet
    enriched_articles = []
    for i, a in enumerate(articles_list):
        enriched_articles.append({
            "index": i,
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "category": a.get("category", ""),
            "category_label": a.get("category_label", ""),
            "summary": summary_map.get(i, ""),
            "published": a.get("published", ""),
        })
    enriched_json = json.dumps(enriched_articles, ensure_ascii=False)

    selection_text = ""
    with client.messages.stream(
        model=SELECTION_MODEL,
        max_tokens=4000,
        system=[
            {
                "type": "text",
                "text": SELECTION_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Here are today's {len(enriched_articles)} candidate articles with summaries. Select the best 35–50.\n\n{enriched_json}"
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            selection_text += text

    try:
        selected_indices = json.loads(strip_code_fences(selection_text))
        print(f"  Sonnet selected {len(selected_indices)} stories", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"  ⚠ Sonnet selection parse failed: {e}", file=sys.stderr)
        print(f"  Falling back to single-pass Haiku...", file=sys.stderr)
        return generate_entries_fallback(articles_json, api_key)

    # --- Step 3: Assemble HTML from selected articles + Haiku summaries ---
    print("  Step 3: Assembling HTML...", file=sys.stderr)

    # Group selected articles by date
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    date_groups = {}  # date_label -> list of article HTML strings

    for idx in selected_indices:
        if idx < 0 or idx >= len(articles_list):
            continue

        a = articles_list[idx]
        summary = summary_map.get(idx, "")

        # Determine date group
        pub = a.get("published", "")
        if pub:
            try:
                pub_date = pub[:10]  # YYYY-MM-DD
            except Exception:
                pub_date = today_str
        else:
            pub_date = today_str

        if pub_date == today_str:
            date_label = now.strftime("%A, %B %-d")
        elif pub_date == yesterday_str:
            date_label = yesterday.strftime("%A, %B %-d")
        else:
            try:
                d = datetime.fromisoformat(pub[:10])
                date_label = d.strftime("%A, %B %-d")
            except Exception:
                date_label = now.strftime("%A, %B %-d")

        if date_label not in date_groups:
            date_groups[date_label] = []

        # Build source key
        source = a.get("source", "")
        source_key = source.lower().replace(" ", "-").replace(".", "").replace("'", "")
        # Normalize known source keys
        source_key_map = {
            "bbc-news": "bbc-news", "bbc-us": "bbc-news", "bbc-science": "bbc-news",
            "npr-world": "npr", "npr-us": "npr", "npr-politics": "npr",
            "npr-science": "npr", "npr-technology": "npr",
            "associated-press": "ap",
            "ars-technica": "ars-technica",
            "the-verge": "the-verge",
            "the-atlantic": "the-atlantic",
            "the-new-yorker": "the-new-yorker",
            "the-hill": "the-hill",
            "pbs-newshour": "pbs-newshour",
            "al-jazeera": "al-jazeera",
            "inside-climate-news": "inside-climate-news",
            "yale-e360": "yale-e360",
            "ketv-omaha": "ketv-omaha",
            "nebraska-examiner": "nebraska-examiner",
            "flatwater-free-press": "flatwater-free-press",
            "american-libraries": "american-libraries",
            "library-technology-guides": "library-technology-guides",
            "foreign-affairs": "foreign-affairs",
            "foreign-policy": "foreign-policy",
        }
        source_key = source_key_map.get(source_key, source_key)

        # Build article ID slug
        title_slug = re.sub(r"[^\w\s-]", "", a.get("title", "").lower())
        title_slug = re.sub(r"\s+", "-", title_slug)[:50].rstrip("-")
        article_id = f"{source_key}-{title_slug}"

        category = a.get("category", "us")
        category_label = html_lib.escape(a.get("category_label", "U.S."))
        title = html_lib.escape(a.get("title", ""))
        summary = html_lib.escape(summary)
        link = html_lib.escape(a.get("link", "#"))
        source = html_lib.escape(source)

        entry_html = f"""            <article class="entry" data-topic="{category}" data-source="{source_key}" data-article-id="{article_id}">
                <div class="entry-top-row">
                    <input type="checkbox" class="read-check" aria-label="Mark as read">
                    <div class="entry-content">
                        <div class="entry-tag">{category_label}</div>
                        <div class="entry-header">
                            <span class="entry-title">{title}</span>
                        </div>
                        <p class="entry-commentary">{summary}</p>
                        <a href="{link}" class="read-more" target="_blank" rel="noopener">Continue reading at {source} <span>→</span></a>
                    </div>
                </div>
            </article>"""

        date_groups[date_label].append(entry_html)

    # Assemble date groups into final HTML
    # Order: today first, then yesterday, then older
    ordered_labels = []
    today_label = now.strftime("%A, %B %-d")
    yesterday_label = yesterday.strftime("%A, %B %-d")
    if today_label in date_groups:
        ordered_labels.append(today_label)
    if yesterday_label in date_groups and yesterday_label != today_label:
        ordered_labels.append(yesterday_label)
    for label in date_groups:
        if label not in ordered_labels:
            ordered_labels.append(label)

    html_parts = []
    for label in ordered_labels:
        entries = date_groups[label]
        html_parts.append(f'        <section class="date-group">')
        html_parts.append(f'            <div class="date-label">{label}</div>')
        html_parts.extend(entries)
        html_parts.append(f'        </section>')

    result = "\n".join(html_parts)
    print(f"  Assembled {sum(len(e) for e in date_groups.values())} entries", file=sys.stderr)
    return result


def generate_entries_fallback(articles_json: str, api_key: str) -> str:
    """Fallback: single-pass Haiku if the pipeline fails."""
    client = anthropic.Anthropic(api_key=api_key)

    response_text = ""
    with client.messages.stream(
        model=FALLBACK_MODEL,
        max_tokens=48000,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Here are today's candidate articles. Select the best stories and generate the HTML entries.\n\n{articles_json}"
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            response_text += text

    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


# ---------------------------------------------------------------------------
# ARCHIVE LIST BUILDER
# ---------------------------------------------------------------------------

def build_archive_list(archive_dir: str) -> str:
    """Scan archive directory for past editions and return HTML links."""
    if not archive_dir or not os.path.isdir(archive_dir):
        return '                <p class="archive-empty">No past editions yet.</p>'

    # Find all edition HTML files
    files = glob.glob(os.path.join(archive_dir, "edition_*.html"))
    if not files:
        return '                <p class="archive-empty">No past editions yet.</p>'

    # Parse dates from filenames: edition_YYYY-MM-DD_HHMMSS.html
    editions = []
    for f in files:
        basename = os.path.basename(f)
        match = re.match(r"edition_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.html", basename)
        if match:
            y, m, d, t = match.groups()
            try:
                dt = datetime(int(y), int(m), int(d),
                              int(t[:2]), int(t[2:4]), int(t[4:6]))
                editions.append((dt, basename))
            except ValueError:
                continue

    # Sort newest first
    editions.sort(key=lambda x: x[0], reverse=True)

    # Build HTML links
    lines = []
    for dt, basename in editions:
        label = dt.strftime("%A, %B %-d, %Y")
        lines.append(f'                <a href="/archive/{basename}" class="archive-link">{label}</a>')

    return "\n".join(lines)


def build_html(entries_html: str, archive_dir: str = None) -> str:
    """Insert the generated entries into the HTML template."""
    now = datetime.now()
    date_str = now.strftime("%A, %B %-d, %Y")

    html = HTML_TEMPLATE.replace("{{DATE}}", date_str)
    html = html.replace("{{ENTRIES}}", entries_html)
    html = html.replace("{{ARCHIVE_LIST}}", build_archive_list(archive_dir))
    html = html.replace("{{STRIPE_PRICING_TABLE_ID}}", STRIPE_PRICING_TABLE_ID)
    html = html.replace("{{STRIPE_PUBLISHABLE_KEY}}", STRIPE_PUBLISHABLE_KEY)

    return html


def deploy(html: str, deploy_url: str, deploy_token: str) -> bool:
    """POST the generated HTML to the deploy endpoint."""
    try:
        response = requests.post(
            deploy_url,
            data=html.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {deploy_token}",
                "Content-Type": "text/html",
            },
            timeout=30,
        )
        if response.status_code == 200:
            result = response.json()
            print(f"  Deployed: {result.get('message', 'ok')}", file=sys.stderr)
            return True
        else:
            print(f"  Deploy failed ({response.status_code}): {response.text}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"  Deploy error: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate Leonne's Daily Post from scraped articles"
    )
    parser.add_argument(
        "-i", "--input", required=True,
        help="Path to articles.json from scraper"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output HTML file path (default: stdout)"
    )
    parser.add_argument(
        "--archive-dir",
        help="Path to archive directory for past editions list"
    )
    parser.add_argument(
        "--deploy",
        help="Deploy URL (e.g., https://leonne.net/deploy)"
    )
    parser.add_argument(
        "--deploy-token",
        help="Deploy auth token (or set DEPLOY_TOKEN env var)"
    )
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)"
    )
    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: Set ANTHROPIC_API_KEY env var or use --api-key", file=sys.stderr)
        sys.exit(1)

    # Load articles
    print("Loading articles...", file=sys.stderr)
    with open(args.input, "r", encoding="utf-8") as f:
        articles_data = f.read()

    articles = json.loads(articles_data)
    print(f"  {articles['article_count']} articles loaded", file=sys.stderr)

    # Generate editorial entries
    print("Generating editorial content...", file=sys.stderr)
    entries_html = generate_entries(articles_data, api_key)
    print(f"  Generated {len(entries_html)} chars of HTML", file=sys.stderr)

    # Build final HTML
    print("Assembling page...", file=sys.stderr)
    final_html = build_html(entries_html, args.archive_dir)
    print(f"  Final page: {len(final_html)} chars", file=sys.stderr)

    # Save locally
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(final_html)
        print(f"  Saved to {args.output}", file=sys.stderr)
    else:
        print(final_html)

    # Deploy if requested
    if args.deploy:
        deploy_token = args.deploy_token or os.environ.get("DEPLOY_TOKEN")
        if not deploy_token:
            print("Error: Set DEPLOY_TOKEN env var or use --deploy-token", file=sys.stderr)
            sys.exit(1)
        print("Deploying...", file=sys.stderr)
        deploy(final_html, args.deploy, deploy_token)

    print("Done!", file=sys.stderr)


if __name__ == "__main__":
    main()
