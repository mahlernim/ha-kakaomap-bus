# 변경 사항 / Changelog

## 1.2.0 — 2026-09-05

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
