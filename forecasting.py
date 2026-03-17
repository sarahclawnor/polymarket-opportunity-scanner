"""
Binary forecasting engine adapted from Metaculus bot template.
Generates probabilistic forecasts for Yes/No markets.
"""
import os
import asyncio
from datetime import datetime
from typing import List, Tuple, Optional
from dataclasses import dataclass
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    """Result of a forecast run."""
    probability_yes: float  # 0-1
    reasoning: str
    confidence: float  # 0-1, based on model consistency
    num_runs: int


class BinaryForecaster:
    """
    Forecasts binary (Yes/No) market outcomes.
    
    Adapted from Metaculus SpringTemplateBot2026.
    Uses multiple inference runs and aggregates results.
    """
    
    FORECAST_PROMPT_TEMPLATE = """You are a professional forecaster interviewing for a job.

Your interview question is:
{question}

Background information:
{background}

Your research assistant says:
{research}

Today is {today}.

Before answering you write:
(a) The time left until the outcome is known.
(b) The status quo outcome if nothing changed.
(c) A brief description of a scenario that results in a No outcome.
(d) A brief description of a scenario that results in a Yes outcome.

You write your rationale remembering that good forecasters put extra weight on the status quo 
outcome since the world changes slowly most of the time. Be specific and cite relevant facts.

The last thing you write is your final answer as: "Probability: ZZ%", where ZZ is between 0-100.
"""
    
    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        num_runs: int = 3,
        api_key: Optional[str] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.num_runs = num_runs
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1" if os.getenv("OPENROUTER_API_KEY") else None,
        )
        self.semaphore = asyncio.Semaphore(3)  # Concurrency limit
    
    async def forecast(
        self,
        question: str,
        background: str,
        research: str,
    ) -> ForecastResult:
        """
        Generate forecast for a binary question.
        
        Args:
            question: The market question
            background: Additional context (description, resolution criteria)
            research: Research findings from news sources
        
        Returns:
            ForecastResult with probability and reasoning
        """
        prompt = self.FORECAST_PROMPT_TEMPLATE.format(
            question=question,
            background=background,
            research=research,
            today=datetime.now().strftime("%Y-%m-%d"),
        )
        
        # Run multiple forecasts for aggregation
        tasks = [self._single_forecast(prompt) for _ in range(self.num_runs)]
        results = await asyncio.gather(*tasks)
        
        probabilities = [r[0] for r in results]
        reasonings = [r[1] for r in results]
        
        # Calculate median probability
        median_prob = sorted(probabilities)[len(probabilities) // 2]
        
        # Confidence based on variance across runs
        variance = sum((p - median_prob) ** 2 for p in probabilities) / len(probabilities)
        confidence = max(0, 1 - (variance * 4))  # Normalize to 0-1
        
        # Combine reasoning
        combined_reasoning = self._combine_reasonings(reasonings, probabilities, median_prob)
        
        logger.info(f"Forecast complete: {median_prob:.1%} (confidence: {confidence:.2f})")
        
        return ForecastResult(
            probability_yes=median_prob,
            reasoning=combined_reasoning,
            confidence=confidence,
            num_runs=self.num_runs,
        )
    
    async def _single_forecast(self, prompt: str) -> Tuple[float, str]:
        """Run a single forecast inference."""
        async with self.semaphore:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            )
            
            reasoning = response.choices[0].message.content
            probability = self._extract_probability(reasoning)
            
            return probability, reasoning
    
    def _extract_probability(self, text: str) -> float:
        """Extract probability from forecast text."""
        import re
        
        # Look for "Probability: XX%" pattern
        match = re.search(r'probability[:\s]*(\d+)%', text, re.IGNORECASE)
        if match:
            prob = int(match.group(1)) / 100
            return max(0.01, min(0.99, prob))  # Clamp to valid range
        
        # Fallback: look for any percentage
        matches = re.findall(r'(\d+)%', text)
        if matches:
            prob = int(matches[-1]) / 100
            return max(0.01, min(0.99, prob))
        
        # Last resort: look for decimal probabilities
        matches = re.findall(r'\b(0\.\d{1,3})\b', text)
        if matches:
            return max(0.01, min(0.99, float(matches[-1])))
        
        logger.warning(f"Could not extract probability from: {text[:200]}...")
        return 0.5  # Neutral fallback
    
    def _combine_reasonings(
        self,
        reasonings: List[str],
        probabilities: List[float],
        median_prob: float,
    ) -> str:
        """Combine multiple reasoning outputs into summary."""
        sections = [
            f"## Forecast Summary\n",
            f"**Median Probability:** {median_prob:.1%}",
            f"**Run Range:** {min(probabilities):.1%} - {max(probabilities):.1%}",
            f"**Individual Runs:** {', '.join(f'{p:.1%}' for p in probabilities)}\n",
            "## Selected Rationale (closest to median):\n",
        ]
        
        # Find reasoning closest to median
        closest_idx = min(
            range(len(probabilities)),
            key=lambda i: abs(probabilities[i] - median_prob),
        )
        sections.append(reasonings[closest_idx])
        
        return "\n".join(sections)
