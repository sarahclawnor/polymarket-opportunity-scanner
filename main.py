"""
Polymarket Opportunity Scanner

Main entry point - discovers markets, forecasts outcomes, detects mispricings.
Based on Metaculus AI Forecasting Bot Template.
"""
import os
import asyncio
import argparse
import logging
from typing import List, Optional
from datetime import datetime

from dotenv import load_dotenv

from gamma_client import GammaClient, Market
from research import get_default_researcher, ResearchProvider
from forecasting import BinaryForecaster, ForecastResult
from opportunity_detector import OpportunityDetector, Opportunity
from alert_history import AlertHistory
from history import HistoryLogger
from alerts import (
    AlertHandler,
    ConsoleAlerts,
    JSONAlerts,
    TelegramAlerts,
    DiscordAlerts,
    CompositeAlerts,
)

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class OpportunityScanner:
    """Main scanner orchestrating market discovery, forecasting, and alerts."""
    
    def __init__(
        self,
        researcher: Optional[ResearchProvider] = None,
        forecaster: Optional[BinaryForecaster] = None,
        detector: Optional[OpportunityDetector] = None,
        alerter: Optional[AlertHandler] = None,
        max_markets: int = 20,
        alert_history: Optional[AlertHistory] = None,
        history_logger: Optional[HistoryLogger] = None,
        skip_alerted: bool = True,
    ):
        self.researcher = researcher or get_default_researcher()
        self.forecaster = forecaster or BinaryForecaster()
        self.detector = detector or OpportunityDetector()
        self.alerter = alerter or ConsoleAlerts()
        self.max_markets = max_markets
        self.alert_history = alert_history or AlertHistory()
        self.history_logger = history_logger or HistoryLogger()
        self.skip_alerted = skip_alerted
    
    async def scan(
        self,
        min_volume: float = 100000,
        max_days_to_close: Optional[int] = 30,
        category: Optional[str] = None,
    ) -> List[Opportunity]:
        """
        Run full scanning pipeline.
        
        Args:
            min_volume: Minimum market volume in USD
            max_days_to_close: Only scan markets closing within N days
            category: Filter by market category
        
        Returns:
            List of detected opportunities
        """
        opportunities = []
        skipped_already_alerted = 0
        skipped_past_close = 0
        
        async with GammaClient() as client:
            # 1. Discover markets
            logger.info(f"Fetching markets (min_volume=${min_volume:,.0f})...")
            markets = await client.get_active_markets(
                min_volume=min_volume,
                max_days_to_close=max_days_to_close,
                limit=self.max_markets,
                category=category,
            )
            
            if not markets:
                logger.warning("No markets found matching criteria")
                return []
            
            logger.info(f"Found {len(markets)} markets, starting analysis...")
            
            # 2. Analyze each market
            for i, market in enumerate(markets, 1):
                # Skip markets that are past their close date
                if market.days_until_close is not None and market.days_until_close < 0:
                    logger.debug(f"Skipping {market.slug}: Past close date ({market.days_until_close:.0f} days)")
                    skipped_past_close += 1
                    continue
                
                logger.info(f"[{i}/{len(markets)}] Analyzing: {market.title[:60]}...")
                
                try:
                    opportunity = await self._analyze_market(market)
                    if opportunity:
                        # Check if we should alert on this opportunity
                        if self.skip_alerted:
                            should_alert = self.alert_history.should_alert(
                                market_id=market.id,
                                market_probability=opportunity.market_probability,
                                forecast_probability=opportunity.forecast_probability,
                            )
                            if not should_alert:
                                logger.info(f"  ⊘ Already alerted (skipped)")
                                skipped_already_alerted += 1
                                continue
                        
                        opportunities.append(opportunity)
                        logger.info(f"  ✓ Opportunity detected: {opportunity.edge:.1%} edge")
                        
                        # Record that we're alerting on this
                        self.alert_history.record_alert(opportunity)
                    else:
                        logger.info(f"  ✗ No opportunity detected")
                except Exception as e:
                    logger.error(f"  ✗ Failed to analyze market: {e}")
                    continue
        
        # 3. Rank and alert
        ranked = self.detector.rank_opportunities(opportunities)
        
        logger.info(f"\n{'='*70}")
        logger.info(f"Scan complete: {len(ranked)} new opportunities")
        logger.info(f"  - Skipped (already alerted): {skipped_already_alerted}")
        logger.info(f"  - Skipped (past close date): {skipped_past_close}")
        
        stats = self.alert_history.get_stats()
        logger.info(f"  - Total markets in history: {stats['total_markets_alerted']}")
        logger.info(f"{'='*70}")
        
        # Only send alerts if we have new opportunities
        if ranked:
            await self.alerter.send(ranked)
        else:
            logger.info("No new opportunities to alert - skipping notifications")

        # Always log scan results to daily history file
        self.history_logger.log_scan(ranked)

        return ranked
    
    async def _analyze_market(self, market: Market) -> Optional[Opportunity]:
        """Analyze a single market for opportunity."""
        
        # 2a. Research
        logger.debug(f"  Researching: {market.question}")
        research = await self.researcher.research(market.question)
        
        # 2b. Forecast
        logger.debug(f"  Forecasting...")
        background = f"""
Description: {market.description}
Category: {market.category}
End Date: {market.end_date}
Resolution Source: {market.resolution_source or "Not specified"}
"""
        forecast = await self.forecaster.forecast(
            question=market.question,
            background=background,
            research=research,
        )
        
        # 2c. Detect opportunity
        return self.detector.analyze(market, forecast)


