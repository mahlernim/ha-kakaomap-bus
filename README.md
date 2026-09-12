# HA KakaoMap Bus

<p align="center"><img src="custom_components/kakaomap_bus/brand/icon@2x.png" alt="HA KakaoMap Bus" width="96" height="96"></p>

카카오맵의 버스 도착 정보를 Home Assistant에서 확인합니다. 정류장과 이용할 버스를 선택하면 도착 예상 시간, 다음 버스 정보, 업데이트 상태를 볼 수 있습니다.

KakaoMap bus arrivals for Home Assistant, with route selection, scheduled pauses, and clear update status.

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
3. 검색된 정류장 이름과 방향을 확인하세요. 이름이 같아도 길 건너편은 다른 방향일 수 있습니다. **카카오맵에서 위치 확인** 링크로 다시 확인할 수 있습니다.
4. 도착 정보를 볼 버스를 하나 이상 선택하세요. 필요하면 `출근길 정류장`처럼 별칭을 입력하세요.
5. 선택한 버스와 업데이트 시간을 확인하고 추가하세요.

기본 설정은 **90초마다 업데이트**, **매일 00:00~05:00 일시 중지**입니다. Home Assistant에 설정된 시간대를 사용합니다.

링크를 인식하지 못하면 브라우저에서 링크를 연 뒤 펼쳐진 주소를 복사하거나, 주소의 `busStopId=BS...` 값을 입력하세요. 장소나 길찾기 공유 링크는 버스 정류장 링크와 다릅니다.

### 도착 정보 확인

선택한 버스마다 **도착 시간**과 **도착 정보 상태** 엔티티가 생깁니다. 대시보드에 두 엔티티를 함께 추가하면 정보가 없는 이유도 확인할 수 있습니다.

| 상태 | 의미 |
|---|---|
| 도착 정보 확인됨 | 해당 버스의 도착 예상 시간을 받았습니다. |
| 도착 정보 없음 | 조회는 성공했지만 표시할 도착 시간이 없습니다. 버스가 반드시 운행하지 않는다는 뜻은 아닙니다. |
| 업데이트 일시 중지 | 설정한 시간 동안 새 정보를 가져오지 않습니다. 종료 시간부터 다시 조회합니다. |
| 연결 끊김 | 카카오맵에서 새 정보를 받지 못했습니다. 자동으로 다시 시도합니다. |

도착 시간은 분 단위입니다. `next_bus_min` 속성은 다음 버스의 예상 시간입니다. 상태 엔티티의 속성에서 마지막으로 정보를 받은 시각(`last_success`)과 일시 중지 종료 시각(`paused_until`)을 확인할 수 있습니다.

일시 중지 중에는 도착 시간이 비어 있고, 연결이 끊기면 사용할 수 없음으로 표시됩니다. 두 경우 모두 이전 도착 시간을 계속 표시하지 않으며, 다음 버스 정보도 비웁니다. 예상 시간이 30초보다 짧으면 반올림 결과가 0분으로 표시될 수 있습니다.

### 버스와 업데이트 설정 변경

추가한 통합 구성요소의 옵션을 열어 변경하세요.

- **확인할 버스**: 이용할 버스를 선택합니다. 모두 해제하면 해당 정류장의 도착 정보를 표시하지 않습니다.
- **정류장 별칭**: 같은 이름의 정류장을 구분할 이름입니다. 비워 두면 원래 이름을 사용합니다. Home Assistant에서 직접 지정한 기기 이름은 유지됩니다.
- **업데이트 일시 중지**: 스위치를 켜고 시작·종료 시간을 선택합니다. 자정을 넘는 시간도 설정할 수 있습니다. 하루 종일 조회하려면 스위치를 끄세요.
- **고급 설정 → 업데이트 간격**: 30~600초 사이의 정수로 설정합니다. 기본값은 90초입니다. 간격을 줄여도 카카오맵 원본 정보가 더 자주 바뀌는 것은 아닙니다.

연결이 끊겨도 기존 버스 선택과 시간 설정을 변경할 수 있습니다. 새 버스를 추가하려면 연결이 복구된 뒤 옵션을 다시 여세요.

### 기존 사용자

업데이트 후 Home Assistant를 재시작하세요. 기존 정류장과 선택한 버스, 유효한 일시 중지 시간, 엔티티 ID를 유지합니다. 버스별 상태 엔티티가 추가되며, 정류장을 다시 등록할 필요는 없습니다.

