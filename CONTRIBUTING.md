# Contributing

Issues and pull requests are welcome in Korean or English. Include the Home
Assistant version, the expected behavior, and a short reproduction. Do not post
credentials or full configuration files.

Use Linux or WSL with Python 3.14 for the current test environment:

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements_test.txt homeassistant==2026.9.0 pytest-homeassistant-custom-component==0.13.363
ruff check .
ruff format --check .
pytest --cov=custom_components.kakaomap_bus --cov-report=term-missing
```

CI also tests Home Assistant 2025.12.0 on Python 3.13.2. Fixtures use fictional
stops and mocked requests. Tests must not contact production Home Assistant or
KakaoMap. Cover config-flow recovery, entity-ID compatibility, pause boundaries,
and missing or invalid arrival data when changing those behaviors.

Keep Korean user guidance clear and concise, with equivalent English essentials.
PR descriptions should explain the resulting behavior and relevant validation in
concise English. Publishing and production installation are separate operations.

## Brand assets

The integration icons are rendered from the existing `images/icon.svg` project symbol on a `#252A32` background, at 256 and 512 pixels. They are project artwork, not an official Kakao logo.
