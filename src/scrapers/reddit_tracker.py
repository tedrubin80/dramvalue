"""
Reddit sentiment tracker for whisky price discussions.

Monitors r/whiskey, r/bourbon, r/scotch and related subreddits
for price mentions and market sentiment.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

import praw
from praw.models import Submission, Comment

logger = logging.getLogger(__name__)


@dataclass
class PriceMention:
    """Represents a price mention found on Reddit."""
    subreddit: str
    post_id: str
    post_title: str
    post_url: str
    author: str
    created_utc: datetime
    bottle_name: Optional[str]
    price: Optional[float]
    currency: str
    context: str  # The text containing the price mention
    sentiment: str  # "positive", "negative", "neutral"
    mention_type: str  # "asking", "offering", "discussing", "complaint"


class RedditSentimentTracker:
    """
    Tracks whisky price discussions on Reddit.

    Monitors subreddits for:
    - Price mentions (e.g., "paid $150 for...")
    - Market sentiment (complaints about pricing, hype)
    - Secondary market activity discussions
    """

    # Subreddits to monitor
    SUBREDDITS = [
        "whiskey",
        "bourbon",
        "scotch",
        "worldwhisky",
        "WhiskyDFW",
        "dcwhisky",
        "PLCB",  # Pennsylvania liquor
    ]

    # Price patterns to look for
    PRICE_PATTERNS = [
        r"\$(\d{1,4}(?:,\d{3})?(?:\.\d{2})?)",  # $150, $1,500
        r"(\d{1,4}(?:,\d{3})?)\s*(?:dollars|USD)",  # 150 dollars
        r"£(\d{1,4}(?:,\d{3})?(?:\.\d{2})?)",  # £150
        r"€(\d{1,4}(?:,\d{3})?(?:\.\d{2})?)",  # €150
    ]

    # Keywords indicating secondary market discussion
    SECONDARY_KEYWORDS = [
        "secondary", "resale", "flip", "flipping",
        "markup", "over msrp", "above msrp",
        "paid", "worth", "value",
        "tater", "allocated", "unicorn",
    ]

    # Sentiment indicators
    NEGATIVE_WORDS = [
        "overpriced", "ridiculous", "insane", "crazy",
        "gouging", "robbery", "rip off", "ripoff",
        "not worth", "pass", "avoid", "scam",
    ]

    POSITIVE_WORDS = [
        "great deal", "steal", "bargain", "worth it",
        "fair price", "good price", "reasonable",
        "lucky", "score", "found",
    ]

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str = "DramValue Sentiment Tracker v1.0",
    ):
        """
        Initialize Reddit tracker.

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string for API requests
        """
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self.reddit.read_only = True

    def search_price_mentions(
        self,
        subreddits: list[str] = None,
        time_filter: str = "week",
        limit: int = 100,
    ) -> list[PriceMention]:
        """
        Search for price mentions in whisky subreddits.

        Args:
            subreddits: List of subreddits to search (default: SUBREDDITS)
            time_filter: Time period ("hour", "day", "week", "month", "year")
            limit: Maximum posts to check per subreddit

        Returns:
            List of PriceMention objects
        """
        if subreddits is None:
            subreddits = self.SUBREDDITS

        mentions = []

        for subreddit_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)

                # Search for price-related posts
                for submission in subreddit.search(
                    "price OR paid OR msrp OR secondary",
                    time_filter=time_filter,
                    limit=limit,
                ):
                    post_mentions = self._extract_mentions_from_post(submission)
                    mentions.extend(post_mentions)

                # Also check hot posts
                for submission in subreddit.hot(limit=min(50, limit)):
                    post_mentions = self._extract_mentions_from_post(submission)
                    mentions.extend(post_mentions)

            except Exception as e:
                logger.error(f"Error searching r/{subreddit_name}: {e}")
                continue

        return mentions

    def get_trending_bottles(
        self,
        subreddits: list[str] = None,
        time_filter: str = "week",
        limit: int = 50,
    ) -> dict[str, int]:
        """
        Get bottles that are being discussed frequently.

        Returns:
            Dict mapping bottle names to mention counts
        """
        if subreddits is None:
            subreddits = self.SUBREDDITS

        bottle_mentions = {}

        for subreddit_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)

                for submission in subreddit.hot(limit=limit):
                    bottles = self._extract_bottle_names(
                        f"{submission.title} {submission.selftext}"
                    )
                    for bottle in bottles:
                        bottle_mentions[bottle] = bottle_mentions.get(bottle, 0) + 1

            except Exception as e:
                logger.error(f"Error getting trending from r/{subreddit_name}: {e}")

        # Sort by frequency
        return dict(
            sorted(bottle_mentions.items(), key=lambda x: x[1], reverse=True)
        )

    def get_sentiment_summary(
        self,
        subreddits: list[str] = None,
        time_filter: str = "week",
    ) -> dict:
        """
        Get overall sentiment summary for the whisky market.

        Returns:
            Dict with sentiment metrics
        """
        mentions = self.search_price_mentions(
            subreddits=subreddits,
            time_filter=time_filter,
            limit=200,
        )

        if not mentions:
            return {
                "total_mentions": 0,
                "positive_pct": 0,
                "negative_pct": 0,
                "neutral_pct": 0,
                "avg_price_mentioned": None,
            }

        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        prices = []

        for mention in mentions:
            sentiment_counts[mention.sentiment] += 1
            if mention.price:
                prices.append(mention.price)

        total = len(mentions)
        return {
            "total_mentions": total,
            "positive_pct": round(sentiment_counts["positive"] / total * 100, 1),
            "negative_pct": round(sentiment_counts["negative"] / total * 100, 1),
            "neutral_pct": round(sentiment_counts["neutral"] / total * 100, 1),
            "avg_price_mentioned": round(sum(prices) / len(prices), 2) if prices else None,
            "price_mentions": len(prices),
        }

    def _extract_mentions_from_post(
        self,
        submission: Submission,
    ) -> list[PriceMention]:
        """Extract price mentions from a Reddit post."""
        mentions = []

        # Check title and body
        full_text = f"{submission.title} {submission.selftext}"

        if self._has_price_discussion(full_text):
            mention = self._create_mention(
                submission=submission,
                text=full_text,
            )
            if mention:
                mentions.append(mention)

        # Check top comments
        submission.comments.replace_more(limit=0)
        for comment in submission.comments[:20]:
            if self._has_price_discussion(comment.body):
                mention = self._create_mention(
                    submission=submission,
                    text=comment.body,
                    comment=comment,
                )
                if mention:
                    mentions.append(mention)

        return mentions

    def _create_mention(
        self,
        submission: Submission,
        text: str,
        comment: Comment = None,
    ) -> Optional[PriceMention]:
        """Create a PriceMention from text."""
        price, currency = self._extract_price(text)
        bottle_names = self._extract_bottle_names(text)
        sentiment = self._analyze_sentiment(text)
        mention_type = self._classify_mention(text)

        return PriceMention(
            subreddit=submission.subreddit.display_name,
            post_id=submission.id,
            post_title=submission.title,
            post_url=f"https://reddit.com{submission.permalink}",
            author=str(comment.author if comment else submission.author),
            created_utc=datetime.utcfromtimestamp(
                comment.created_utc if comment else submission.created_utc
            ),
            bottle_name=bottle_names[0] if bottle_names else None,
            price=price,
            currency=currency,
            context=text[:500],
            sentiment=sentiment,
            mention_type=mention_type,
        )

    def _has_price_discussion(self, text: str) -> bool:
        """Check if text contains price discussion."""
        text_lower = text.lower()

        # Must have price pattern or secondary keyword
        has_price = any(
            re.search(pattern, text) for pattern in self.PRICE_PATTERNS
        )
        has_keyword = any(
            keyword in text_lower for keyword in self.SECONDARY_KEYWORDS
        )

        return has_price or has_keyword

    def _extract_price(self, text: str) -> tuple[Optional[float], str]:
        """Extract price and currency from text."""
        for pattern in self.PRICE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                price_str = match.group(1).replace(",", "")
                try:
                    price = float(price_str)
                    # Determine currency
                    if "£" in pattern:
                        return price, "GBP"
                    elif "€" in pattern:
                        return price, "EUR"
                    return price, "USD"
                except ValueError:
                    continue

        return None, "USD"

    def _extract_bottle_names(self, text: str) -> list[str]:
        """Extract potential bottle names from text."""
        # Common distillery/brand patterns
        distilleries = [
            "buffalo trace", "blanton", "eagle rare", "weller",
            "pappy", "van winkle", "eh taylor", "stagg",
            "macallan", "glenfiddich", "glenlivet", "lagavulin",
            "ardbeg", "laphroaig", "talisker", "oban",
            "hibiki", "yamazaki", "hakushu", "nikka",
            "redbreast", "green spot", "yellow spot",
            "maker's mark", "woodford", "four roses", "wild turkey",
        ]

        found = []
        text_lower = text.lower()

        for distillery in distilleries:
            if distillery in text_lower:
                # Try to get more context
                pattern = rf"({distillery}[\w\s]*?\d*\s*(?:year|yr)?)"
                match = re.search(pattern, text_lower)
                if match:
                    found.append(match.group(1).strip().title())
                else:
                    found.append(distillery.title())

        return list(set(found))

    def _analyze_sentiment(self, text: str) -> str:
        """Analyze sentiment of text."""
        text_lower = text.lower()

        negative_count = sum(1 for w in self.NEGATIVE_WORDS if w in text_lower)
        positive_count = sum(1 for w in self.POSITIVE_WORDS if w in text_lower)

        if negative_count > positive_count:
            return "negative"
        elif positive_count > negative_count:
            return "positive"
        return "neutral"

    def _classify_mention(self, text: str) -> str:
        """Classify the type of price mention."""
        text_lower = text.lower()

        if any(w in text_lower for w in ["selling", "asking", "wts", "for sale"]):
            return "offering"
        elif any(w in text_lower for w in ["looking for", "wtb", "want to buy"]):
            return "asking"
        elif any(w in text_lower for w in ["paid", "bought", "picked up", "found"]):
            return "discussing"
        elif any(w in text_lower for w in self.NEGATIVE_WORDS):
            return "complaint"

        return "discussing"
