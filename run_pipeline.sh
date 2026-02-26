#!/bin/bash
# Leonne's Daily Post — Full Pipeline Runner
# Runs scrape → generate → deploy → cache purge in sequence.
# Called by the /generate endpoint in deploy_server.py
#
# Usage: ./run_pipeline.sh
# Exit codes: 0 = success, 1 = scraper failed, 2 = generator failed

set -euo pipefail

WORKDIR="/opt/leonne-deploy"
VENV="$WORKDIR/venv/bin/python3"
LOGFILE="$WORKDIR/logs/pipeline-$(date +%Y%m%d-%H%M%S).log"
ARCHIVE_DIR="/var/www/leonne.net/archive"

mkdir -p "$WORKDIR/logs"

echo "=== Pipeline started at $(date) ===" | tee "$LOGFILE"

# Step 1a: Scrape RSS feeds
echo "→ Scraping feeds..." | tee -a "$LOGFILE"
python3 "$WORKDIR/scraper.py" -o "$WORKDIR/articles.json" --hours 28 2>&1 | tee -a "$LOGFILE"

if [ ! -s "$WORKDIR/articles.json" ]; then
    echo "✗ Scraper produced no output" | tee -a "$LOGFILE"
    exit 1
fi

# Step 1b: Parse AP emails and merge into articles pool
echo "→ Parsing AP emails..." | tee -a "$LOGFILE"
python3 "$WORKDIR/parse_ap_emails.py" -o "$WORKDIR/ap_articles.json" --hours 28 2>&1 | tee -a "$LOGFILE"

if [ -s "$WORKDIR/ap_articles.json" ]; then
    echo "→ Merging AP email articles..." | tee -a "$LOGFILE"
    python3 "$WORKDIR/merge_articles.py" \
        "$WORKDIR/articles.json" \
        "$WORKDIR/ap_articles.json" \
        -o "$WORKDIR/articles.json" \
        2>&1 | tee -a "$LOGFILE"
else
    echo "  (No AP email articles to merge)" | tee -a "$LOGFILE"
fi

# Step 2: Generate + Deploy
echo "→ Generating edition..." | tee -a "$LOGFILE"
$VENV "$WORKDIR/generate.py" \
    -i "$WORKDIR/articles.json" \
    -o "$WORKDIR/index.html" \
    --archive-dir "$ARCHIVE_DIR" \
    --deploy "http://localhost:8472/deploy" \
    --deploy-token "$DEPLOY_TOKEN" \
    2>&1 | tee -a "$LOGFILE"

if [ $? -ne 0 ]; then
    echo "✗ Generator failed" | tee -a "$LOGFILE"
    exit 2
fi

# Step 3: Purge Cloudflare cache
echo "→ Purging Cloudflare cache..." | tee -a "$LOGFILE"
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/purge_cache" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"files":["https://leonne.net/","https://leonne.net/index.html"]}' \
    | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"
echo "✓ Cache purged" | tee -a "$LOGFILE"

echo "=== Pipeline finished at $(date) ===" | tee -a "$LOGFILE"

# Keep only last 14 days of logs
find "$WORKDIR/logs" -name "pipeline-*.log" -mtime +14 -delete 2>/dev/null || true
