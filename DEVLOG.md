# Development Notes

## TODO

### MVP (Current)
- [x] Gamma API client for market discovery
- [x] Research providers (Perplexity, AskNews)
- [x] Binary forecasting engine
- [x] Opportunity detection
- [x] Console alerts
- [x] JSON output

### Near-term
- [ ] Add config.yaml loader
- [ ] Telegram alert integration
- [ ] Discord webhook alerts
- [ ] Market history caching
- [ ] Opportunity tracking (don't re-alert)
- [ ] Confidence calibration tracking
- [ ] Backtesting framework

### Future
- [ ] Real-time market streaming
- [ ] Position sizing model
- [ ] Wallet integration (actual trading)
- [ ] Subgraph integration for historical data
- [ ] Multi-model ensemble forecasting
- [ ] Automated performance tracking

## Architecture Decisions

1. **Async throughout** - All I/O (APIs, LLMs) is async for efficiency
2. **Modular providers** - Easy to swap research sources or LLMs
3. **Separation of concerns** - Research → Forecast → Detect → Alert
4. **No trading yet** - Alerts only until confidence established

## Research Provider Notes

### Perplexity
- Pros: Real-time search, fast, cost-effective
- Cons: Sometimes misses niche topics

### AskNews  
- Pros: Deep archive, structured data
- Cons: Requires separate auth, rate limits

### Composite (both)
- Best coverage but higher latency

## Forecasting Strategy

Based on Metaculus template:
1. Multiple inference runs (default 3)
2. Median aggregation (robust to outliers)
3. Confidence from variance across runs
4. Structured prompting for consistency
