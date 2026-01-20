"""
AI-powered services using Perplexity API.

Provides intelligent search, bottle research, and market insights.
"""

import os
from typing import Any

from perplexity import Perplexity


class AIService:
    """
    AI service powered by Perplexity for whisky intelligence.

    Features:
    - Smart bottle search with context
    - Bottle information enrichment
    - Market research and analysis
    - Price valuation assistance
    """

    def __init__(self, api_key: str | None = None):
        """Initialize with API key from env or parameter."""
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY not set")
        self.client = Perplexity(api_key=self.api_key)

    async def search_whisky(self, query: str) -> dict[str, Any]:
        """
        AI-enhanced whisky search.

        Uses Perplexity to understand the query and provide relevant results
        with context about the whisky.
        """
        prompt = f"""You are a whisky expert assistant. The user is searching for: "{query}"

Provide a helpful response that includes:
1. What specific bottle(s) they might be looking for
2. Key details about the whisky (distillery, age, flavor profile if known)
3. General price range if known (secondary market)
4. Any notable facts or recent news

Keep the response concise and factual. Format as JSON with keys:
- bottles: list of bottle names that match
- details: brief description
- price_range: estimated range or "varies"
- notes: any relevant context"""

        try:
            response = self.client.chat.completions.create(
                model="sonar",
                messages=[
                    {"role": "system", "content": "You are a knowledgeable whisky expert helping users find and understand whisky bottles and their values."},
                    {"role": "user", "content": prompt}
                ]
            )

            content = response.choices[0].message.content
            return {
                "success": True,
                "query": query,
                "response": content,
                "model": "sonar",
            }
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": str(e),
            }

    async def get_bottle_info(self, bottle_name: str) -> dict[str, Any]:
        """
        Get detailed information about a specific bottle.

        Enriches bottle data with AI-researched information.
        """
        prompt = f"""Provide detailed information about this whisky bottle: "{bottle_name}"

Include:
1. Distillery and region
2. Age statement (if applicable)
3. Flavor profile and tasting notes
4. Production details (cask type, ABV if standard)
5. Historical context or notable releases
6. Approximate secondary market value range (USD)

Be factual and concise. If you're uncertain about specific details, say so."""

        try:
            response = self.client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a whisky encyclopedia providing accurate, detailed information about whisky bottles."},
                    {"role": "user", "content": prompt}
                ]
            )

            return {
                "success": True,
                "bottle_name": bottle_name,
                "info": response.choices[0].message.content,
                "model": "sonar-pro",
            }
        except Exception as e:
            return {
                "success": False,
                "bottle_name": bottle_name,
                "error": str(e),
            }

    async def analyze_market(self, category: str = "scotch whisky") -> dict[str, Any]:
        """
        Get AI-powered market analysis for a category.

        Provides current trends, notable bottles, and market insights.
        """
        prompt = f"""Provide a current market analysis for {category} on the secondary/auction market.

Include:
1. Current market trends (rising, falling, stable)
2. Hot bottles or distilleries seeing increased demand
3. Value opportunities (undervalued bottles)
4. Recent notable auction results
5. Factors affecting prices (closures, limited releases, etc.)

Focus on actionable insights for collectors and investors. Be specific with bottle names where relevant."""

        try:
            response = self.client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a whisky market analyst providing insights on secondary market trends and values."},
                    {"role": "user", "content": prompt}
                ],
            )

            return {
                "success": True,
                "category": category,
                "analysis": response.choices[0].message.content,
                "model": "sonar-pro",
            }
        except Exception as e:
            return {
                "success": False,
                "category": category,
                "error": str(e),
            }

    async def estimate_value(
        self,
        bottle_name: str,
        condition: str = "good",
        has_box: bool = True
    ) -> dict[str, Any]:
        """
        Get AI-assisted value estimation for a bottle.

        Combines web knowledge with market understanding.
        """
        box_status = "with original box/packaging" if has_box else "without box"

        prompt = f"""Estimate the current secondary market value for:

Bottle: {bottle_name}
Condition: {condition}
Packaging: {box_status}

Provide:
1. Estimated value range (low - high in USD)
2. Confidence level (high/medium/low)
3. Key factors affecting this valuation
4. Recent comparable sales if known
5. Whether this is a good buy at current market prices

Be specific and cite sources where possible."""

        try:
            response = self.client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a whisky valuation expert helping collectors understand the market value of their bottles."},
                    {"role": "user", "content": prompt}
                ],
            )

            return {
                "success": True,
                "bottle_name": bottle_name,
                "condition": condition,
                "has_box": has_box,
                "valuation": response.choices[0].message.content,
                "model": "sonar-pro",
            }
        except Exception as e:
            return {
                "success": False,
                "bottle_name": bottle_name,
                "error": str(e),
            }

    async def compare_bottles(self, bottles: list[str]) -> dict[str, Any]:
        """
        Compare multiple bottles for investment or drinking.
        """
        bottles_str = ", ".join(bottles)

        prompt = f"""Compare these whisky bottles: {bottles_str}

For each bottle, provide:
1. Current approximate value (USD)
2. Investment potential (appreciation likelihood)
3. Drinking quality (if opened)
4. Rarity/availability

Then provide:
- Overall recommendation for collectors
- Best value pick
- Best investment pick
- Best drinking pick

Be concise but specific."""

        try:
            response = self.client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a whisky expert helping collectors compare bottles for purchase decisions."},
                    {"role": "user", "content": prompt}
                ],
            )

            return {
                "success": True,
                "bottles": bottles,
                "comparison": response.choices[0].message.content,
                "model": "sonar-pro",
            }
        except Exception as e:
            return {
                "success": False,
                "bottles": bottles,
                "error": str(e),
            }

    async def research_topic(self, topic: str) -> dict[str, Any]:
        """
        Research any whisky-related topic using AI.

        General-purpose research method for flexible queries.
        """
        prompt = f"""Research the following topic thoroughly: {topic}

Provide comprehensive, well-organized information with:
1. Key facts and details
2. Current status/trends (if applicable)
3. Notable examples or specifics
4. Pros and cons (if comparing options)
5. Recommendations or actionable insights

Format the response clearly with sections. Be specific and cite sources where possible."""

        try:
            response = self.client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a knowledgeable researcher providing detailed, accurate information about whisky-related topics."},
                    {"role": "user", "content": prompt}
                ],
            )

            return {
                "success": True,
                "topic": topic,
                "research": response.choices[0].message.content,
                "model": "sonar-pro",
            }
        except Exception as e:
            return {
                "success": False,
                "topic": topic,
                "error": str(e),
            }


# Singleton instance
_ai_service: AIService | None = None


def get_ai_service() -> AIService:
    """Get or create the AI service instance."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
