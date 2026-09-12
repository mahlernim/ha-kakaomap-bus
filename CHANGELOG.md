# 변경 사항 / Changelog

## 1.3.0

### 한국어

도착 예상 시간의 만료 처리와 업데이트 방식을 개선했습니다.

- 성공적으로 받은 도착 예상 시간은 다음 요청 전까지 기기에서 카운트다운합니다. 첫 도착 예상 시간이 만료되면 첫 버스와 다음 버스 정보를 모두 비우고 `expired` 상태를 표시합니다. 두 번째 버스를 첫 번째 버스로 자동 승격하지 않습니다.
- 새 항목과 기존 항목의 기본 업데이트 방식을 적응형으로 변경했습니다. 선택한 버스 중 유효한 첫 도착 예상 시간이 3분 이내이면 30초마다, 그 외에는 120초마다 요청합니다. 고정 30~600초 설정은 계속 사용할 수 있으며 기존 90초 값도 보존됩니다.
- 요청 제한, 잘못된 정류장 응답, 같은 이름의 노선 구분 불가를 각각 `rate_limited`, `invalid_stop`, `ambiguous_route`로 표시합니다. `retry_at`은 요청할 수 있는 가장 이른 시각입니다.
- 같은 정류장을 재구성하여 이름과 방향 메타데이터를 새로고침할 수 있습니다. 정류장 ID와 엔티티 ID는 바뀌지 않습니다. 다른 실제 정류장은 별도 항목으로 추가합니다.
- 설정을 두 화면으로 나누고 두 번째 화면에 검색 가능한 버스 선택, 별칭, 업데이트 방식, 일시 중지 시간과 접힌 선택 설정을 배치했습니다. 선택 해제한 버스의 엔티티와 맞춤 설정은 다시 선택할 수 있도록 유지합니다.

업데이트 후 Home Assistant를 재시작하세요. 기존 항목은 한 번 적응형 방식으로 전환하며 이전 고정 간격 값은 보존합니다. 이후 고정 방식을 선택하면 그 선택을 유지합니다. 기본 일시 중지 시간은 00:00~05:00입니다.

적응형 업데이트는 이 통합 구성요소의 요청 주기만 조절합니다. 카카오맵 원본 정보가 더 빨리 갱신되거나 더 정확해짐을 뜻하지 않습니다.

### English

This release improves estimate expiry handling and polling behavior.

- Arrival estimates count down locally after a successful request. When the first estimate expires, both first and second arrival values are cleared and the route reports `expired`. The second bus is never promoted automatically.
- Adaptive polling is now the default for new and existing entries. It requests data every 30 seconds when an enabled selected route has a valid first arrival within three minutes, otherwise every 120 seconds. Fixed polling from 30 to 600 seconds remains available, and an existing 90-second value is retained.
- `rate_limited`, `invalid_stop`, and `ambiguous_route` distinguish request limits, invalid stop responses, and same-name route ambiguity. `retry_at` is the earliest permitted request time.
- Reconfigure a stop to refresh its name and direction metadata without changing its stop or entity IDs. Add a separate entry for another physical stop.
- Setup now uses two screens. The second screen has a searchable route picker, nickname, polling mode, quiet hours, and collapsed optional settings. Deselected route entities and customizations remain available for reselection.

Restart Home Assistant after updating. Existing entries migrate once to adaptive polling and retain their previous fixed interval. A later fixed-mode choice persists. The default quiet hours remain 00:00 to 05:00.

Adaptive polling changes this integration's request schedule only. It does not establish that KakaoMap source data updates more quickly or becomes more accurate.

## 1.2.0 - 2026-09-05

### 한국어

정류장을 더 쉽게 추가하고, 도착 정보가 보이지 않는 이유를 확인할 수 있도록 개선했습니다.

- 카카오맵 공유 링크를 붙여넣어 정류장을 찾을 수 있습니다. 정류장 이름과 방향을 확인하고, 필요한 버스만 선택한 뒤 추가합니다.
- 정류장에 별칭을 붙일 수 있습니다. 버스 목록은 번호순으로 정렬하고, 방향도 함께 표시합니다.
- 버스마다 도착 정보 상태를 추가했습니다. `도착 정보 없음`, `업데이트 일시 중지`, `연결 끊김`을 구분하고, 마지막으로 정보를 받은 시각을 확인할 수 있습니다.
- 업데이트 일시 중지를 스위치와 시간 선택기로 설정합니다. 일시 중지 중이거나 연결이 끊기면 이전 도착 시간을 계속 표시하지 않습니다.
- 연결 실패를 잘못된 정류장 ID로 안내하던 문제와, 일부 도착 정보가 비어 있을 때 오류가 나던 문제를 수정했습니다.

업데이트 후 Home Assistant를 재시작하세요. 기존 정류장 설정과 엔티티 ID는 유지되며, 정류장을 다시 추가할 필요가 없습니다. 기존 도착 시간 엔티티와 별도로 버스별 상태 엔티티가 추가됩니다. Home Assistant 2025.12 이상이 필요합니다.

기존 일시 중지의 시작·종료 시간이 같으면 하루 종일 업데이트하도록 처리합니다. 자동화에서는 정보가 없는 상태를 0분 도착으로 바꾸지 않도록 확인하세요.

카카오맵이 제공하는 정보의 지연이나 누락은 발생할 수 있습니다. 도착 시간은 예상값입니다.

### English

- Add stops using a KakaoMap share link or ID. Check the stop and direction, choose routes, and confirm setup.
- Add a stop nickname and use naturally sorted route labels with directions.
- Each route gains a localized status entity for live arrivals, missing information, scheduled pauses, and connection loss, with last-success metadata.
- Configure scheduled pauses with a switch and time pickers. Clear expired estimates during pauses and outages.
- Distinguish connection failures from invalid stop IDs and handle missing or malformed arrival fields safely.

Restart Home Assistant after updating. Existing settings and entity IDs are retained; re-adding stops is unnecessary. Route status entities are added alongside existing arrival sensors. Requires Home Assistant 2025.12 or later.

Legacy equal pause times now allow all-day updates. Check that automations handle unknown or unavailable arrivals without converting them to zero minutes.

Arrivals remain estimates and may be delayed or missing at the source.
