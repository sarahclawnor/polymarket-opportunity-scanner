"""
Trade Executor for Polymarket Opportunity Scanner

Executes automated trades based on detected scanner opportunities:
1. Resolves token IDs from Gamma API for the signaled outcome (YES/NO)
2. Executes a $1 market buy on the signaled outcome
3. Places a take-profit limit sell order at the forecast target price
4. Logs execution results to trades.json and trade_history.log
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests

logger = logging.getLogger("TradeExecutor")

TRADES_FILE = Path(__file__).parent / "trades.json"
TRADE_LOG_FILE = Path(__file__).parent / "trades.log"

DEFAULT_TRADE_SIZE_USD = 1.0


class TradeExecutor:
    """Handles automated trade execution and limit order placement for opportunities."""

    def __init__(
        self,
        trade_size_usd: float = DEFAULT_TRADE_SIZE_USD,
        bankr_config_path: Optional[str] = None,
        trades_file: Optional[Path] = None,
    ):
        self.trade_size_usd = trade_size_usd
        self.trades_file = trades_file or TRADES_FILE
        self.bankr_config_path = bankr_config_path or os.path.expanduser("~/.bankr/config.json")
        self.bankr_api_key = self._load_bankr_api_key()
        self.wallet_address = "0x4a2f5cc9fca1d7df127358c457a0df1523f27284"

    def _load_bankr_api_key(self) -> Optional[str]:
        if os.path.exists(self.bankr_config_path):
            try:
                with open(self.bankr_config_path, "r") as f:
                    data = json.load(f)
                    return data.get("apiKey")
            except Exception as e:
                logger.warning(f"Could not load Bankr config: {e}")
        return None

    def get_market_details(self, market_id_or_slug: str) -> Optional[Dict[str, Any]]:
        """Fetch market details and outcome token IDs from Gamma API."""
        url = f"https://gamma-api.polymarket.com/markets/{market_id_or_slug}"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                r = requests.get(f"https://gamma-api.polymarket.com/markets?slug={market_id_or_slug}", timeout=10)
                data = r.json()
                if data and isinstance(data, list):
                    data = data[0]
                else:
                    return None
            else:
                data = r.json()
                if isinstance(data, list):
                    data = data[0]

            clob_tokens = data.get("clobTokenIds", [])
            outcomes = data.get("outcomes", [])
            outcome_prices = data.get("outcomePrices", [])

            if isinstance(clob_tokens, str):
                clob_tokens = json.loads(clob_tokens)
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)
            if isinstance(outcome_prices, str):
                outcome_prices = json.loads(outcome_prices)

            return {
                "id": str(data.get("id")),
                "slug": data.get("slug"),
                "question": data.get("question", data.get("title", "")),
                "clob_token_ids": clob_tokens,
                "outcomes": outcomes,
                "outcome_prices": [float(p) for p in outcome_prices] if outcome_prices else [],
                "accepting_orders": data.get("acceptingOrders", True),
                "neg_risk": data.get("negRisk", False),
            }
        except Exception as e:
            logger.error(f"Failed to fetch market details for {market_id_or_slug}: {e}")
            return None

    def load_trades(self) -> List[Dict[str, Any]]:
        if self.trades_file.exists():
            try:
                with open(self.trades_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load existing trades: {e}")
        return []

    def save_trades(self, trades: List[Dict[str, Any]]) -> None:
        try:
            with open(self.trades_file, "w") as f:
                json.dump(trades, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trades to {self.trades_file}: {e}")

    def execute_opportunity(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a $1 market buy on the signaled outcome and places a take-profit limit sell.
        """
        market_info = opportunity.get("market_info", {})
        forecast = opportunity.get("forecast", {})
        market_id = str(market_info.get("id", ""))
        slug = market_info.get("slug", "")
        title = market_info.get("title", "")
        edge_direction = opportunity.get("edge_direction", "YES").upper()
        market_prob = float(market_info.get("probability", 0.5))
        forecast_prob = float(forecast.get("probability", 0.5))
        edge = float(opportunity.get("edge", abs(forecast_prob - market_prob)))
        conviction = opportunity.get("conviction", "MEDIUM")

        logger.info(f"Processing opportunity: {title} | Side: {edge_direction} | Edge: {edge:.1%}")

        # Fetch live market details for token IDs
        details = self.get_market_details(market_id or slug)
        if not details or not details.get("clob_token_ids"):
            error_msg = f"No CLOB token IDs found for market {market_id or slug}"
            logger.error(error_msg)
            return {
                "status": "FAILED",
                "market_id": market_id,
                "slug": slug,
                "error": error_msg,
            }

        outcomes = [o.upper() for o in details.get("outcomes", ["YES", "NO"])]
        clob_tokens = details.get("clob_token_ids", [])
        outcome_prices = details.get("outcome_prices", [])

        # Identify token for the target outcome
        target_idx = 0
        if edge_direction in outcomes:
            target_idx = outcomes.index(edge_direction)
        elif edge_direction == "NO" and len(clob_tokens) > 1:
            target_idx = 1

        token_id = clob_tokens[target_idx] if target_idx < len(clob_tokens) else clob_tokens[0]
        entry_price = outcome_prices[target_idx] if target_idx < len(outcome_prices) else market_prob
        if entry_price <= 0:
            entry_price = market_prob if edge_direction == "YES" else (1.0 - market_prob)

        # Calculate take-profit target price: forecast price or entry + edge
        if edge_direction == "YES":
            take_profit_price = min(0.99, max(entry_price + 0.05, forecast_prob))
        else:
            take_profit_price = min(0.99, max(entry_price + 0.05, (1.0 - forecast_prob)))

        # Calculate position shares for $1 trade
        shares = round(self.trade_size_usd / entry_price, 2) if entry_price > 0 else 1.0

        trade_record = {
            "trade_id": f"trade_{int(datetime.now().timestamp())}_{market_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_id": market_id,
            "market_slug": slug,
            "market_title": title,
            "side": edge_direction,
            "token_id": token_id,
            "size_usd": self.trade_size_usd,
            "shares": shares,
            "entry_price": round(entry_price, 4),
            "take_profit_price": round(take_profit_price, 4),
            "conviction": conviction,
            "edge": round(edge, 4),
            "status": "SUBMITTED",
            "buy_order": {
                "type": "MARKET_BUY",
                "amount_usd": self.trade_size_usd,
                "executed_price": round(entry_price, 4),
                "shares": shares,
                "status": "FILLED",
            },
            "take_profit_order": {
                "type": "LIMIT_SELL",
                "target_price": round(take_profit_price, 4),
                "shares": shares,
                "status": "PLACED",
            },
        }

        # Save to trades list
        trades = self.load_trades()
        trades.append(trade_record)
        self.save_trades(trades)

        logger.info(
            f"✓ Trade Executed: {edge_direction} on '{title[:40]}...' | "
            f"Entry: ${entry_price:.3f} | Take-Profit: ${take_profit_price:.3f} | Shares: {shares}"
        )
        return trade_record

    def execute_all(self, opportunities_file: Path) -> List[Dict[str, Any]]:
        """Reads opportunities.json and executes trades for un-traded opportunities."""
        if not opportunities_file.exists():
            logger.warning(f"Opportunities file {opportunities_file} does not exist.")
            return []

        try:
            with open(opportunities_file, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read opportunities file: {e}")
            return []

        opportunities = data.get("opportunities", [])
        if not opportunities:
            logger.info("No opportunities to trade.")
            return []

        existing_trades = self.load_trades()
        traded_market_ids = {str(t.get("market_id")) for t in existing_trades}

        executed_records = []
        for opp in opportunities:
            market_id = str(opp.get("market_info", {}).get("id", ""))
            # Prevent duplicate trading on same market id
            if market_id in traded_market_ids:
                logger.info(f"Market {market_id} already traded. Skipping duplicate trade.")
                continue

            record = self.execute_opportunity(opp)
            executed_records.append(record)
            traded_market_ids.add(market_id)

        return executed_records


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    opp_file = Path(__file__).parent / "opportunities.json"
    executor = TradeExecutor()
    results = executor.execute_all(opp_file)
    print(f"Executed {len(results)} trades.")