def create_alerter(args) -> AlertHandler:
    """Factory for alert handler based on args/env."""
    handlers = [ConsoleAlerts()]
    
    # Add JSON output if requested
    if args.output:
        handlers.append(JSONAlerts(args.output))
    
    # Add Telegram if configured
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.getenv("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat:
        handlers.append(TelegramAlerts(telegram_token, telegram_chat))

    # Add Discord if configured
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_webhook:
        handlers.append(DiscordAlerts(discord_webhook))

    if len(handlers) == 1:
        return handlers[0]

    return CompositeAlerts(handlers)


def main():
    parser = argparse.ArgumentParser(
        description="Polymarket Opportunity Scanner - AI-powered mispricing detection"
    )
    
    # Market filters
    parser.add_argument(
        "--min-volume",
        type=float,
        default=10000,
        help="Minimum market volume in USD (default: 10000)",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=None,
        help="Only scan markets closing within N days (default: no limit)",
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Filter by category (e.g., Politics, Crypto, Sports)",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=100,
        help="Maximum markets to analyze (default: 100)",
    )
    
    # Forecasting settings
    parser.add_argument(
        "--forecast-runs",
        type=int,
        default=3,
        help="Number of forecast runs per market (default: 3)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="LLM model for forecasting (default: gpt-4o)",
    )
    
    # Opportunity detection
    parser.add_argument(
        "--min-edge",
        type=float,
        default=0.10,
        help="Minimum edge to flag opportunity (default: 0.10 = 10%%)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="Minimum forecast confidence (default: 0.5)",
    )
    
    # Deduplication
    parser.add_argument(
        "--skip-alerted",
        action="store_true",
        default=True,
        help="Skip markets already alerted (default: True)",
    )
    parser.add_argument(
        "--no-skip-alerted",
        dest="skip_alerted",
        action="store_false",
        help="Re-alert on all opportunities regardless of history",
    )

    # Output
    parser.add_argument(
        "--output",
        type=str,
        help="Save opportunities to JSON file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Build components
    alerter = create_alerter(args)
    alert_history = AlertHistory()
    
    scanner = OpportunityScanner(
        forecaster=BinaryForecaster(
            model=args.model,
            num_runs=args.forecast_runs,
        ),
        detector=OpportunityDetector(
            min_edge=args.min_edge,
            min_confidence=args.min_confidence,
        ),
        alerter=alerter,
        max_markets=args.max_markets,
        alert_history=alert_history,
        skip_alerted=args.skip_alerted,
    )
    
    # Run scan
    try:
        opportunities = asyncio.run(scanner.scan(
            min_volume=args.min_volume,
            max_days_to_close=args.max_days,
            category=args.category,
        ))
        
        # Exit code based on results
        exit(0 if opportunities else 1)
        
    except KeyboardInterrupt:
        logger.info("Scan interrupted by user")
        exit(130)
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()
