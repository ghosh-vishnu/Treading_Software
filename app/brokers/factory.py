from app.brokers.base import BrokerClient
from app.brokers.delta_exchange import DeltaExchangeBroker, MockBroker


def get_broker_client(
    broker_name: str,
    api_key: str | None = None,
    api_secret: str | None = None,
    base_url: str | None = None,
) -> BrokerClient:
    broker = broker_name.lower()
    if broker == "delta":
        return DeltaExchangeBroker(api_key=api_key, api_secret=api_secret, base_url=base_url)
    if broker in {"zerodha", "binance"}:
        # Fallback implementation keeps the interface stable; swap in the provider-specific client once
        # credentials and API access are configured.
        return MockBroker()
    return MockBroker()
