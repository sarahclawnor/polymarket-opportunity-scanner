#!/bin/bash
# Polymarket Opportunity Scanner - Hourly Cron Script
# Place this in crontab: 0 * * * * /home/azureadmin/.openclaw/workspace/polymarket-opportunity-scanner/run_scanner.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load virtual environment
source venv/bin/activate

# Run scanner with optimized parameters:
# --max-markets: 100 markets per scan (increased coverage)
# --min-volume: $10k to balance quality vs quantity
# --min-edge: 10% edge threshold
# --max-days: No limit (scans all active markets, prioritizes closing-soon)
# --skip-alerted: Prevents duplicate alerts and wasted API credits
python main.py \
    --max-markets 100 \
    --min-volume 10000 \
    --min-edge 0.10 \
    --max-days 90 \
    --forecast-runs 1 \
    --skip-alerted \
    --output "${SCRIPT_DIR}/opportunities.json" \
    >> "${SCRIPT_DIR}/scanner.log" 2>&1

EXIT_CODE=$?

# Log completion
echo "[$(date)] Scanner completed with exit code ${EXIT_CODE}" >> "${SCRIPT_DIR}/scanner.log"

# Push new data to GitHub if there are changes
if [ ${EXIT_CODE} -eq 0 ]; then
    if ! git diff --quiet opportunities.json alerted_markets.json history/ 2>/dev/null || ! git diff --cached --quiet; then
        git add opportunities.json alerted_markets.json history/
        COMMIT_MSG="Scanner run $(date +%Y-%m-%d_%H:%M): $(python3 -c "import json; d=json.load(open('opportunities.json')); print(f'{d[\"count\"]} opportunities')" 2>/dev/null || echo "completed")"
        git commit -m "${COMMIT_MSG}" --quiet
        git push --quiet 2>> "${SCRIPT_DIR}/scanner.log"
        echo "[$(date)] Data pushed to GitHub" >> "${SCRIPT_DIR}/scanner.log"
    else
        echo "[$(date)] No data changes, skipping push" >> "${SCRIPT_DIR}/scanner.log"
    fi
fi

exit ${EXIT_CODE}
