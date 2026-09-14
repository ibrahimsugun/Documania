import pytest


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """`time.sleep`'i beklemeden kaydeder — yeniden deneme testleri hızlı kalır (03.5.1)."""
    calls: list[float] = []
    monkeypatch.setattr("app.ai.provider.time.sleep", calls.append)
    return calls
