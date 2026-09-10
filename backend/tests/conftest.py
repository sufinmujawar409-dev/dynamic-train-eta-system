import pytest


class MockOpenWeatherResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "dt": 1789050000,
            "main": {"temp": 27.4, "feels_like": 28.1, "humidity": 64},
            "wind": {"speed": 3.2},
            "visibility": 10000,
            "weather": [{"description": "clear sky"}],
            "rain": {"1h": 0.4},
        }


@pytest.fixture(autouse=True)
def mock_external_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: MockOpenWeatherResponse())
