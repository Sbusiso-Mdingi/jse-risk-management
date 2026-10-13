"""Portfolio construction and risk measurement for JSE equities, shared by research and service."""

# Brokerage and spread per side, plus 0.25% securities transfer tax on purchases.
BUY_COST, SELL_COST = 0.0010 + 0.0025, 0.0010
FREEZE = "2026-09-30"
