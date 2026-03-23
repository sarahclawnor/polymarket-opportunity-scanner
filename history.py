"""
Alert history logging - append-only daily JSON files for dashboard consumption.
Each day gets its own file: history/YYYY-MM-DD.json
"""
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List

from opportunity_detector import Opportunity

logger = logging.getLogger(__name__)

HISTORY_DIR = Path(__file__).parent / "history"


class HistoryLogger:
    """Append scan results to daily JSON files."""

    def __init__(self, history_dir: Path | None = None):
        self.history_dir = history_dir or HISTORY_DIR
        self.history_dir.mkdir(exist_ok=True)

    def _path_for_date(self, d: date) -> Path:
        return self.history_dir / f"{d.isoformat()}.json"

    def log_scan(self, opportunities: List[Opportunity]) -> Path:
        """
        Append a scan run to today's history file.

        Each day file contains:
        {
          "date": "YYYY-MM-DD",
          "scans": [
            {
              "scanned_at": "ISO-8601 timestamp",
              "opportunities_found": N,
              "opportunities": [...]
            }
          ]
        }

        Returns the path written.
        """
        today = date.today()
        filepath = self._path_for_date(today)

        scan_entry = {
            "scanned_at": datetime.utcnow().isoformat() + "Z",
            "opportunities_found": len(opportunities),
            "opportunities": [opp.to_dict() for opp in opportunities],
        }

        # Load existing day data or start fresh
        if filepath.exists():
            try:
                with open(filepath, "r") as f:
                    day_data = json.load(f)
            except (json.JSONDecodeError, KeyError):
                logger.warning(f"Corrupted history file {filepath}, starting fresh")
                day_data = {"date": today.isoformat(), "scans": []}
        else:
            day_data = {"date": today.isoformat(), "scans": []}

        day_data["scans"].append(scan_entry)

        with open(filepath, "w") as f:
            json.dump(day_data, f, indent=2)

        logger.info(f"Appended {len(opportunities)} opportunities to {filepath}")
        return filepath

    def get_recent_days(self, days: int = 7) -> List[dict]:
        """Return history for the last N days."""
        results = []
        today = date.today()
        for i in range(days):
            d = today - __import__("datetime").timedelta(days=i)
            filepath = self._path_for_date(d)
            if filepath.exists():
                try:
                    with open(filepath, "r") as f:
                        results.append(json.load(f))
                except (json.JSONDecodeError, KeyError):
                    continue
        return results
