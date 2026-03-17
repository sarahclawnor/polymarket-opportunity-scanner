#!/bin/bash
# Polymarket Opportunity Scanner - Hourly Cron Script
# Place this in crontab: 0 * * * * /home/azureadmin/.openclaw/workspace/polymarket-opportunity-scanner/run_scanner.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load virtual environment
source venv/bin/activate

# Run scanner with configured parameters
# Adjust these parameters as needed:
# --max-markets: How many markets to analyze per run
# --min-volume: Minimum market volume in USD
# --min-edge: Minimum edge % to flag opportunity (0.10 = 10%)
# --max-days: Only markets closing within N days
python main.py \
    --max-markets 10 \
    --min-volume 100000 \
    --min-edge 0.10 \
    --max-days 30 \
    --output "${SCRIPT_DIR}/opportunities.json" \
    >> "${SCRIPT_DIR}/scanner.log" 2>&1

EXIT_CODE=$?

# Log completion
echo "[$(date)] Scanner completed with exit code ${EXIT_CODE}" >> "${SCRIPT_DIR}/scanner.log"

exit ${EXIT_CODE}
