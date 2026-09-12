"""v1.3 API response and rate-limit regression coverage."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from custom_components.kakaomap_bus import api


@pytest.mark.parametrize("response_id", [None, 12345, "12345", "BS12x", "BS12345 "])
def test_stop_identity_rejects_missing_or_malformed_response_ids(response_id):
    payload = {"id": response_id}
    with pytest.raises(api.InvalidResponse):
        api.validate_stop_identity(payload, "BS12345")


def test_stop_identity_normalizes_response_id_and_rejects_mismatch():
    assert api.validate_stop_identity({"id": "bs12345"}, "BS12345") == "BS12345"
    with pytest.raises(api.InvalidResponse, match="did not match"):
        api.validate_stop_identity({"id": "BS99999"}, "BS12345")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("0", 1),
        ("00120", 120),
        ("100000000000", 100000000000),
        ("999999999999", 60),
        ("1e3", 60),
        ("120.0", 60),
        ("-120", 60),
        ("inf", 60),
        ("9" * 1000, 60),
    ],
)
def test_retry_after_only_accepts_decimal_integer_delays(header, expected):
    assert api._retry_after(header) == expected


def test_retry_after_accepts_aware_http_date_and_rejects_naive_date():
    future = datetime.now(UTC) + timedelta(seconds=120)
    delay = api._retry_after(format_datetime(future, usegmt=True))
    assert 118 <= delay <= 120
    assert api._retry_after("Wed, 21 Oct 2015 07:28:00") == 60


def test_retry_after_honors_representable_far_future_http_date():
    delay = api._retry_after("Fri, 31 Dec 9999 23:59:59 GMT")
    assert delay > 100_000_000_000


def test_exact_duplicate_route_rows_deduplicate_and_retain_route_id(stop_payload):
    duplicate = deepcopy(stop_payload["lines"][0])
    stop_payload["lines"].append(duplicate)

    route = api.build_bus_dict(stop_payload)["10"]

    assert route["id"] == "B10"
    assert route["ambiguous"] is False
    assert route["arrival"]["arrivalTime"] == 120


def test_conflicting_duplicate_route_names_are_ambiguous_and_not_selectable(stop_payload):
    conflicting = deepcopy(stop_payload["lines"][0])
    conflicting["id"] = "B10-alt"
    conflicting["arrival"]["arrivalTime"] = 30
    stop_payload["lines"].append(conflicting)

    route = api.build_bus_dict(stop_payload)["10"]

    assert route["id"] is None
    assert route["ambiguous"] is True
    assert route["arrival"]["arrivalTime"] is None
    assert route["arrival"]["arrivalTime2"] is None
    assert "10" not in api.build_bus_labels(stop_payload)


def test_duplicate_route_ambiguity_does_not_depend_on_response_order(stop_payload):
    conflicting = deepcopy(stop_payload["lines"][0])
    conflicting["id"] = "B10-alt"
    conflicting["arrival"]["arrivalTime"] = 30
    original = deepcopy(stop_payload)
    original["lines"].append(conflicting)
    reversed_rows = deepcopy(original)
    reversed_rows["lines"] = list(reversed(reversed_rows["lines"]))

    assert api.build_bus_dict(original)["10"] == api.build_bus_dict(reversed_rows)["10"]


def test_duplicate_name_with_missing_id_is_conservatively_ambiguous(stop_payload):
    duplicate = deepcopy(stop_payload["lines"][0])
    duplicate.pop("id")
    stop_payload["lines"].append(duplicate)

    assert api.build_bus_dict(stop_payload)["10"]["ambiguous"] is True
