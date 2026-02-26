# Leonne's Daily Post

A calm, curated daily news digest — built for people who want to stay informed without the doomscroll, visual clutter, and distracting ads of mainstream news sites.

Leonne's Daily Post uses AI to scrape RSS feeds from dozens of trusted sources, select the most important stories, write brief commentaries, and assemble them into a clean, accessible single-page edition every morning. No algorithms, no tracking, no noise. You cna view the latest edition at https://leonne.net.

## How It Works

The editorial pipeline runs in three stages:

1. **Scrape** — `scraper.py` pulls articles from 30+ RSS feeds (wire services, public media, science, tech, environment, local news, long-form journalism). `parse_ap_emails.py` supplements this with AP News alerts parsed from email via IMAP.
2. **Curate** — `generate.py` runs a two-model AI pipeline: Claude Haiku writes summaries for all candidates, then Claude Sonnet selects the best 35–50 stories based on editorial guidelines.
3. **Publish** — The selected stories are assembled into a single HTML page and deployed to your web server. A Cloudflare cache purge ensures readers see the new edition immediately.

A cron job runs this daily at 6 AM, or the reader can trigger it on-demand via an iOS Shortcut.

## What You Get

- A single static HTML page with curated stories, grouped by date
- Topic filtering (World, U.S., Science, Tech, Environment, Local, Libraries, Long Read)
- Source filtering (toggle individual sources on/off)
- Read tracking via localStorage (no server-side tracking)
- Past editions archive
- Donation support via Stripe (optional)
- Contact form with spam protection
- Privacy-respecting design (no analytics, no cookies, no user accounts)

## Quick Start

### Prerequisites

- A VPS or server (Ubuntu recommended)
- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
- Caddy (or nginx) as a reverse proxy
- A domain name

### Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/daily-post.git
cd daily-post

# Install Python dependencies
pip3 install anthropic feedparser flask requests

# Copy and edit the environment config
cp .env.example .env
nano .env  # Fill in your API keys and settings

# Edit config.py to personalize your instance
nano config.py  # Change SITE_NAME, READER_NAME, etc.

# Edit the FEEDS list in scraper.py to add/remove sources
nano scraper.py

# Test the scraper
python3 scraper.py -o articles.json --hours 48

# Test generation
python3 generate.py -i articles.json -o index.html

# Open index.html in a browser to preview
```

### Deployment

See `SHORTCUT_INSTRUCTIONS.md` for details on setting up the systemd service, Caddy reverse proxy, cron job, and iOS Shortcut.

The key environment variables you'll need on the server:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | AI editorial pipeline |
| `DEPLOY_TOKEN` | Authentication for the deploy endpoint |
| `IMAP_USER` / `IMAP_TOKEN` | AP email parsing (optional) |
| `CONTACT_EMAIL` | Where contact form messages go |
| `CLOUDFLARE_ZONE_ID` / `CLOUDFLARE_API_TOKEN` | Cache purging (optional) |
| `STRIPE_PRICING_TABLE_ID` / `STRIPE_PUBLISHABLE_KEY` | Donations (optional) |

See `.env.example` for the full list.

## Making It Yours

This project was built for a specific person — a librarian in Omaha, Nebraska. To make it your own:

1. **`config.py`** — Change the site name, reader name, tagline, and other identity settings
2. **`scraper.py`** — Edit the `FEEDS` list to add your local news sources and remove ones that aren't relevant to your reader
3. **`generate.py`** — The editorial prompts in `SYSTEM_PROMPT`, `ENRICHMENT_PROMPT`, and `SELECTION_PROMPT` describe what kind of stories to prioritize. Adjust these to match your reader's interests.
4. **HTML template** — The template inside `generate.py` contains the full page layout. Update the site name, sources list, about text, and footer to match your instance.

## Cost

Each daily generation costs approximately **$0.09** in Anthropic API usage (Haiku for summaries + Sonnet for selection). That's roughly **$2.70/month**.

## Project Structure

```
├── config.py              # Site identity and configuration
├── scraper.py             # RSS feed scraper
├── parse_ap_emails.py     # AP News email parser (IMAP)
├── merge_articles.py      # Merges article sources
├── generate.py            # AI editorial pipeline + HTML assembly
├── deploy_server.py       # Flask server for deploy/generate/contact
├── run_pipeline.sh        # Full pipeline orchestrator
├── cron_generate.sh       # Cron wrapper
├── SHORTCUT_INSTRUCTIONS.md # iOS Shortcut setup guide
├── .env.example           # Environment variable template
└── LICENSE                # AGPL-3.0
```

## Origin Story

This project was built for Leonne — a librarian with ADHD and chronic migraines who wanted a better way to keep up with the world. Traditional news sites, with their autoplay video, pop-ups, infinite scroll, and visual noise, made staying informed physically painful.

The result is a calm daily digest: a handful of stories worth reading, presented in a clean, dark-mode format with no distractions. It's built with accessibility and low-stimulation design as first principles.

If it helps you or someone you care about, that's a win.

## License

This project is released under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

This means you're free to use, modify, and share the code — but if you run a modified version as a network service, you must make your source code available to users. All derivatives must also be licensed under AGPL-3.0.

**If you'd like to use this in a commercial context, please reach out.**

## Contributing

Issues, suggestions, and pull requests are welcome. If you build your own Daily Post for someone you care about, I'd love to hear about it.
