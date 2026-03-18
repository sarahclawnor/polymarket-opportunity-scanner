"""
Alert history tracking - prevents duplicate alerts and wasted API calls.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Set
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

ALERTED_MARKETS_FILE = Path(__file__).parent / "alerted_markets.json"

# Re-alert if market probability changes by more than this threshold
PROBABILITY_CHANGE_THRESHOLD = 0.10  # 10%

# Re-alert after this many days even if probability hasn't changed
REAlert_AFTER_DAYS = 7


@dataclass
class AlertRecord:
    """Record of a previous alert."""
    market_id: str
    market_title: str
    market_probability: float
    forecast_probability: float
    edge: float
    edge_direction: str
    alerted_at: str  # ISO timestamp
    alert_count: int = 1
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AlertRecord":
        return cls(**data)


class AlertHistory:
    """Tracks which markets have already been alerted to avoid duplicates."""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or ALERTED_MARKETS_FILE
        self._records: Dict[str, AlertRecord] = {}
        self._load()
    
    def _load(self) -> None:
        """Load alert history from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                for market_id, record_data in data.items():
                    self._records[market_id] = AlertRecord.from_dict(record_data)
                logger.info(f"Loaded {len(self._records)} alert records")
            except Exception as e:
                logger.warning(f"Failed to load alert history: {e}")
                self._records = {}
        else:
            logger.info("No alert history file found, starting fresh")
    
    def _save(self) -> None:
        """Save alert history to disk."""
        try:
            data = {k: v.to_dict() for k, v in self._records.items()}
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save alert history: {e}")
    
    def should_alert(
        self,
        market_id: str,
        market_probability: float,
        forecast_probability: float,
    ) -> bool:
        """
        Determine if we should alert on this market.
        
        Returns True if:
        - Market has never been alerted before
        - Market probability has changed significantly (>10%)
        - Enough time has passed since last alert (7 days)
        """
        if market_id not in self._records:
            return True
        
        record = self._records[market_id]
        
        # Check if market probability changed significantly
        prob_change = abs(market_probability - record.market_probability)
        if prob_change >= PROBABILITY_CHANGE_THRESHOLD:
            logger.info(
                f"Market {market_id}: Probability changed {prob_change:.1%}, "
                "re-alerting"
            )
            return True
        
        # Check if enough time has passed
        last_alert = datetime.fromisoformat(record.alerted_at)
        days_since = (datetime.now() - last_alert).days
        if days_since >= REAlert_AFTER_DAYS:
            logger.info(
                f"Market {market_id}: {days_since} days since last alert, "
                "re-alerting"
            )
            return True
        
        logger.debug(
            f"Skipping alert for {market_id}: Already alerted {days_since}d ago, "
            f"prob change {prob_change:.1%}"
        )
        return False
    
    def record_alert(self, opportunity) -> None:
        """Record that we alerted on this opportunity."""
        market_id = opportunity.market.id
        
        if market_id in self._records:
            # Update existing record
            old_record = self._records[market_id]
            self._records[market_id] = AlertRecord(
                market_id=market_id,
                market_title=opportunity.market.title,
                market_probability=opportunity.market_probability,
                forecast_probability=opportunity.forecast_probability,
                edge=opportunity.edge,
                edge_direction=opportunity.edge_direction,
                alerted_at=datetime.now().isoformat(),
                alert_count=old_record.alert_count + 1,
            )
            logger.info(f"Updated alert record for {market_id} (alert #{self._records[market_id].alert_count})")
        else:
            # Create new record
            self._records[market_id] = AlertRecord(
                market_id=market_id,
                market_title=opportunity.market.title,
                market_probability=opportunity.market_probability,
                forecast_probability=opportunity.forecast_probability,
                edge=opportunity.edge,
                edge_direction=opportunity.edge_direction,
                alerted_at=datetime.now().isoformat(),
                alert_count=1,
            )
            logger.info(f"Created new alert record for {market_id}")
        
        self._save()
    
    def get_stats(self) -> dict:
        """Get statistics about alert history."""
        return {
            "total_markets_alerted": len(self._records),
            "total_alerts_sent": sum(r.alert_count for r in self._records.values()),
            "last_alert": max(
                (r.alerted_at for r in self._records.values()),
                default=None
            ),
        }
    
    def clear_old_records(self, days: int = 30) -> int:
        """Clear records older than specified days. Returns count cleared."""
        cutoff = datetime.now() - timedelta(days=days)
        to_remove = []
        
        for market_id, record in self._records.items():
            record_date = datetime.fromisoformat(record.alerted_at)
            if record_date < cutoff:
                to_remove.append(market_id)
        
        for market_id in to_remove:
            del self._records[market_id]
        
        if to_remove:
            self._save()
        
        return len(to_remove)
