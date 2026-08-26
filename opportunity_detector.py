"""
Opportunity detection - identifies mispriced markets.
"""
import re
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
    
    POLYMARKET_REFERRAL = "0x3f0e7f9f739411885e22d49af129ed8d2b06e700"

    @property
    def market_url(self) -> str:
        return f"https://polymarket.com/market/{self.market.slug}?r={self.POLYMARKET_REFERRAL}"
    
    @property
    def reasoning_summary(self) -> str:
        """Extract contextualized AI reasoning summary (same logic as Discord alerts)."""
        return self._extract_reasoning_summary(
            self.forecast.reasoning,
            self.forecast_probability,
            self.market_probability,
            self.edge_direction,
        )
    
    @staticmethod
    def _extract_reasoning_summary(
        reasoning: str,
        forecast_probability: float = 0.5,
        market_probability: float = 0.5,
        edge_direction: str = "yes",
    ) -> str:
        """Extract key reasoning points from forecast text.
        
        The key insight: AI might say "30% YES" and explain why it's unlikely (leaning NO),
        but if market is at 5% YES, the edge is betting YES. The reasoning needs to be
        contextualized to match the action.
        """
        lines = [l.strip() for l in reasoning.split('\n') if l.strip()]
        
        # PRIORITY 1: Look for section (e) - the conclusion
        conclusion_section = []
        in_conclusion = False
        
        for line in lines:
            if re.match(r'^[\s]*(?:\(?)[e][\).]\s*', line, re.IGNORECASE):
                in_conclusion = True
                content = re.sub(r'^[\s]*(?:\(?)[e][\).]\s*', '', line, flags=re.IGNORECASE)
                if content and len(content) > 20:
                    conclusion_section.append(content)
                continue
            
            if in_conclusion:
                if re.match(r'^[\s]*(?:\(?)[a-d][\).]\s*', line, re.IGNORECASE):
                    break
                if 'probability:' in line.lower():
                    break
                conclusion_section.append(line)
        
        if conclusion_section:
            full_conclusion = ' '.join(conclusion_section)
            full_conclusion = re.sub(r'\s+', ' ', full_conclusion).strip()
            if len(full_conclusion) > 40:
                header = f"AI predicts {forecast_probability:.0%} YES (vs market {market_probability:.0%}) → Bet {edge_direction.upper()}"
                return f"{header}\n\n{full_conclusion[:600]}"
        
        # PRIORITY 2: Look for "your conclusion" or similar patterns
        conclusion_patterns = [
            r'(?:your\s+)?conclusion[:\s]+(.+?)(?=\n\s*(?:\([a-d]\)|probability:|$))',
            r'(?:based on the above|therefore)[,\s]+(.+?)(?=\n\s*(?:\([a-d]\)|probability:|$))',
        ]
        
        for pattern in conclusion_patterns:
            match = re.search(pattern, reasoning, re.IGNORECASE | re.DOTALL)
            if match:
                conclusion = match.group(1).strip()
                conclusion = re.sub(r'\s+', ' ', conclusion)
                if len(conclusion) > 30:
                    header = f"AI predicts {forecast_probability:.0%} YES (vs market {market_probability:.0%}) → Bet {edge_direction.upper()}"
                    return f"{header}\n\n{conclusion[:600]}"
        
        # PRIORITY 3: Show both scenarios (c) and (d) with context
        scenarios = []
        seen = set()
        for line in lines:
            match = re.match(r'^[\s]*(?:\(?)([c-d])[\).]\s*(.+)$', line, re.IGNORECASE)
            if match:
                letter = match.group(1).upper()
                content = match.group(2).strip()
                content_lower = content.lower()[:50]
                if content_lower not in seen and len(content) > 20:
                    seen.add(content_lower)
                    content = re.sub(r'\s+', ' ', content)
                    content = re.sub(r'^A brief description of a scenario that results in [aA]\s*', '', content)
                    scenarios.append(f"**{letter}:** {content[:180]}")
        
        if scenarios:
            header = f"AI predicts {forecast_probability:.0%} YES (vs market {market_probability:.0%}) → Bet {edge_direction.upper()}"
            return f"{header}\n\nKey scenarios:\n" + '\n'.join(scenarios[:2])
        
        # Fallback
        return f"AI predicts {forecast_probability:.0%} YES (vs market {market_probability:.0%}) → Bet {edge_direction.upper()}\n\nSee detailed analysis in logs"
    
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
            "edge": round(self.edge, 3),
            "edge_direction": self.edge_direction.upper(),
            "expected_value": round(self.expected_value, 3),
            "conviction": self.conviction.upper(),
            "reasoning_summary": self.reasoning_summary,
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
