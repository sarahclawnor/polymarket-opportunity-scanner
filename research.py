"""
Research providers for gathering context on markets.
Adapted from Metaculus forecasting-tools.
"""
import os
import asyncio
from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ResearchProvider(ABC):
    """Abstract base for research providers."""
    
    @abstractmethod
    async def research(self, query: str) -> str:
        """Return research context for a query."""
        pass


class PerplexityResearcher(ResearchProvider):
    """
    Perplexity AI for real-time research.
    
    Supports both direct Perplexity API and OpenRouter.
    Set PERPLEXITY_API_KEY for direct API, or use OPENROUTER_API_KEY
    with PERPLEXITY_MODEL environment variable.
    """
    
    # Available Perplexity models via OpenRouter
    # Note: llama-sonar models are not available on OpenRouter
    OPENROUTER_MODELS = {
        "sonar": "perplexity/sonar",
        "sonar-pro": "perplexity/sonar-pro",
        "sonar-reasoning": "perplexity/sonar-reasoning",
        "sonar-deep-research": "perplexity/sonar-deep-research",
    }
    
    # Direct Perplexity API models
    DIRECT_MODELS = {
        "sonar": "sonar",
        "sonar-pro": "sonar-pro",
        "sonar-reasoning": "sonar-reasoning",
        "sonar-deep-research": "sonar-deep-research",
        "llama-sonar-large": "llama-3.1-sonar-large-128k-online",
        "llama-sonar-small": "llama-3.1-sonar-small-128k-online",
    }
    
    DEFAULT_MODEL = "sonar-pro"
    OPENROUTER_DEFAULT = "perplexity/sonar-pro"
    
    # Direct Perplexity API models
    DIRECT_MODELS = {
        "sonar": "sonar",
        "sonar-pro": "sonar-pro",
        "sonar-reasoning": "sonar-reasoning",
        "sonar-deep-research": "sonar-deep-research",
        "llama-sonar-large": "llama-3.1-sonar-large-128k-online",
        "llama-sonar-small": "llama-3.1-sonar-small-128k-online",
    }
    
    DEFAULT_MODEL = "llama-sonar-large"
    OPENROUTER_DEFAULT = "perplexity/llama-3.1-sonar-large-128k-online"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        openrouter_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize Perplexity researcher.
        
        Args:
            api_key: Direct Perplexity API key (optional)
            openrouter_key: OpenRouter API key (optional)
            model: Model to use - can be full model name or short alias:
                   "sonar", "sonar-pro", "sonar-reasoning",
                   "llama-sonar-large" (default), "llama-sonar-small"
        """
        self.direct_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.openrouter_key = openrouter_key or os.getenv("OPENROUTER_API_KEY")
        
        if not (self.direct_key or self.openrouter_key):
            raise ValueError(
                "Either PERPLEXITY_API_KEY or OPENROUTER_API_KEY required"
            )
        
        # Determine which API to use
        self.use_openrouter = not self.direct_key and bool(self.openrouter_key)
        
        # Resolve model name
        model = model or os.getenv("PERPLEXITY_MODEL") or self.DEFAULT_MODEL
        self.model = self._resolve_model(model)
        
        logger.info(f"Using Perplexity via {'OpenRouter' if self.use_openrouter else 'Direct API'} with model: {self.model}")
    
    def _resolve_model(self, model: str) -> str:
        """Resolve model alias to full model name."""
        model = model.lower().strip()
        
        # If it already looks like a full path, use it
        if "/" in model:
            return model
        
        # Use appropriate model map
        model_map = self.OPENROUTER_MODELS if self.use_openrouter else self.DIRECT_MODELS
        
        if model in model_map:
            return model_map[model]
        
        # Fallback: assume it's a valid model name
        logger.warning(f"Unknown model alias '{model}', using as-is")
        return model
    
    async def research(self, query: str) -> str:
        """Perform research using Perplexity."""
        if self.use_openrouter:
            return await self._research_via_openrouter(query)
        else:
            return await self._research_via_direct_api(query)
    
    async def _research_via_direct_api(self, query: str) -> str:
        """Research using direct Perplexity API."""
        import aiohttp
        
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.direct_key}",
            "Content-Type": "application/json",
        }
        
        system_prompt = """You are an assistant to a superforecaster.
