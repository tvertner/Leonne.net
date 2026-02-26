#!/usr/bin/env python3
"""
Leonne's Daily Post — Deploy & Generate Server
Accepts POST requests with generated HTML and writes to web root.
Also provides a /generate endpoint to trigger the full pipeline.
Keeps timestamped backups of previous editions.

Usage:
    python3 deploy_server.py

Environment variables:
    DEPLOY_TOKEN    — Shared secret for authenticating requests
    ANTHROPIC_API_KEY — API key (needed for /generate pipeline)
    WEB_ROOT        — Path to serve files from (default: /var/www/leonne.net)
    BACKUP_DIR      — Path for edition backups (default: /var/www/leonne.net/archive)
    PORT            — Port to listen on (default: 8472)
"""

import os
import smtplib
import sys
import subprocess
import threading
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("Flask not installed. Run: pip3 install flask")
    sys.exit(1)

app = Flask(__name__)

# Configuration from environment
DEPLOY_TOKEN = os.environ.get("DEPLOY_TOKEN", "CHANGE_ME_TO_A_LONG_RANDOM_STRING")
WEB_ROOT = Path(os.environ.get("WEB_ROOT", "/var/www/leonne.net"))
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/var/www/leonne.net/archive"))
PORT = int(os.environ.get("PORT", 8472))
PIPELINE_SCRIPT = "/opt/leonne-deploy/run_pipeline.sh"

# Track whether a generation is already in progress
generation_lock = threading.Lock()
generation_status = {"running": False, "last_run": None, "last_result": None}


