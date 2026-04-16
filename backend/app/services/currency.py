"""Currency normalization helpers for subunit (minor) currency codes.

Some exchanges quote prices in subunit currencies (e.g. London Stock Exchange
quotes in pence 'GBp', 1/100 of GBP). yfinance returns these as-is, so we
must normalize before FX conversion or storing to DB.
"""

# Subunit (minor) currency codes that equal a fraction of a major currency
# Format: raw_code -> (major_code, divisor)
SUBUNIT_MAP: dict[str, tuple[str, float]] = {
    "GBp": ("GBP", 100),    # LSE pence
    "GBX": ("GBP", 100),    # alternate LSE pence code
    "ZAC": ("ZAR", 100),    # JSE (Johannesburg) cents
    "ILA": ("ILS", 100),    # TASE (Tel Aviv) agorot
    "KWF": ("KWD", 1000),   # Kuwait fils (KWD has 3 decimal places)
}


def normalize_currency(raw_ccy: str) -> tuple[str, float]:
    """Return (major_ccy, divisor) for a currency code.

    Examples:
        normalize_currency('GBp') -> ('GBP', 100)
        normalize_currency('USD') -> ('USD', 1.0)
        normalize_currency('gbp') -> ('GBP', 1.0)  # lowercase major, not a subunit
    """
    if raw_ccy in SUBUNIT_MAP:
        major, div = SUBUNIT_MAP[raw_ccy]
        return major, float(div)
    return raw_ccy.upper(), 1.0


def normalize_price(price: float, raw_ccy: str) -> tuple[float, str]:
    """Convert a subunit price to major currency units.

    Returns (normalized_price, major_currency_code).

    Examples:
        normalize_price(3340.5, 'GBp') -> (33.405, 'GBP')
        normalize_price(89.84, 'USD')  -> (89.84, 'USD')
    """
    major, div = normalize_currency(raw_ccy)
    return price / div, major
