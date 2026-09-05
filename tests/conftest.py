"""Offline HA fixtures for integration and flow tests."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations):
    """Allow loading this custom integration in the isolated HA instance."""


@pytest.fixture
def stop_payload():
    """Fictional stop and route data; no production captures."""
    return {
        "id": "BS12345",
        "name": "예시역",
        "direction": "시청 방향",
        "lines": [
            {
                "id": "B10",
                "name": "10",
                "realtimeState": "NORMAL",
                "arrival": {
                    "direction": "시청 방향",
                    "arrivalTime": 120,
                    "arrivalTime2": 600,
                    "vehicleType": "0",
                },
            },
            {
                "id": "B2",
                "name": "2",
                "realtimeState": "NOVEHICLE",
                "arrival": {
                    "direction": "공원 방향",
                    "arrivalTime": 0,
                    "arrivalTime2": 0,
                },
            },
        ],
    }
