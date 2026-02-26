#!/bin/bash
# Leonne's Daily Post — Cron wrapper
# Loads environment variables and runs the pipeline.
# Add to www-data's crontab: 0 6 * * * /opt/leonne-deploy/cron_generate.sh

# Source environment from the systemd service file
eval $(grep '^Environment=' /etc/systemd/system/leonne-deploy.service | sed 's/^Environment=/export /')

# Run the pipeline
/opt/leonne-deploy/run_pipeline.sh >> /opt/leonne-deploy/logs/cron-$(date +\%Y\%m\%d).log 2>&1
