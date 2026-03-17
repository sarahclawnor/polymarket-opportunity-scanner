"""
Alert handlers for notifying about opportunities.
"""
import json
import logging
from typing import List
from datetime import datetime
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
            print("\n" + "=" * 70)
            print("No opportunities found matching criteria.")
            print("=" * 70)
            return
        
        print("\n" + "=" * 70)
        print(f"🎯 FOUND {len(opportunities)} OPPORTUNITIES")
        print("=" * 70)
        
        for i, opp in enumerate(opportunities, 1):
            emoji = {"high": "🔥", "medium": "⚡", "low": "💡"}.get(opp.conviction, "📊")
            
            print(f"\n{'─' * 70}")
            print(f"{emoji} #{i} [{opp.conviction.upper()}] {opp.market.title}")
            print(f"{'─' * 70}")
            print(f"   📈 Market:     {opp.market_probability:>6.1%} (Polymarket)")
            print(f"   🤖 Forecast:   {opp.forecast_probability:>6.1%} (AI model)")
            print(f"   💰 Edge:       {opp.edge:>6.1%} → Bet on {opp.edge_direction.upper()}")
            print(f"   📊 Volume:     ${opp.market.volume:>10,.0f}")
            print(f"   🎯 Confidence: {opp.forecast.confidence:>6.0%}")
            print(f"   ⏰ Closes:     {opp.market.days_until_close:>6.0f} days" if opp.market.days_until_close else "   ⏰ Closes:     TBD")
            print(f"   🔗 URL:        {opp.market_url}")
            print(f"\n   🧠 AI Reasoning:")
            
            # Extract and format key reasoning
            reasoning = self._extract_key_reasoning(opp.forecast.reasoning)
            for line in reasoning[:5]:  # Show up to 5 key points
                print(f"      • {line}")
            if len(reasoning) > 5:
                print(f"      ... ({len(reasoning) - 5} more points)")
        
        print("\n" + "=" * 70)
    
    def _extract_key_reasoning(self, reasoning: str) -> List[str]:
        """Extract key reasoning points from forecast text."""
        import re
        
        points = []
        
        # Look for bullet points and numbered lists
        bullet_pattern = r'^[\s]*[-•\*][\s]+(.+)$'
        number_pattern = r'^[\s]*\(?([a-d][\).]|[0-9]+[\).])\s*(.+)$'
        
        for line in reasoning.split('\n'):
            line = line.strip()
            if not line or len(line) < 20:
                continue
            
            # Match bullet points
            bullet_match = re.match(bullet_pattern, line, re.MULTILINE)
            if bullet_match:
                points.append(bullet_match.group(1)[:150])
                continue
            
            # Match numbered items (a), b), 1), 2), etc.)
            number_match = re.match(number_pattern, line)
            if number_match:
                points.append(number_match.group(2)[:150])
                continue
            
            # Look for key sentences with forecasting keywords
            keywords = ['status quo', 'baseline', 'scenario', 'outcome', 
                       'likely', 'probability', 'chance', 'expected']
            if any(kw in line.lower() for kw in keywords) and len(line) > 40:
                if line not in points:
                    points.append(line[:150])
        
        # If no structured points found, take first substantial paragraph
        if not points:
            paragraphs = reasoning.split('\n\n')
            for para in paragraphs:
                clean = para.strip().replace('\n', ' ')
                if len(clean) > 50 and len(clean) < 300:
                    points.append(clean)
                    break
        
        return points[:10]  # Limit to 10 points


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


