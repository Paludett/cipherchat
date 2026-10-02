import pytest

from app.ratelimit import limiter


@pytest.fixture(autouse=True)
def zerar_rate_limit():
    limiter.reset()
