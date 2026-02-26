"""
Configuration for your Daily Post instance.

All site-specific settings live here. When forking this project,
this is the main file you'll edit to make it your own.

Secrets (API keys, tokens) should go in environment variables or a .env file.
This file is for non-secret configuration only.
"""

import os

# ---------------------------------------------------------------------------
# SITE IDENTITY
# ---------------------------------------------------------------------------

SITE_NAME = os.environ.get("SITE_NAME", "Leonne's Daily Post")
SITE_TAGLINE = os.environ.get("SITE_TAGLINE", "Curated with love for Leonne")

# Used in editorial prompts to personalize the AI's tone and selection
READER_NAME = os.environ.get("READER_NAME", "Leonne")
READER_DESCRIPTION = os.environ.get(
    "READER_DESCRIPTION",
    "a librarian with ADHD and chronic migraines"
)

# ---------------------------------------------------------------------------
# STRIPE (Donations)
# ---------------------------------------------------------------------------
# Publishable keys are safe to expose in HTML (they're designed for it),
# but keeping them here means forks don't accidentally point at your account.

STRIPE_PRICING_TABLE_ID = os.environ.get("STRIPE_PRICING_TABLE_ID", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

# ---------------------------------------------------------------------------
# CONTACT
# ---------------------------------------------------------------------------

CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")

# ---------------------------------------------------------------------------
# SERVER PATHS (adjust for your deployment)
# ---------------------------------------------------------------------------

WEB_ROOT = os.environ.get("WEB_ROOT", "/var/www/leonne.net")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/var/www/leonne.net/archive")
DEPLOY_PORT = int(os.environ.get("PORT", "8472"))
PIPELINE_SCRIPT = os.environ.get(
    "PIPELINE_SCRIPT", "/opt/leonne-deploy/run_pipeline.sh"
)

# ---------------------------------------------------------------------------
# EDITORIAL SETTINGS
# ---------------------------------------------------------------------------

# How many stories the AI should select per edition
STORY_COUNT_MIN = int(os.environ.get("STORY_COUNT_MIN", "35"))
STORY_COUNT_MAX = int(os.environ.get("STORY_COUNT_MAX", "50"))

# Models used in the editorial pipeline
ENRICHMENT_MODEL = os.environ.get("ENRICHMENT_MODEL", "claude-haiku-4-5-20251001")
SELECTION_MODEL = os.environ.get("SELECTION_MODEL", "claude-sonnet-4-5-20250929")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "claude-haiku-4-5-20251001")

# ---------------------------------------------------------------------------
# LOCAL SOURCES
# ---------------------------------------------------------------------------
# These sources are hidden by default for new visitors (shown for the
# primary reader). Edit this list to match your own local area.

DEFAULT_OFF_SOURCES = [
    "ketv-omaha", "nebraska-examiner", "flatwater-free-press",
    "american-libraries", "lisnews", "librarian-net", "library-technology-guides",
]

# ---------------------------------------------------------------------------
# CLOUDFLARE (cache purging)
# ---------------------------------------------------------------------------

SITE_URL = os.environ.get("SITE_URL", "https://leonne.net")
CLOUDFLARE_ZONE_ID = os.environ.get("CLOUDFLARE_ZONE_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