class DiscordAlerts(AlertHandler):
    """Send alerts via Discord webhook."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send(self, opportunities: List[Opportunity]) -> None:
        import aiohttp
        
        if not opportunities:
            return
        
        # Send summary message first
        summary_embed = self._format_summary_embed(opportunities)
        
        async with aiohttp.ClientSession() as session:
            # Send summary
            payload = {"embeds": [summary_embed]}
            async with session.post(self.webhook_url, json=payload) as resp:
                if resp.status not in (200, 204):
                    logger.error(f"Failed to send Discord summary: {await resp.text()}")
            
            # Send individual opportunities (max 3)
            for opp in opportunities[:3]:
                embed = self._format_embed(opp)
                payload = {"embeds": [embed]}
                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status not in (200, 204):
                        logger.error(f"Failed to send Discord alert: {await resp.text()}")
    
    def _format_summary_embed(self, opportunities: List[Opportunity]) -> dict:
        """Format summary of all opportunities."""
        total_opps = len(opportunities)
        high_conviction = sum(1 for o in opportunities if o.conviction == "high")
        
        return {
            "title": "🎯 POLYMARKET OPPORTUNITY SCAN COMPLETE",
            "description": f"Found **{total_opps}** mispriced markets",
            "color": 0x00BFFF,
            "fields": [
                {
                    "name": "📊 High Conviction",
                    "value": f"{high_conviction}",
                    "inline": True,
                },
                {
                    "name": "⏰ Scan Time",
                    "value": datetime.now().strftime("%H:%M UTC"),
                    "inline": True,
                },
            ],
            "timestamp": datetime.now().isoformat(),
        }
    
    def _format_embed(self, opp: Opportunity) -> dict:
        """Format opportunity as Discord embed."""
        color_map = {"high": 0xFF4500, "medium": 0xFFA500, "low": 0x32CD32}
        emoji_map = {"high": "🔥", "medium": "⚡", "low": "💡"}
        
        color = color_map.get(opp.conviction, 0x808080)
        emoji = emoji_map.get(opp.conviction, "📊")
        
        # Extract key reasoning points (first substantial paragraph)
        reasoning = self._extract_reasoning_summary(opp.forecast.reasoning)
        
        return {
            "title": f"{emoji} {opp.market.title[:250]}",
            "description": f"**{opp.conviction.upper()} CONVICTION** | Edge: {opp.edge:.1%}",
            "color": color,
            "fields": [
                {
                    "name": "📈 Market (Polymarket)",
                    "value": f"{opp.market_probability:.1%}",
                    "inline": True,
                },
                {
                    "name": "🤖 AI Forecast",
                    "value": f"{opp.forecast_probability:.1%}",
                    "inline": True,
                },
                {
                    "name": "💰 Action",
                    "value": f"Bet **{opp.edge_direction.upper()}**",
                    "inline": True,
                },
                {
                    "name": "📊 Volume",
                    "value": f"${opp.market.volume:,.0f}",
                    "inline": True,
                },
                {
                    "name": "🎯 Confidence",
                    "value": f"{opp.forecast.confidence:.0%}",
                    "inline": True,
                },
                {
                    "name": "⏰ Days Left",
                    "value": f"{opp.market.days_until_close:.0f}" if opp.market.days_until_close else "N/A",
                    "inline": True,
                },
                {
                    "name": "🧠 AI Reasoning",
                    "value": reasoning[:1000] if reasoning else "See detailed analysis in logs",
                    "inline": False,
                },
            ],
            "url": opp.market_url,
            "footer": {
                "text": f"{opp.market.category} | ID: {opp.market.id[:8]}...",
            },
            "timestamp": datetime.now().isoformat(),
        }
    
    def _extract_reasoning_summary(self, reasoning: str) -> str:
        """Extract key reasoning points from forecast text."""
        import re
        
        # Remove markdown headers
        text = re.sub(r'#+ ', '', reasoning)
        
        # Look for key sections
        patterns = [
            r'(?:rationale|reasoning|analysis|key factors)[\s\S]{0,500}?(?=\n\n|\Z)',
            r'(?:a\)|b\)|c\)|d\))[^\n]{50,300}',
            r'status quo.*?\.(?:\s|$)',
            r'scenario.*?\.(?:\s|$)',
        ]
        
        summaries = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches[:2]:  # Take first 2 matches per pattern
                clean = match.strip().replace('\n', ' ')
                if len(clean) > 30 and clean not in summaries:
                    summaries.append(clean[:300])
        
        # If no good summaries found, take first substantial paragraph
        if not summaries:
            paragraphs = text.split('\n\n')
            for para in paragraphs:
                clean = para.strip().replace('\n', ' ')
                if len(clean) > 50 and 'probability' not in clean.lower():
                    summaries.append(clean[:400])
                    break
        
        return '\n\n'.join(summaries) if summaries else reasoning[:500]


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
