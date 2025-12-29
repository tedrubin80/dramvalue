"""
Currency conversion utilities for WTracker scrapers.

Provides conversion to USD for consistent price comparison.
"""

import logging
from datetime import date
from typing import Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


# Static exchange rates (updated periodically)
# In production, these should be fetched from an API
DEFAULT_RATES = {
    "USD": Decimal("1.0"),
    "GBP": Decimal("1.27"),    # 1 GBP = 1.27 USD
    "EUR": Decimal("1.08"),    # 1 EUR = 1.08 USD
    "CHF": Decimal("1.12"),    # 1 CHF = 1.12 USD
    "JPY": Decimal("0.0067"),  # 1 JPY = 0.0067 USD
    "AUD": Decimal("0.67"),    # 1 AUD = 0.67 USD
    "CAD": Decimal("0.74"),    # 1 CAD = 0.74 USD
    "HKD": Decimal("0.13"),    # 1 HKD = 0.13 USD
}


class CurrencyConverter:
    """
    Converts prices to USD using exchange rates.

    For MVP, uses static rates. Can be extended to fetch
    live rates from an API like exchangeratesapi.io.
    """

    def __init__(self, rates: dict = None):
        self.rates = rates or DEFAULT_RATES

    def to_usd(
        self,
        amount: float | Decimal,
        currency: str,
        transaction_date: Optional[date] = None,
    ) -> Decimal:
        """
        Convert amount to USD.

        Args:
            amount: Price in original currency
            currency: ISO currency code (GBP, EUR, etc.)
            transaction_date: Date for historical rate (not yet implemented)

        Returns:
            Amount in USD as Decimal
        """
        currency = currency.upper()

        if currency == "USD":
            return Decimal(str(amount))

        rate = self.rates.get(currency)
        if rate is None:
            logger.warning(f"Unknown currency: {currency}, using 1:1 rate")
            rate = Decimal("1.0")

        usd_amount = Decimal(str(amount)) * rate
        return usd_amount.quantize(Decimal("0.01"))

    def get_rate(self, currency: str) -> Decimal:
        """Get exchange rate for currency to USD."""
        return self.rates.get(currency.upper(), Decimal("1.0"))


# Module-level converter instance
_converter = CurrencyConverter()


def convert_to_usd(
    amount: float | Decimal,
    currency: str,
    transaction_date: Optional[date] = None,
) -> Decimal:
    """
    Convert amount to USD.

    Convenience function using module-level converter.
    """
    return _converter.to_usd(amount, currency, transaction_date)