@app.route("/deploy", methods=["POST"])
def deploy():
    # Authenticate
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != DEPLOY_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    # Get the HTML content
    html = request.get_data(as_text=True)
    if not html or len(html.strip()) < 100:
        return jsonify({"error": "No HTML content or content too short"}), 400

    try:
        # Ensure directories exist
        WEB_ROOT.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        index_path = WEB_ROOT / "index.html"

        # Backup current edition if it exists
        if index_path.exists():
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            backup_path = BACKUP_DIR / f"edition_{timestamp}.html"
            index_path.rename(backup_path)

            # Keep only the last 30 backups
            backups = sorted(BACKUP_DIR.glob("edition_*.html"))
            for old in backups[:-30]:
                old.unlink()

        # Write new edition
        index_path.write_text(html, encoding="utf-8")

        return jsonify({
            "status": "ok",
            "message": "Edition deployed",
            "timestamp": datetime.now().isoformat()
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate", methods=["POST"])
def generate():
    """Trigger the full pipeline: scrape -> generate -> deploy."""
    # Authenticate
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != DEPLOY_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    # Don't allow concurrent runs
    if generation_status["running"]:
        return jsonify({
            "status": "busy",
            "message": "A generation is already in progress",
            "started_at": generation_status["last_run"]
        }), 409

    # Run pipeline in background thread so the HTTP response returns immediately
    def run_pipeline():
        generation_status["running"] = True
        generation_status["last_run"] = datetime.now().isoformat()
        try:
            env = os.environ.copy()
            result = subprocess.run(
                ["bash", PIPELINE_SCRIPT],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                env=env,
                cwd="/opt/leonne-deploy"
            )
            generation_status["last_result"] = {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "finished_at": datetime.now().isoformat(),
                "stdout_tail": result.stdout[-500:] if result.stdout else "",
                "stderr_tail": result.stderr[-500:] if result.stderr else "",
            }
        except subprocess.TimeoutExpired:
            generation_status["last_result"] = {
                "success": False,
                "error": "Pipeline timed out after 5 minutes",
                "finished_at": datetime.now().isoformat()
            }
        except Exception as e:
            generation_status["last_result"] = {
                "success": False,
                "error": str(e),
                "finished_at": datetime.now().isoformat()
            }
        finally:
            generation_status["running"] = False

    thread = threading.Thread(target=run_pipeline)
    thread.start()

    return jsonify({
        "status": "started",
        "message": "Edition generation started. Check /generate/status for progress.",
        "started_at": generation_status["last_run"]
    }), 202


@app.route("/generate/status", methods=["GET"])
def generate_status():
    """Check the status of the last generation run."""
    # Authenticate
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != DEPLOY_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify({
        "running": generation_status["running"],
        "last_run": generation_status["last_run"],
        "last_result": generation_status["last_result"]
    })


@app.route("/generate/done", methods=["GET"])
def generate_done():
    """Simple Shortcuts-friendly status: returns plain text 'yes', 'no', or 'error'."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != DEPLOY_TOKEN:
        return "unauthorized", 401, {"Content-Type": "text/plain"}

    if generation_status["running"]:
        return "no", 200, {"Content-Type": "text/plain"}

    if generation_status["last_result"] and generation_status["last_result"].get("success"):
        return "yes", 200, {"Content-Type": "text/plain"}

    return "error", 200, {"Content-Type": "text/plain"}


@app.route("/deploy-file", methods=["POST"])
def deploy_file():
    """Deploy a file to the working directory (/opt/leonne-deploy/).
    Expects JSON: {"filename": "...", "content": "..."}
    Only allows .py and .sh files within the working directory."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != DEPLOY_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data or "filename" not in data or "content" not in data:
        return jsonify({"error": "Missing filename or content"}), 400

    filename = data["filename"]
    content = data["content"]

    # Security: only allow safe filenames in the working directory
    if '/' in filename or '..' in filename:
        return jsonify({"error": "Invalid filename"}), 400
    if not filename.endswith(('.py', '.sh')):
        return jsonify({"error": "Only .py and .sh files allowed"}), 400

    target = Path("/opt/leonne-deploy") / filename
    try:
        target.write_text(content, encoding="utf-8")
        if filename.endswith('.sh'):
            target.chmod(0o755)
        return jsonify({
            "status": "ok",
            "file": str(target),
            "size": len(content)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# CONTACT FORM
# ---------------------------------------------------------------------------

# Rate limiting: track submissions by IP
contact_timestamps = {}  # ip -> list of timestamps
CONTACT_RATE_LIMIT = 3  # max submissions per hour
CONTACT_RECIPIENT = os.environ.get("CONTACT_EMAIL", "")


@app.route("/contact", methods=["POST"])
def contact():
    """Handle contact form submissions. Sends email via Gmail SMTP."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    # Honeypot check — if the hidden 'website' field is filled, it's a bot
    if data.get("website", ""):
        # Silently accept to not tip off the bot
        return jsonify({"status": "ok", "message": "Message sent"}), 200

    name = (data.get("name") or "").strip()[:200]
    email_addr = (data.get("email") or "").strip()[:200]
    message = (data.get("message") or "").strip()[:5000]

    if not message:
        return jsonify({"error": "Message is required"}), 400

    # Basic rate limiting by IP
    ip = request.remote_addr
    now = datetime.now()
    if ip in contact_timestamps:
        # Prune old entries
        contact_timestamps[ip] = [
            t for t in contact_timestamps[ip]
            if (now - t).total_seconds() < 3600
        ]
        if len(contact_timestamps[ip]) >= CONTACT_RATE_LIMIT:
            return jsonify({"error": "Too many messages. Please try again later."}), 429
    else:
        contact_timestamps[ip] = []
    contact_timestamps[ip].append(now)

    # Build and send email
    imap_user = os.environ.get("IMAP_USER")
    imap_token = os.environ.get("IMAP_TOKEN")

    if not imap_user or not imap_token:
        return jsonify({"error": "Mail not configured"}), 500

    reply_to = email_addr if email_addr else None
    sender_info = f"{name} ({email_addr})" if name and email_addr else name or email_addr or "Anonymous"

    body = f"From: {sender_info}\n\n{message}"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"Leonne's Daily Post — Contact from {sender_info}"
    msg["From"] = imap_user
    msg["To"] = CONTACT_RECIPIENT
    if reply_to:
        msg["Reply-To"] = reply_to

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(imap_user, imap_token)
            smtp.send_message(msg)
        return jsonify({"status": "ok", "message": "Message sent"}), 200
    except Exception as e:
        print(f"Contact form email error: {e}", file=sys.stderr)
        return jsonify({"error": "Failed to send message"}), 500


@app.route("/deploy", methods=["GET"])
def health():
    """Simple health check."""
    index_path = WEB_ROOT / "index.html"
    return jsonify({
        "status": "running",
        "current_edition_exists": index_path.exists(),
        "backup_count": len(list(BACKUP_DIR.glob("edition_*.html"))) if BACKUP_DIR.exists() else 0
    })


if __name__ == "__main__":
    if DEPLOY_TOKEN == "CHANGE_ME_TO_A_LONG_RANDOM_STRING":
        print("WARNING: Using default deploy token. Set DEPLOY_TOKEN environment variable.")
    print(f"Deploy endpoint listening on port {PORT}")
    print(f"Web root: {WEB_ROOT}")
    print(f"Backups:  {BACKUP_DIR}")
    app.run(host="127.0.0.1", port=PORT)
