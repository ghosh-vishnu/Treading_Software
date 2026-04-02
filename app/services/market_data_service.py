from __future__ import annotations

import hashlib
from decimal import Decimal


class MarketDataService:
    def get_latest_price(self, symbol: str) -> Decimal:
        # Deterministic simulated price fallback when the live feed is unavailable.
        normalized = symbol.upper().strip()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        basis = int(digest[:8], 16) % 50000
        price = Decimal("100") + Decimal(basis) / Decimal("100")
        return price.quantize(Decimal("0.01"))


market_data_service = MarketDataService()