이전에 시작·종료 시간을 같게 설정했다면 업데이트가 하루 종일 멈추던 동작이 바뀝니다. 같은 시간은 일시 중지하지 않는 것으로 처리합니다. 새 옵션 화면에서는 하루 종일 조회하려면 스위치를 끄도록 안내합니다.

기존 자동화에서 `unknown`과 `unavailable`을 처리하고 있는지 확인하세요. 정보가 없을 때 도착 시간을 0분으로 바꾸어 안내하지 않는 것이 좋습니다.

### 문제 해결과 제한 사항

- **정류장을 찾지 못함**: 버스 정류장의 공유 링크 또는 `BS`로 시작하는 ID인지 확인하세요.
- **연결 실패**: 입력값은 유지됩니다. 인터넷 연결을 확인한 뒤 다시 시도하세요.
- **도착 정보 없음**: 카카오맵에서도 같은 정류장과 방향의 정보를 확인하세요.
- **업데이트 일시 중지**: 옵션의 스위치, 시작·종료 시간, Home Assistant 시간대를 확인하세요.
- **일시적인 요청 제한**: 카카오맵이 안내한 대기 시간이 있으면 기다린 뒤 다시 조회합니다.

이 프로젝트는 카카오의 공식 통합 구성요소가 아닙니다. 웹사이트의 정보 제공 방식이 바뀌면 동작에 영향을 받을 수 있습니다. 도착 시간은 예상값이며 지연이나 누락이 발생할 수 있습니다. 같은 정류장에서 서로 다른 노선이 동일한 이름으로 제공되는 경우의 구분은 아직 지원하지 않습니다.

조회할 정류장 ID와 공유 링크를 처리하기 위한 요청이 카카오맵 관련 서버로 전송됩니다. 별도의 계정 정보나 인증키는 저장하지 않습니다.

문제나 제안은 [GitHub Issues](https://github.com/mahlernim/ha-kakaomap-bus/issues)에 한국어 또는 영어로 남겨 주세요. Home Assistant 버전과 재현 방법을 알려 주시고, 전체 설정 파일이나 인증 정보는 올리지 마세요.

[MIT 라이선스](LICENSE)로 배포합니다.

## English

### Requirements and setup

Requires Home Assistant 2025.12 or later, internet access, and a Korean bus stop available in KakaoMap. No Kakao account or API key is needed.

1. Add `mahlernim/ha-kakaomap-bus` to HACS as a custom **Integration** repository.
2. Download **HA KakaoMap Bus** and restart Home Assistant.
3. Add the integration under **Settings → Devices & services**.
4. Paste a KakaoMap stop link (`map.kakao.com` or `kko.to`) or an ID beginning with `BS`. Check the stop and direction, choose routes, optionally set a nickname, and confirm.

If a short link cannot be resolved, open it in a browser and paste the expanded URL or its `busStopId` value. Place and directions links do not identify bus stops. This is a custom-repository installation, not a claim of HACS default inclusion.

### Arrivals and options

Updates default to every **90 seconds**, paused daily from **00:00 to 05:00** in Home Assistant's time zone.

Each route has an arrival sensor in minutes and a localized status sensor. `next_bus_min` contains the second arrival. Status distinguishes live arrivals, no arrival information, scheduled pauses, and connection loss, with `last_success` and `paused_until` attributes.

Paused arrivals are unknown; failed updates make arrivals unavailable. Expired first- and second-bus estimates are suppressed. An unavailable attribute may be absent rather than null. Positive arrivals under 30 seconds can round to 0 minutes.

Options include route selection, a stop nickname, a pause switch with time pickers, and an advanced interval of 30–600 seconds. Turn pausing off for all-day updates. Times can cross midnight. Existing selections and times remain editable offline; reopen options after recovery to refresh the route list. Manually renamed HA devices keep their names.

### Updating and support

Restart Home Assistant after updating. Existing settings and entity IDs are retained; new status entities are added. Re-adding stops is unnecessary. Legacy equal pause times now disable pausing instead of stopping updates all day.

Handle unknown and unavailable values in automations without converting them to zero-minute arrivals. Check direction, pause settings, the HA time zone, and connectivity when information is missing.

This unofficial integration uses KakaoMap's website endpoint, which may change. Arrivals are estimates and can be delayed or absent. Distinct same-name routes at one stop are not yet distinguished. Requests send the selected stop ID and supported share links to KakaoMap-related servers; no account credentials are stored.

Report issues in Korean or English through [GitHub Issues](https://github.com/mahlernim/ha-kakaomap-bus/issues). See [CONTRIBUTING](CONTRIBUTING.md) for development and [CHANGELOG](CHANGELOG.md) for changes.

Released under the [MIT license](LICENSE).