The superforecaster will give you a question they intend to forecast on.
To be a great assistant, you generate a concise but detailed rundown of the most relevant news, 
including if the question would resolve Yes or No based on current information.
You do not produce forecasts yourself. Focus on facts and recent developments."""
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "temperature": 0.2,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    
    async def _research_via_openrouter(self, query: str) -> str:
        """Research using OpenRouter with Perplexity model."""
        import aiohttp
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://polymarket-opportunity-scanner.local",
            "X-Title": "Polymarket Opportunity Scanner",
        }
        
        system_prompt = """You are an assistant to a superforecaster.
The superforecaster will give you a question they intend to forecast on.
To be a great assistant, you generate a concise but detailed rundown of the most relevant news, 
including if the question would resolve Yes or No based on current information.
You do not produce forecasts yourself. Focus on facts and recent developments."""
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "temperature": 0.2,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"]


class AskNewsResearcher(ResearchProvider):
    """AskNews for comprehensive news coverage."""
    
    def __init__(self, client_id: Optional[str] = None, secret: Optional[str] = None):
        self.client_id = client_id or os.getenv("ASKNEWS_CLIENT_ID")
        self.secret = secret or os.getenv("ASKNEWS_SECRET")
        if not (self.client_id and self.secret):
            raise ValueError("AskNews client_id and secret required")
    
    async def research(self, query: str) -> str:
        from asknews_sdk import AsyncAskNewsSDK
        
        ask = AsyncAskNewsSDK(
            client_id=self.client_id,
            client_secret=self.secret,
            scopes=["news", "stories"],
        )
        
        # Get latest news (past 48h)
        hot_response = await ask.news.search_news(
            query=query,
            n_articles=5,
            return_type="both",
            strategy="latest news",
        )
        
        # Get historical context (past 60 days)
        historical_response = await ask.news.search_news(
            query=query,
            n_articles=8,
            return_type="both",
            strategy="news knowledge",
        )
        
        # Format results
        sections = ["# Research Report\n"]
        
        if hot_response.as_dicts:
            sections.append("## Latest Developments (Past 48h)\n")
            for article in sorted(hot_response.as_dicts, key=lambda x: x.pub_date, reverse=True)[:5]:
                sections.append(f"**{article.eng_title}**\n{article.summary}\nSource: {article.source_id}\n")
        
        if historical_response.as_dicts:
            sections.append("\n## Background Context (Past 60 Days)\n")
            for article in sorted(historical_response.as_dicts, key=lambda x: x.pub_date, reverse=True)[:5]:
                sections.append(f"**{article.eng_title}**\n{article.summary}\n")
        
        return "\n".join(sections)


class CompositeResearcher(ResearchProvider):
    """Combines multiple research providers."""
    
    def __init__(self, providers: list[ResearchProvider]):
        self.providers = providers
    
    async def research(self, query: str) -> str:
        """Run all providers and combine results."""
        tasks = [p.research(query) for p in self.providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        combined = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Research provider {i} failed: {result}")
                continue
            provider_name = self.providers[i].__class__.__name__
            combined.append(f"\n--- {provider_name} ---\n{result}")
        
        return "\n\n".join(combined)


def get_default_researcher() -> ResearchProvider:
    """Factory for default research provider based on available keys."""
    providers = []
    
    # Try Perplexity (direct or via OpenRouter)
    if os.getenv("PERPLEXITY_API_KEY") or os.getenv("OPENROUTER_API_KEY"):
        try:
            providers.append(PerplexityResearcher())
        except ValueError as e:
            logger.warning(f"Could not initialize Perplexity: {e}")
    
    # Try AskNews
    if os.getenv("ASKNEWS_CLIENT_ID") and os.getenv("ASKNEWS_SECRET"):
        try:
            providers.append(AskNewsResearcher())
        except ValueError as e:
            logger.warning(f"Could not initialize AskNews: {e}")
    
    if not providers:
        raise ValueError(
            "No research provider configured. Set one of:\n"
            "- PERPLEXITY_API_KEY (direct Perplexity)\n"
            "- OPENROUTER_API_KEY (Perplexity via OpenRouter)\n"
            "- ASKNEWS_CLIENT_ID + ASKNEWS_SECRET"
        )
    
    if len(providers) == 1:
        return providers[0]
    
    return CompositeResearcher(providers)
