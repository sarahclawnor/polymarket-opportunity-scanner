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
    """Perplexity AI for real-time research."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            raise ValueError("Perplexity API key required")
    
    async def research(self, query: str) -> str:
        import aiohttp
        
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        system_prompt = """You are an assistant to a superforecaster.
The superforecaster will give you a question they intend to forecast on.
To be a great assistant, you generate a concise but detailed rundown of the most relevant news, 
including if the question would resolve Yes or No based on current information.
You do not produce forecasts yourself. Focus on facts and recent developments."""
        
        payload = {
            "model": "llama-3.1-sonar-large-128k-online",
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
    
    if os.getenv("PERPLEXITY_API_KEY"):
        providers.append(PerplexityResearcher())
    
    if os.getenv("ASKNEWS_CLIENT_ID") and os.getenv("ASKNEWS_SECRET"):
        providers.append(AskNewsResearcher())
    
    if not providers:
        raise ValueError("No research provider configured. Set PERPLEXITY_API_KEY or AskNews credentials.")
    
    if len(providers) == 1:
        return providers[0]
    
    return CompositeResearcher(providers)
