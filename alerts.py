"""
Alert handlers for notifying about opportunities.
"""
import json
import logging
from typing import List
from opportunity_detector import Opportunity

logger = logging.getLogger(__name__)


class AlertHandler:
    """Base class for alert handlers."""
    
    async def send(self, opportunities: List[Opportunity]) -> None:
        """Send alerts for opportunities."""
        raise NotImplementedError


class ConsoleAlerts(AlertHandler):
    """Print opportunities to console."""
    
    async def send(self, opportunities: List[Opportunity]) -> None:
        if not opportunities:
            print("\n" + "=" * 60)
            print("No opportunities found matching criteria.")
            print("=" * 60)
            return
        
        print("\n" + "=" * 60)
        print(f"🎯 FOUND {len(opportunities)} OPPORTUNITIES")
        print("=" * 60)
        
        for i, opp in enumerate(opportunities, 1):
            print(f"\n{'─' * 60}")
            print(f"#{i} [{opp.conviction.upper()}] {opp.market.title}")
            print(f"{'─' * 60}")
            print(f"   Market:     {opp.market_probability:.1%} (Polymarket)")
            print(f"   Forecast:   {opp.forecast_probability:.1%} (AI model)")
            print(f"   Edge:       {opp.edge:.1%} → Bet on {opp.edge_direction.upper()}")
            print(f"   Volume:     ${opp.market.volume:,.0f}")
            print(f"   Confidence: {opp.forecast.confidence:.0%}")
            print(f"   URL:        {opp.market_url}")
            print(f"\n   Reasoning excerpt:")
            # Show first 300 chars of reasoning
            reasoning_preview = opp.forecast.reasoning[:300].replace('\n', ' ')
            print(f"   {reasoning_preview}...")
        
        print("\n" + "=" * 60)


class JSONAlerts(AlertHandler):
    """Save opportunities to JSON file."""
    
    def __init__(self, output_path: str = "opportunities.json"):
        self.output_path = output_path
    
    async def send(self, opportunities: List[Opportunity]) -> None:
        data = {
            "count": len(opportunities),
            "opportunities": [opp.to_dict() for opp in opportunities],
        }
        
        with open(self.output_path, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved {len(opportunities)} opportunities to {self.output_path}")


class TelegramAlerts(AlertHandler):
    """Send alerts via Telegram bot."""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
    
    async def send(self, opportunities: List[Opportunity]) -> None:
        import aiohttp
        
        if not opportunities:
            return
        
        for opp in opportunities[:5]:  # Limit to top 5
            message = self._format_message(opp)
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to send Telegram alert: {await resp.text()}")
    
    def _format_message(self, opp: Opportunity) -> str:
        emoji = {"high": "🔥", "medium": "⚡", "low": "💡"}.get(opp.conviction, "📊")
        
        return f"""{emoji} *{opp.conviction.upper()} CONVICTION OPPORTUNITY*

*{opp.market.title}*

📈 Market: {opp.market_probability:.1%}
🤖 Forecast: {opp.forecast_probability:.1%}
💰 Edge: {opp.edge:.1%} → Bet *{opp.edge_direction.upper()}*
📊 Volume: ${opp.market.volume:,.0f}
🎯 Confidence: {opp.forecast.confidence:.0%}

[View on Polymarket]({opp.market_url})
"""


class CompositeAlerts(AlertHandler):
    """Send to multiple handlers."""
    
    def __init__(self, handlers: List[AlertHandler]):
        self.handlers = handlers
    
    async def send(self, opportunities: List[Opportunity]) -> None:
        for handler in self.handlers:
            try:
                await handler.send(opportunities)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")
