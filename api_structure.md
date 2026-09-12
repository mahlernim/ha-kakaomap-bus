# KakaoMap Bus API Structure

This document describes the observed JSON shape used by the integration. It is not a published Kakao developer API contract.

## Endpoint

`https://map.kakao.com/bus/stop.json?busstopid={STOP_ID}`

## Root object

| Key | Type | Description |
| --- | --- | --- |
| `id` | String | Bus stop identifier. The integration requires it to match the configured stop ID. A missing or mismatched value is an invalid response. |
| `name` | String | Stop name, for example `수정역`. |
| `hname1` | String | City name, for example `부산`. |
| `direction` | String | Direction associated with the stop. |
| `realTime` | Boolean | Whether real-time data is available. |
| `lines` | Array | Routes served at the stop. |

## Line object

Each item in `lines` represents a bus route.

| Key | Type | Description |
| --- | --- | --- |
| `id` | String | Internal KakaoMap route identifier. The current integration preserves identity by configured stop ID and route name. It does not migrate existing entities to route-ID identity. |
| `name` | String | Route number or name, for example `126`. Duplicate route names are ambiguous and are not used for a route selection or arrival sensor. |
| `busLineType` | String | Route type, for example `GENERAL` or `MAUL`. |
| `arrival` | Object | Arrival details for the first and second bus. |

## Arrival object

| Key | Type | Description |
| --- | --- | --- |
| `arrivalTime` | Number | Seconds until the first bus arrives. A positive finite number is a usable estimate. |
| `busStopCount` | Integer | Stops remaining until the first bus arrives. |
| `arrivalTime2` | Number | Seconds until the second bus arrives. |
| `busStopCount2` | Integer | Stops remaining until the second bus arrives. |
| `direction` | String | Route direction, for example `수정역 방향`. |
| `nextBusStopName` | String | Name of the next stop. |
| `vehicleType` | String | Vehicle type, for example `0` for general. |
| `collectStatus` | String | Upstream collection status, for example `NORMAL`. |

## Example response

```json
{
  "id": "BS97660",
  "name": "수정역",
  "lines": [
    {
      "id": "B9082",
      "name": "126",
      "arrival": {
        "arrivalTime": 345,
        "busStopCount": 3,
        "arrivalTime2": 950,
        "busStopCount2": 8
      }
    }
  ]
}
```

## Integration behavior

- **Polling**. Adaptive polling is the default for new and migrated entries. The integration requests every 30 seconds when any enabled selected route has a valid first arrival within three minutes. It requests every 120 seconds otherwise. Fixed polling remains selectable from 30 to 600 seconds, with a prior saved fixed interval retained during the one-time adaptive migration.
- **Local countdown**. After a successful response, first and second estimates count down locally. When the first estimate reaches expiry, the integration clears both estimates and reports `expired`. It never automatically promotes the second estimate. Local updates do not change `last_success` or schedule a network request.
- **Polling controls**. Quiet hours and disabled automatic polling prevent automatic requests. Local countdown continues while automatic polling is disabled. Requests do not overlap or catch up in bursts. A rate-limit deadline is honored before scheduled or manual requests.
- **Rate limits and failures**. HTTP `Retry-After` integer delays and HTTP dates are accepted when representable. Malformed or unrepresentable values use a 60-second fallback. `retry_at` is the earliest eligible request time, not a service-recovery guarantee. Bounded immediate retries apply to retryable API failures. Exhausted non-rate-limit failures use scheduled backoff from 120 seconds, doubling to a 15-minute maximum and resetting after success.
- **Validation**. Missing, boolean, string, negative, or nonfinite arrival values are not usable estimates. Malformed routes are isolated where possible. A missing or mismatched root `id` produces a retryable `invalid_stop` response, preserves `last_success`, and suppresses arrival values.
- **Route ambiguity**. Duplicate route names are detected before route choices are built. Ambiguous names are excluded during setup and report `ambiguous_route` for existing affected routes. Other routes continue independently.
- **Status**. Selected routes report `live`, `no_arrival`, `paused`, `connection_lost`, `expired`, `rate_limited`, `invalid_stop`, or `ambiguous_route`. Status precedence is scheduled pause, current request failure, route ambiguity, expired estimate, then live or no arrival information.
- **Identity and metadata**. Arrival unique IDs remain `kakaobus_{stop_id}_{bus_name}`. Status IDs remain `kakaobus_status_{stop_id}_{bus_name}`. Reconfiguring the same stop can refresh its metadata without changing identity. A different physical stop requires a separate entry.
- **Scope**. The endpoint and its fields can change without notice. Adaptive polling changes only this integration's request cadence and does not establish a fresher or more accurate upstream KakaoMap feed.
