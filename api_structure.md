# KakaoMap Bus API Structure

This document outlines the JSON structure returned by the KakaoMap Bus Arrival API.

## Endpoint
`https://map.kakao.com/bus/stop.json?busstopid={STOP_ID}`

## Root Object
| Key | Type | Description |
| :--- | :--- | :--- |
| `id` | String | Unique identifier for the bus stop. |
| `name` | String | Human-readable name of the bus stop (e.g., "수정역"). |
| `hname1` | String | City name (e.g., "부산"). |
| `direction` | String | The direction the buses are heading. |
| `realTime` | Boolean | Whether real-time data is available. |
| `lines` | Array | List of bus routes (lines) served at this stop. |

## Line (Bus Route) Object
Each item in the `lines` array contains:
| Key | Type | Description |
| :--- | :--- | :--- |
| `id` | String | Internal ID for the bus route (e.g., "B9082"). |
| `name` | String | Bus route number/name (e.g., "126"). |
| `busLineType` | String | Type of bus (e.g., "GENERAL", "MAUL"). |
| `arrival` | Object | Detailed arrival information for the next bus. |

## Arrival Object
| Key | Type | Description |
| :--- | :--- | :--- |
| `arrivalTime` | Number | Seconds until the next bus arrives. Zero or missing values do not provide a usable estimate. |
| `busStopCount` | Integer | Number of stops remaining until arrival. |
| `arrivalTime2` | Integer | Seconds until the second following bus arrives. |
| `busStopCount2` | Integer | Number of stops remaining for the second bus. |
| `direction` | String | Descriptive direction (e.g., "수정역 방향"). |
| `nextBusStopName` | String | The name of the next stop. |
| `vehicleType` | String | Type of vehicle (e.g., "0" for general). |
| `collectStatus` | String | Status of data collection (e.g., "NORMAL"). |

## Example Response Snippet
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

## Integration Logic
- **Refresh interval**: 90 seconds by default; configurable from 30 to 600 seconds. Scheduled pauses suppress requests and clear arrival values.
- **Sensor Mapping**: Each `line` in the `lines` array should map to a sensor entity in Home Assistant.
- **State**: Valid positive seconds divided by 60, rounded to minutes. Missing or invalid values produce unknown; request failures produce unavailable. Second-arrival values are cleared when the first arrival is not current.
- **Validation**: Null objects, booleans, strings, negative values, and nonfinite values are not arrival estimates. Malformed routes are isolated when possible.
- **Status**: Each selected route also has an enum sensor for `live`, `no_arrival`, `paused`, and `connection_lost`, localized by Home Assistant.
- **Identity**: Existing arrival unique IDs remain `kakaobus_{stop_id}_{bus_name}`. Status IDs use `kakaobus_status_{stop_id}_{bus_name}`. Same-name route collisions remain unsupported.
- **Scope**: This describes an unofficial website endpoint, not a published Kakao developer API contract. Fields can change.
