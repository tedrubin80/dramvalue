"""
Scrapy item pipelines for WTracker.

Pipeline execution order (by priority):
1. ValidationPipeline (100) - Validates required fields and data integrity
2. NormalizationPipeline (200) - Matches/creates bottles, normalizes names
3. DeduplicationPipeline (300) - Checks for existing records
4. DatabasePipeline (400) - Persists to PostgreSQL with audit logging
"""

from src.scrapers.pipelines.validation import ValidationPipeline
from src.scrapers.pipelines.normalization import NormalizationPipeline
from src.scrapers.pipelines.deduplication import DeduplicationPipeline
from src.scrapers.pipelines.database import DatabasePipeline

__all__ = [
    "ValidationPipeline",
    "NormalizationPipeline",
    "DeduplicationPipeline",
    "DatabasePipeline",
]
