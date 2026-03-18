"""
Polymarket Gamma API Client
Fetches active markets for analysis.
"""
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"


@dataclass
class Market:
    """Represents a Polymarket market."""
    id: str
    slug: str
    title: str
    description: str
    category: str
    outcome_yes_price: float  # Current probability (0-1)
    outcome_no_price: float
    volume: float
    liquidity: float
    end_date: Optional[datetime]
    question: str
    resolution_source: Optional[str]
    icon: Optional[str]
    
    @property
    def implied_probability(self) -> float:
        """Returns the market's implied probability of Yes."""
        return self.outcome_yes_price
    
    @property
    def days_until_close(self) -> Optional[float]:
        """Returns days until market closes."""
        if not self.end_date:
            return None
        # Handle timezone-aware vs naive datetime comparison
        now = datetime.now(self.end_date.tzinfo) if self.end_date.tzinfo else datetime.now()
        delta = self.end_date - now
        return delta.total_seconds() / 86400


class GammaClient:
    """Client for Polymarket's Gamma API."""
    
    def __init__(self, base_url: str = GAMMA_API_BASE):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _get(self, endpoint: str, params: Dict[str, Any] = None) -> Dict:
        """Make GET request to Gamma API."""
        url = f"{self.base_url}{endpoint}"
        async with self.session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def get_active_markets(
        self,
        min_volume: float = 100000,
        max_days_to_close: Optional[int] = None,
        limit: int = 100,
        category: Optional[str] = None,
        prioritize_recent: bool = True,
    ) -> List[Market]:
        """
        Fetch active markets matching criteria.
        
        Args:
            min_volume: Minimum 24h volume in USD
            max_days_to_close: Only markets closing within N days (None = no limit)
            limit: Maximum markets to fetch
            category: Filter by category (optional)
            prioritize_recent: If True, prioritize markets closing sooner
        """
        # Fetch more than needed to allow for filtering
        fetch_limit = min(limit * 3, 500)
        
        params = {
            "active": "true",
            "closed": "false",
            "limit": fetch_limit,
            "sort": "volume",
        }
        
        if category:
            params["category"] = category
        
        data = await self._get("/markets", params)
        markets = []
        
        # Handle both list response and dict with 'markets' key
        market_list = data if isinstance(data, list) else data.get("markets", [])
        
        for market_data in market_list:
            try:
                market = self._parse_market(market_data)
                # Filter by volume
                if market.volume < min_volume:
                    continue
                # Filter by days to close if specified
                if max_days_to_close is not None:
                    days = market.days_until_close
                    if days is None or days > max_days_to_close:
                        continue
                markets.append(market)
            except Exception as e:
                logger.warning(f"Failed to parse market: {e}")
                continue
        
        # Prioritize: markets closing sooner get higher priority
        if prioritize_recent:
            # Score = volume / (days_until_close + 1)
            # This prioritizes high-volume markets that close soon
            def priority_score(m: Market) -> float:
                if m.days_until_close is None:
                    days = 365  # Treat no date as far future
                elif m.days_until_close < 0:
                    days = 0.1  # Past close but still active
                else:
                    days = m.days_until_close
                # High volume + closing soon = high priority
                return m.volume / (days + 1)
            
            markets.sort(key=priority_score, reverse=True)
        
        # Return only requested limit
        result = markets[:limit]
        
        # Log breakdown
        closing_soon = sum(1 for m in result if m.days_until_close is not None and 0 <= m.days_until_close <= 30)
        closing_mid = sum(1 for m in result if m.days_until_close is not None and 30 < m.days_until_close <= 90)
        closing_late = sum(1 for m in result if m.days_until_close is None or m.days_until_close > 90)
        past_close = sum(1 for m in result if m.days_until_close is not None and m.days_until_close < 0)
        
        logger.info(f"Found {len(result)} markets matching criteria:")
        logger.info(f"  - Closing ≤30 days: {closing_soon}")
        logger.info(f"  - Closing 31-90 days: {closing_mid}")
        logger.info(f"  - Closing >90 days: {closing_late}")
        if past_close:
            logger.info(f"  - Past close date: {past_close}")
        
        return result
    
    def _parse_market(self, data: Dict[str, Any]) -> Market:
        """Parse API response into Market object."""
        # Parse end date
        end_date_str = data.get("endDate")
        end_date = None
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        
        # Parse outcomes and prices (they come as JSON strings)
        yes_price = 0.5
        no_price = 0.5
        
        try:
            outcomes_str = data.get("outcomes", "[]")
            outcome_prices_str = data.get("outcomePrices", "[]")
            
            outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
            outcome_prices = json.loads(outcome_prices_str) if isinstance(outcome_prices_str, str) else outcome_prices_str
            
            for i, outcome in enumerate(outcomes):
                name = outcome.lower() if isinstance(outcome, str) else str(outcome).lower()
                price = float(outcome_prices[i]) if i < len(outcome_prices) else 0
                if name == "yes":
                    yes_price = price
                elif name == "no":
                    no_price = price
        except (json.JSONDecodeError, IndexError, ValueError) as e:
            logger.warning(f"Failed to parse outcomes/prices: {e}")
            yes_price = 0.5
            no_price = 0.5
        
        # Get title from available fields (Gamma API uses 'question' not 'title')
        title = data.get("question", "")
        if not title and data.get("groupItemTitle"):
            title = data.get("groupItemTitle")
        if not title and data.get("events"):
            # Try to get title from first event
            events = data.get("events", [])
            if events and isinstance(events, list):
                title = events[0].get("title", "")
        
        return Market(
            id=str(data.get("id", "")),
            slug=data.get("slug", ""),
            title=title,
            description=data.get("description", ""),
            category=data.get("category", ""),
            outcome_yes_price=yes_price,
            outcome_no_price=no_price,
            volume=float(data.get("volume", 0)),
            liquidity=float(data.get("liquidity", 0)),
            end_date=end_date,
            question=data.get("question", title),
            resolution_source=data.get("resolutionSource"),
            icon=data.get("icon"),
        )
    
    async def get_market_by_slug(self, slug: str) -> Optional[Market]:
        """Fetch a specific market by its slug."""
        try:
            data = await self._get(f"/markets/{slug}")
            return self._parse_market(data)
        except Exception as e:
            logger.error(f"Failed to fetch market {slug}: {e}")
            return None
