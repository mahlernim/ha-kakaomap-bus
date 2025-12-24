# HA-KakaoMap-Bus (카카오맵 버스 도착 정보)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant를 위한 카카오맵 실시간 버스 도착 정보 통합구성요소입니다.  
사용자가 원하는 버스 정류장과 노선(버스 번호)을 선택하여 실시간 도착 정보를 센서로 제공합니다.

---

## 🇰🇷 한국어 (Korean)

### 주요 기능
- **실시간 도착 정보**: 카카오맵 API를 통해 정확한 도착 예정 시간(분)을 제공합니다.
- **다중 노선 추적**: 하나의 정류장에서 여러 버스를 동시에 추적할 수 있습니다.
- **2번째 버스 정보**: 바로 오는 버스뿐만 아니라, 그 뒤에 오는 2번째 버스의 도착 시간까지 알려줍니다 (속성값).
- **방해 금지 모드 (Quiet Hours)**: 심야 시간 등 버스가 다니지 않는 시간에는 API 요청을 멈춰 리소스를 절약합니다.
- **효율적인 업데이트**: 한 정류장에 버스가 10대가 있어도, API 호출은 1번만 수행합니다.

### 설치 방법
1. HACS > Integrations > 우측 상단 메뉴 > **Custom repositories** 선택.
2. Repository URL에 `mahlernim/ha-kakaomap-bus` 입력 후 Category를 **Integration**으로 선택.
3. **HA KakaoMap Bus**를 검색하여 설치합니다.
4. Home Assistant를 재시작합니다.

### 설정 방법 (버스 정류장 ID 찾기)
1. [카카오맵(PC)](https://map.kakao.com)에서 원하는 버스 정류장을 획대하여 클릭합니다.
2. 정보창의 **공유(Share)** 아이콘을 클릭합니다.
3. **URL 복사**를 선택하고 팝업창에서 **복사**를 클릭합니다 (단축 URL).
4. 웹 브라우저 주소창에 복사한 주소를 붙여넣고 이동합니다.
5. 주소가 길게 풀리면 URL 중간의 `busStopId=` 값을 확인합니다.
   - 예: `https://map.kakao.com/...&busStopId=BS97660&...`
   - 여기서 `BS97660`이 **정류장 ID**입니다.
4. Home Assistant > 설정 > 기기 및 서비스 > 통합구성요소 추가 > **KakaoMap Bus** 선택.
5. 위에서 찾은 **정류장 ID**를 입력합니다.
6. 추적하고 싶은 버스 노선을 선택(체크)합니다.

### 옵션 변경
- 설치 후에도 `구성(Configure)` 버튼을 통해 다음 항목을 변경할 수 있습니다:
  - 추적할 버스 노선 변경
  - 방해 금지 시간 (기본값: 00:00 ~ 05:00)

---

## 🇺🇸 English

### Features
- **Real-time Arrival**: Provides accurate arrival times (in minutes) via KakaoMap API.
- **Multi-bus Tracking**: Track multiple bus routes from a single stop.
- **Next Bus Info**: Shows the arrival time of the *second* bus as an attribute.
- **Quiet Hours**: Pauses API polling during configured hours (e.g., late night) to save resources.
- **Optimized**: Uses a single API call per stop update, regardless of how many buses are tracked.

### Installation
1. HACS > Integrations > **Custom repositories**.
2. Add `mahlernim/ha-kakaomap-bus` as an **Integration**.
3. Install **HA KakaoMap Bus**.
4. Restart Home Assistant.

### How to find Bus Stop ID
1. Go to [KakaoMap (PC)](https://map.kakao.com) and click on the desired bus stop.
2. Click the **Share** button in the info window.
3. Click **Copy URL** (URL 복사) and then **Copy** (복사) in the popup.
4. Paste the copied short URL into your browser's address bar.
5. Once the URL expands, find `busStopId=` in the address bar.
   - Example: `https://map.kakao.com/...&busStopId=BS97660&...`
   - The value `BS97660` is your **Stop ID**.
4. Home Assistant > Settings > Integrations > Add Integration > **KakaoMap Bus**.
5. Enter the **Stop ID**.
6. Select the routes you want to track.

### Configuration
- You can re-configure the integration options at any time:
  - Select/Deselect buses.
  - Set Quiet Hours (Default: 00:00 - 05:00).
