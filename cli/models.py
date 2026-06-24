from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    # Wire value stays "social" for saved-config and string-keyed-caller
    # back-compat; the user-facing label is "Sentiment Analyst".
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
    POLICY = "policy"
    HOT_MONEY = "hot_money"
    LOCKUP = "lockup"


class AssetType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
