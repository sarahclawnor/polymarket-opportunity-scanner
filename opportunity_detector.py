"""
Opportunity detection - identifies mispriced markets.
"""
from dataclasses import dataclass
from typing import List, Optional
from gamma_client import Market
from forecasting import ForecastResult
import logging

logger = logging.getLogger(__name__)


@dataclass
class Opportunity:
    """A detected market mispricing opportunity."""
    market: Market
    forecast: ForecastResult
    market_probability: float
    forecast_probability: float
    edge: float  # Absolute difference between forecast and market
    edge_direction: str  # "yes" or "no" - which side to bet
    expected_value: float  # Rough EV estimate
    conviction: str  # "high", "medium", "low" based on confidence and edge
    
    @property
    def market_url(self) -> str:
        return f"https://polymarket.com/market/{self.market.slug}"
    
    def to_dict(self) -> dict:
        return {
            "market_info": {
                "id": self.market.id,
                "title": self.market.title,
                "slug": self.market.slug,
                "url": self.market_url,
                "category": self.market.category,
                "volume": self.market.volume,
                "days_until_close": self.market.days_until_close,
                "probability": round(self.market_probability, 3),
            },
            "forecast": {
                "probability": round(self.forecast_probability, 3),
                "confidence": round(self.forecast.confidence, 2),
                "reasoning": self.forecast.reasoning,
            },
            "opportunity": {
                "edge": round(self.edge, 3),
                "edge_direction": self.edge_direction,
                "expected_value": round(self.expected_value, 3),
                "conviction": self.conviction,
            },
        }


class OpportunityDetector:
    """Detects mispriced markets based on forecast vs market price divergence."""
    
    def __init__(
        self,
        min_edge: float = 0.10,  # Minimum 10% edge
        min_confidence: float = 0.5,
        max_market_probability: float = 0.95,  # Skip markets near certainty
        min_market_probability: float = 0.05,
    ):
        self.min_edge = min_edge
        self.min_confidence = min_confidence
        self.max_market_probability = max_market_probability
        self.min_market_probability = min_market_probability
    
    def analyze(
        self,
        market: Market,
        forecast: ForecastResult,
    ) -> Optional[Opportunity]:
        """
        Analyze a market for opportunity.
        
        Returns:
            Opportunity if mispricing detected, None otherwise.
        """
        market_prob = market.implied_probability
        
        # Skip markets near certainty (no value)
        if market_prob > self.max_market_probability or market_prob < self.min_market_probability:
            logger.debug(f"Skipping {market.slug}: probability at boundary")
            return None
        
        # Skip low confidence forecasts
        if forecast.confidence < self.min_confidence:
            logger.debug(f"Skipping {market.slug}: low confidence ({forecast.confidence:.2f})")
            return None
        
        forecast_prob = forecast.probability_yes
        edge = abs(forecast_prob - market_prob)
        
        # Skip if edge too small
        if edge < self.min_edge:
            logger.debug(f"Skipping {market.slug}: edge too small ({edge:.2f})")
            return None
        
        # Determine direction
        if forecast_prob > market_prob:
            edge_direction = "yes"
            expected_value = forecast_prob - market_prob
        else:
            edge_direction = "no"
            expected_value = market_prob - forecast_prob
        
        # Calculate conviction
        conviction_score = edge * forecast.confidence
        if conviction_score > 0.15:
            conviction = "high"
        elif conviction_score > 0.08:
            conviction = "medium"
        else:
            conviction = "low"
        
        return Opportunity(
            market=market,
            forecast=forecast,
            market_probability=market_prob,
            forecast_probability=forecast_prob,
            edge=edge,
            edge_direction=edge_direction,
            expected_value=expected_value,
            conviction=conviction,
        )
    
    def rank_opportunities(self, opportunities: List[Opportunity]) -> List[Opportunity]:
        """Rank opportunities by expected value and confidence."""
        return sorted(
            opportunities,
            key=lambda o: (o.expected_value * o.forecast.confidence),
            reverse=True,
        )
