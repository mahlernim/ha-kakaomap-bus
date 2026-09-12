# HA KakaoMap Bus

<p align="center"><img src="custom_components/kakaomap_bus/brand/icon@2x.png" alt="HA KakaoMap Bus" width="96" height="96"></p>

카카오맵의 버스 도착 예상 시간을 Home Assistant에서 확인하세요. 정류장과 버스를 선택하면 도착 시간, 다음 버스, 정보 상태를 함께 볼 수 있습니다.

View KakaoMap bus arrival estimates in Home Assistant with per-route arrival and status sensors.

[한국어](#한국어) · [English](#english) · [설치하기](#준비-사항과-설치) · [변경 사항](CHANGELOG.md)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![Release](https://img.shields.io/github/v/release/mahlernim/ha-kakaomap-bus)](https://github.com/mahlernim/ha-kakaomap-bus/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 한국어

### 준비 사항과 설치

Home Assistant 2025.12 이상과 인터넷 연결이 필요합니다. 카카오맵에서 조회할 수 있는 국내 버스 정류장을 사용하며, 카카오 계정이나 API 키는 필요하지 않습니다.

1. HACS의 사용자 지정 저장소에 `mahlernim/ha-kakaomap-bus`를 **Integration** 유형으로 추가하세요.
2. **HA KakaoMap Bus**를 다운로드하고 Home Assistant를 재시작하세요.
3. **설정 → 기기 및 서비스 → 통합 구성요소 추가**에서 **HA KakaoMap Bus**를 선택하세요.

이 안내는 HACS 사용자 지정 저장소 설치 방법입니다. 기본 목록 등록과는 별개입니다.

### 정류장 추가

1. 카카오맵에서 이용할 **버스 정류장**을 선택하고 공유 링크를 복사하세요.
2. **정류장 링크 또는 ID**에 링크를 붙여넣으세요. `map.kakao.com` 링크, `kko.to` 공유 링크, 또는 `BS`로 시작하는 정류장 ID를 사용할 수 있습니다.
3. 검색된 정류장 이름과 방향을 확인하세요. 이름이 같아도 길 건너편은 다른 정류장일 수 있습니다. **카카오맵에서 위치 확인** 링크로 다시 확인할 수 있습니다.
4. 다음 화면에서 검색 가능한 목록으로 버스를 하나 이상 선택하세요. 별칭, 업데이트 방식, 일시 중지 시간도 확인할 수 있고 선택 설정은 접혀 있습니다.

기본값은 **적응형 업데이트**와 **매일 00:00~05:00 일시 중지**입니다. Home Assistant에 설정된 시간대를 사용합니다. 적응형 업데이트는 선택한 버스 중 유효한 첫 도착 예상 시간이 3분 이내이면 30초마다, 그 외에는 120초마다 새 정보를 요청합니다.

링크를 인식하지 못하면 브라우저에서 링크를 연 뒤 펼쳐진 주소를 복사하거나, 주소의 `busStopId=BS...` 값을 입력하세요. 장소나 길찾기 공유 링크는 버스 정류장 링크와 다릅니다.

### 도착 정보와 상태

선택한 버스마다 **도착 시간**과 **도착 정보 상태** 엔티티가 생깁니다. 대시보드에 두 엔티티를 함께 추가하면 정보가 없는 이유도 확인할 수 있습니다.

| 상태 | 의미 |
|---|---|
| 도착 정보 확인됨 | 해당 버스의 현재 도착 예상 시간을 받았습니다. |
| 도착 정보 없음 | 조회는 성공했지만 표시할 도착 시간이 없습니다. 버스가 반드시 운행하지 않는다는 뜻은 아닙니다. |
| 업데이트 일시 중지 | 설정한 시간 동안 새 정보를 요청하지 않습니다. |
| 요청 제한됨 | 카카오맵이 요청 대기 시간을 안내했습니다. `retry_at`은 다음 요청을 시도할 수 있는 가장 이른 시각이며 서비스 복구를 보장하는 시각은 아닙니다. |
| 잘못된 정류장 응답 | 응답의 정류장 ID를 확인할 수 없거나 설정한 정류장과 일치하지 않았습니다. 다시 조회합니다. |
| 노선 이름 중복 | 같은 이름의 노선을 구분할 수 없어 해당 노선의 도착 정보를 표시하지 않습니다. |
| 도착 예상 시간 만료 | 마지막으로 받은 첫 도착 예상 시간이 지났습니다. 새 정보가 올 때까지 첫 버스와 다음 버스 정보를 모두 비웁니다. |
| 연결 끊김 | 카카오맵에서 새 정보를 받지 못했습니다. 자동으로 다시 시도합니다. |

성공적으로 받은 정보 사이에는 기기에서 도착 예상 시간을 줄여 표시합니다. 첫 도착 예상 시간이 만료되면 두 도착 예상 시간을 모두 비우며, 두 번째 버스를 첫 번째 버스로 자동 승격하지 않습니다. 이 로컬 갱신은 새 요청이나 `last_success` 변경으로 처리하지 않습니다. 도착 시간은 분 단위이며, 30초보다 짧은 양수 예상 시간은 반올림 결과 0분으로 표시될 수 있습니다. `next_bus_min` 속성은 다음 버스의 예상 시간입니다.

### 버스와 업데이트 설정 변경

추가한 통합 구성요소의 옵션을 열어 변경하세요.

- **확인할 버스**에서 버스를 검색하고 선택하세요. 선택을 해제한 엔티티와 맞춤 설정은 보존되므로 나중에 다시 선택할 수 있습니다. 모두 해제하면 해당 정류장의 도착 정보를 표시하지 않습니다.
- **정류장 별칭**은 같은 이름의 정류장을 구분할 때 사용합니다. 비워 두면 원래 이름을 사용합니다. Home Assistant에서 직접 지정한 기기 이름은 유지됩니다.
- **업데이트 방식**은 기본 적응형 또는 고정 간격입니다. 고정 간격은 30~600초 사이의 정수로 설정하며 기존 설정의 90초 값도 보존됩니다.
- **업데이트 일시 중지**는 스위치를 켜고 시작·종료 시간을 선택하세요. 자정을 넘는 시간도 설정할 수 있습니다. 하루 종일 조회하려면 스위치를 끄세요.

자동 업데이트를 끄더라도 마지막으로 받은 도착 예상 시간의 로컬 카운트다운과 만료 처리는 계속됩니다. 자동 요청은 만들지 않습니다. 일시 중지 중에도 새 요청은 하지 않으며, 종료 시 요청 제한 대기 시간이 남아 있으면 그 시각 전에는 다시 요청하지 않습니다.

옵션은 연결이 끊겨도 변경할 수 있습니다. 같은 정류장의 이름이나 방향 등 메타데이터는 재구성으로 새로고침할 수 있으며 정류장 ID와 엔티티 ID는 바뀌지 않습니다. 다른 실제 정류장으로 바꾸려면 별도 통합 구성요소를 추가하세요.

### 기존 사용자

v1.3.0으로 업데이트한 뒤 Home Assistant를 재시작하세요. 기존 항목은 한 번 적응형 업데이트 방식으로 전환되고 이전 고정 간격 값은 보존됩니다. 이후 고정 간격을 선택하면 다음 업데이트와 다시 시작 후에도 그 선택을 유지합니다. 기존 정류장, 버스 선택, 유효한 일시 중지 시간, 엔티티 ID는 유지됩니다.

자동화에서 `unknown`, `unavailable`과 새 상태를 처리하세요. 특히 `expired`는 도착했다는 뜻이 아니며 `rate_limited`의 `retry_at`은 서비스가 정상화된다는 약속이 아닙니다. 정보가 없을 때 도착 시간을 0분으로 바꾸어 안내하지 않는 것이 좋습니다.

### 문제 해결과 제한 사항

- **정류장을 찾지 못함**: 버스 정류장의 공유 링크 또는 `BS`로 시작하는 ID인지 확인하세요.
- **잘못된 정류장 응답**: 잠시 뒤 다시 조회합니다. 반복되면 카카오맵에서 정류장 링크와 방향을 확인하세요.
- **노선 이름 중복**: 같은 이름의 노선을 현재 구분할 수 없습니다. 해당 노선은 표시하지 않으며 다른 노선은 계속 사용할 수 있습니다.
- **요청 제한됨**: `retry_at` 이후에 다시 시도하세요. 수동 새로고침도 그 시각 전에는 요청하지 않습니다.
- **도착 정보 없음 또는 만료**: 카카오맵에서도 같은 정류장과 방향의 정보를 확인하세요. 예상 시간은 새 응답을 받을 때만 다시 표시됩니다.

이 프로젝트는 카카오의 공식 통합 구성요소가 아닙니다. 웹사이트의 정보 제공 방식이 바뀌면 동작에 영향을 받을 수 있습니다. 도착 시간은 예상값이며 지연이나 누락이 발생할 수 있습니다. 적응형 요청은 표시 정보에 맞춰 요청 주기를 조절하지만 카카오맵 원본 정보가 더 빨리 갱신되거나 더 정확해짐을 의미하지 않습니다.

조회할 정류장 ID와 공유 링크를 처리하기 위한 요청이 카카오맵 관련 서버로 전송됩니다. 별도의 계정 정보나 인증키는 저장하지 않습니다.

문제나 제안은 [GitHub Issues](https://github.com/mahlernim/ha-kakaomap-bus/issues)에 한국어 또는 영어로 남겨 주세요. Home Assistant 버전과 재현 방법을 알려 주시고 전체 설정 파일이나 인증 정보는 올리지 마세요.

[MIT 라이선스](LICENSE)로 배포합니다.

## English

### Requirements and setup

Requires Home Assistant 2025.12 or later, internet access, and a Korean bus stop available in KakaoMap. No Kakao account or API key is needed.

1. Add `mahlernim/ha-kakaomap-bus` to HACS as a custom **Integration** repository.
2. Download **HA KakaoMap Bus** and restart Home Assistant.
3. Add the integration under **Settings → Devices & services**.
4. Paste a KakaoMap stop link (`map.kakao.com` or `kko.to`) or an ID beginning with `BS`. Check the stop and direction.
5. On the next screen, search for and select routes. You can also set a nickname, polling mode, and quiet hours. Optional settings are collapsed.

This is a custom-repository installation, not a claim of HACS default inclusion. If a short link cannot be resolved, open it in a browser and paste the expanded URL or its `busStopId` value. Place and directions links do not identify bus stops.

### Arrivals, polling, and status

Adaptive polling is the default for new and existing entries. The integration requests new data every **30 seconds** while any enabled selected route has a valid first arrival within three minutes. It requests data every **120 seconds** otherwise. Quiet hours default to **00:00 to 05:00** in Home Assistant's time zone.

Between successful requests, the integration counts an estimate down locally. When the first estimate expires, it clears both arrival values and reports `expired`. It never promotes the second bus to become the first. Local countdown updates do not make a request or change `last_success`. `next_bus_min` contains the second arrival estimate, and positive estimates under 30 seconds can round to 0 minutes.

Each selected route has an arrival sensor and a localized status sensor. The status can be `live`, `no_arrival`, `paused`, `connection_lost`, `expired`, `rate_limited`, `invalid_stop`, or `ambiguous_route`.

- `rate_limited` includes `retry_at`, the earliest permitted request time. It is not a promise that the upstream service will be available then.
- `invalid_stop` means the response omitted a stop ID or returned a different stop ID. The integration retries it as an invalid response.
- `ambiguous_route` suppresses an affected same-name route while routes with unambiguous names continue to work.

### Changing routes and options

Open the integration's options to change routes, the stop nickname, polling mode, and quiet hours. Route selection is searchable. Deselected route entities and their customizations are retained so they can be selected again. Selecting no routes leaves the stop configured but publishes no arrivals.

Adaptive polling is the default. Fixed polling remains available from 30 to 600 seconds. Existing 90-second settings are retained as the saved fixed interval, so you can switch back to them.

When automatic polling is disabled, local countdown and expiry still run but no automatic requests are made. Quiet hours also suppress requests. When polling resumes, an outstanding rate-limit deadline is honored before another request, including a manual refresh.

You can edit options while the route list is unavailable. Reconfigure the same stop to refresh its metadata without changing its stop ID or entity IDs. Add a separate integration entry for a different physical stop. Manually renamed Home Assistant devices retain their names.

### Updating and support

After updating to v1.3.0, restart Home Assistant. Existing entries migrate once to adaptive polling and retain their former fixed interval. Choosing fixed polling after the migration persists across later restarts and upgrades. Existing stop configuration, valid quiet hours, selected routes, and entity IDs are retained.

Update automations to handle `unknown`, `unavailable`, and the additional status values. `expired` does not mean a bus has arrived. Do not convert missing information into a zero-minute arrival.

This unofficial integration uses a KakaoMap website endpoint, which may change. Arrivals are estimates and can be delayed or absent. Adaptive polling changes only this integration's request schedule. It does not establish that KakaoMap data becomes fresher or more accurate.

Requests send the selected stop ID and supported share links to KakaoMap-related servers. No account credentials are stored. Report issues in Korean or English through [GitHub Issues](https://github.com/mahlernim/ha-kakaomap-bus/issues). See [CONTRIBUTING](CONTRIBUTING.md) for development and [CHANGELOG](CHANGELOG.md) for changes.

Released under the [MIT license](LICENSE).
