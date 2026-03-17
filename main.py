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
from alerts import (
    AlertHandler,
    ConsoleAlerts,
    JSONAlerts,
    TelegramAlerts,
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
    ):
        self.researcher = researcher or get_default_researcher()
        self.forecaster = forecaster or BinaryForecaster()
        self.detector = detector or OpportunityDetector()
        self.alerter = alerter or ConsoleAlerts()
        self.max_markets = max_markets
    
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
            
            logger.info(f"Analyzing {len(markets)} markets...")
            
            # 2. Analyze each market
            for i, market in enumerate(markets, 1):
                logger.info(f"[{i}/{len(markets)}] Analyzing: {market.title[:60]}...")
                
                try:
                    opportunity = await self._analyze_market(market)
                    if opportunity:
                        opportunities.append(opportunity)
                        logger.info(f"  ✓ Opportunity detected: {opportunity.edge:.1%} edge")
                    else:
                        logger.info(f"  ✗ No opportunity detected")
                except Exception as e:
                    logger.error(f"  ✗ Failed to analyze market: {e}")
                    continue
        
        # 3. Rank and alert
        ranked = self.detector.rank_opportunities(opportunities)
        
        logger.info(f"\nScan complete. Found {len(ranked)} opportunities.")
        
        await self.alerter.send(ranked)
        
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
        default=100000,
        help="Minimum market volume in USD (default: 100000)",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=30,
        help="Only scan markets closing within N days (default: 30)",
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Filter by category (e.g., Politics, Crypto, Sports)",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=20,
        help="Maximum markets to analyze (default: 20)",
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
