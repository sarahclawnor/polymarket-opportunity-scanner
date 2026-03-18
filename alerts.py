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
            print(f"   📈 Market:     YES {opp.market_probability:>6.1%} | NO {1-opp.market_probability:>6.1%}")
            print(f"   🤖 Forecast:   YES {opp.forecast_probability:>6.1%} | NO {1-opp.forecast_probability:>6.1%}")
            print(f"   💰 Edge:       {opp.edge:>6.1%} → Bet on {opp.edge_direction.upper()}")
            print(f"   📊 Volume:     ${opp.market.volume:>10,.0f}")
            print(f"   🎯 Confidence: {opp.forecast.confidence:>6.0%}")
            print(f"   ⏰ Closes:     {opp.market.days_until_close:>6.0f} days" if opp.market.days_until_close else "   ⏰ Closes:     TBD")
            print(f"   🔗 URL:        {opp.market_url}")
            print(f"\n   🧠 AI Reasoning:")
            print(f"      AI predicts {opp.forecast_probability:.0%} YES (market: {opp.market_probability:.0%})")
            
            # Extract and format key reasoning - prioritize conclusion
            reasoning = self._extract_key_reasoning(opp.forecast.reasoning)
            for line in reasoning[:4]:  # Show up to 4 key points
                print(f"      • {line}")
            if len(reasoning) > 4:
                print(f"      ... ({len(reasoning) - 4} more points)")
        
        print("\n" + "=" * 70)
    
    def _extract_key_reasoning(self, reasoning: str) -> List[str]:
        """Extract key reasoning points from forecast text."""
        import re
        
        lines = [l.strip() for l in reasoning.split('\n') if l.strip()]
        points = []
        seen = set()
        
        # PRIORITY 1: Extract section (e) - the conclusion
        in_conclusion = False
        conclusion_text = []
        
        for line in lines:
            if re.match(r'^[\s]*(?:\(?)[e][\).]\s*', line, re.IGNORECASE):
                in_conclusion = True
                content = re.sub(r'^[\s]*(?:\(?)[e][\).]\s*', '', line, flags=re.IGNORECASE)
                if content and len(content) > 20:
                    conclusion_text.append(content)
                continue
            
            if in_conclusion:
                # Stop if we hit a new section or probability
                if re.match(r'^[\s]*(?:\(?)[a-d][\).]\s*', line, re.IGNORECASE):
                    break
                if 'probability:' in line.lower():
                    break
                conclusion_text.append(line)
        
        if conclusion_text:
            full_conclusion = ' '.join(conclusion_text)
            full_conclusion = re.sub(r'\s+', ' ', full_conclusion).strip()
            # Split into sentences for better readability
            sentences = re.split(r'(?<=[.!?])\s+', full_conclusion)
            for sent in sentences[:3]:  # Up to 3 sentences from conclusion
                if len(sent) > 30:
                    points.append(sent[:200])
        
        # PRIORITY 2: Extract structured items (a, b, c, d...) if conclusion was short
        if len(points) < 2:
            for line in lines:
                match = re.match(r'^[\s]*(?:\(?)([a-d])[\).]\s*(.+)$', line, re.IGNORECASE)
                if match:
                    content = match.group(2).strip()
                    content_lower = content.lower()[:50]
                    if content_lower not in seen and len(content) > 20:
                        seen.add(content_lower)
                        content = re.sub(r'\s+', ' ', content)
                        # Remove the "A brief description..." prefix
                        content = re.sub(r'^A brief description of.+?results in\s*', '', content, flags=re.IGNORECASE)
                        points.append(content[:180])
        
        # If still nothing found, look for conclusion keywords
        if not points:
            for line in lines:
                lower = line.lower()
                if any(x in lower for x in ['conclusion:', 'summary:', 'overall:', 'in summary']):
                    content = line.split(':', 1)[-1].strip()
                    if len(content) > 30:
                        points.append(content[:200])
                        break
        
        return points[:5]  # Limit to 5 points


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
        
        # Get contextualized reasoning
        reasoning_summary = self._extract_reasoning_for_telegram(
            opp.forecast.reasoning, 
            opp.forecast_probability,
            opp.market_probability,
            opp.edge_direction
        )
        
        return f"""{emoji} *{opp.conviction.upper()} CONVICTION OPPORTUNITY*

*{opp.market.title}*

📈 Market: {opp.market_probability:.1%} YES | {1-opp.market_probability:.1%} NO
🤖 AI Forecast: {opp.forecast_probability:.1%} YES | {1-opp.forecast_probability:.1%} NO
💰 Edge: {opp.edge:.1%} → Bet *{opp.edge_direction.upper()}*
📊 Volume: ${opp.market.volume:,.0f}
🎯 Confidence: {opp.forecast.confidence:.0%}

🧠 *AI Reasoning:*
AI predicts {opp.forecast_probability:.0%} YES (market at {opp.market_probability:.0%}) → Bet {opp.edge_direction.upper()}

{reasoning_summary}

[View on Polymarket]({opp.market_url})
"""
    
    def _extract_reasoning_for_telegram(self, reasoning: str, forecast_prob: float, 
                                        market_prob: float, direction: str) -> str:
        """Extract concise reasoning for Telegram format."""
        import re
        
        lines = [l.strip() for l in reasoning.split('\n') if l.strip()]
        
        # Look for section (e) - conclusion
        in_conclusion = False
        conclusion_parts = []
        
        for line in lines:
            if re.match(r'^[\s]*(?:\(?)[e][\).]\s*', line, re.IGNORECASE):
                in_conclusion = True
                content = re.sub(r'^[\s]*(?:\(?)[e][\).]\s*', '', line, flags=re.IGNORECASE)
                if content and len(content) > 20:
                    conclusion_parts.append(content)
                continue
            
            if in_conclusion:
                if re.match(r'^[\s]*(?:\(?)[a-d][\).]\s*', line, re.IGNORECASE):
                    break
                if 'probability:' in line.lower():
                    break
                conclusion_parts.append(line)
        
        if conclusion_parts:
            full_text = ' '.join(conclusion_parts)
            full_text = re.sub(r'\s+', ' ', full_text).strip()
            # Get first 2-3 sentences
            sentences = re.split(r'(?<=[.!?])\s+', full_text)
            summary = ' '.join(sentences[:2])
            return summary[:400] if len(summary) > 400 else summary
        
        # Fallback: look for conclusion keywords
        for line in lines:
            lower = line.lower()
            if any(x in lower for x in ['conclusion:', 'summary:', 'overall:']):
                content = line.split(':', 1)[-1].strip()
                if len(content) > 30:
                    return content[:400]
        
        return "See detailed analysis on Polymarket"


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
        
        # Extract key reasoning points with proper context
        reasoning = self._extract_reasoning_summary(
            opp.forecast.reasoning, 
            opp.forecast_probability,
            opp.market_probability,
            opp.edge_direction
        )
        
        return {
            "title": f"{emoji} {opp.market.title[:250]}",
            "description": f"**{opp.conviction.upper()} CONVICTION** | Edge: {opp.edge:.1%}",
            "color": color,
            "fields": [
                {
                    "name": "📈 Market (Polymarket)",
                    "value": f"YES: {opp.market_probability:.1%}\nNO: {1-opp.market_probability:.1%}",
                    "inline": True,
                },
                {
                    "name": "🤖 AI Forecast",
                    "value": f"YES: {opp.forecast_probability:.1%}\nNO: {1-opp.forecast_probability:.1%}",
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
    
    def _extract_reasoning_summary(self, reasoning: str, forecast_probability: float = 0.5, 
                                     market_probability: float = 0.5, edge_direction: str = "yes") -> str:
        """Extract key reasoning points from forecast text.
        
        The key insight: AI might say "30% YES" and explain why it's unlikely (leaning NO),
        but if market is at 5% YES, the edge is betting YES. The reasoning needs to be
        contextualized to match the action.
        """
        import re
        
        # Split into lines and clean
        lines = [l.strip() for l in reasoning.split('\n') if l.strip()]
        
        # Determine what the forecast is saying relative to the market
        forecast_direction = "YES" if forecast_probability > 0.5 else "NO"
        prob_diff = abs(forecast_probability - market_probability)
        
        # PRIORITY 1: Look for section (e) - the conclusion that explains which outcome is favored
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
                # Frame the conclusion to match the action
                header = f"**AI predicts {forecast_probability:.0%} YES** (vs market {market_probability:.0%}) → Bet {edge_direction.upper()}"
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
                    header = f"**AI predicts {forecast_probability:.0%} YES** (vs market {market_probability:.0%}) → Bet {edge_direction.upper()}"
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
                    # Remove the "A brief description..." prefix
                    content = re.sub(r'^A brief description of a scenario that results in [aA]\s*', '', content)
                    scenarios.append(f"**{letter}:** {content[:180]}")
        
        if scenarios:
            header = f"**AI predicts {forecast_probability:.0%} YES** (vs market {market_probability:.0%}) → Bet {edge_direction.upper()}"
            return f"{header}\n\nKey scenarios:\n" + '\n'.join(scenarios[:2])
        
        # Fallback: just show the forecast vs market comparison
        return f"**AI predicts {forecast_probability:.0%} YES** (vs market {market_probability:.0%}) → Bet {edge_direction.upper()}\n\nSee detailed analysis in logs"


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
