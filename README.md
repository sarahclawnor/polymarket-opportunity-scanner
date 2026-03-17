# Polymarket Opportunity Scanner

AI-powered market scanner that identifies potentially mispriced markets on Polymarket using research-driven forecasting.

Based on the [Metaculus AI Forecasting Bot Template](https://github.com/Metaculus/metac-bot-template).

## Overview

This scanner:
1. Discovers active Polymarket markets via Gamma API
2. Performs AI-powered research on each market topic
3. Generates probabilistic forecasts using LLMs
4. Compares predictions against market prices
5. Alerts on significant mispricings (opportunities)

## Project Status: POC

Current capabilities:
- ✅ Market discovery from Polymarket
- ✅ AI research integration (Perplexity, AskNews)
- ✅ Binary forecasting engine
- ✅ Mispricing detection
- ✅ Alert output (console/JSON)
- 🚧 Trading execution (not implemented)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

# Run scanner
python main.py --min-confidence 0.7 --min-edge 0.15
```

## Architecture

```
main.py
├── gamma_client.py      # Polymarket market discovery
├── research/            # News/research providers
│   ├── perplexity.py
│   ├── asknews.py
│   └── smart_searcher.py
├── forecasting/         # Forecasting engine
│   └── binary_forecaster.py
├── analysis/            # Mispricing detection
│   └── opportunity_detector.py
└── alerts/              # Alert handlers
    └── console_alerts.py
```

## Configuration

See `config.yaml` for all settings:
- Market filters (volume, closing soon, etc.)
- Research providers
- Forecasting parameters
- Alert thresholds

## License

MIT
