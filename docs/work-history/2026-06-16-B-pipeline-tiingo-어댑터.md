# 2026-06-16 B-pipeline — Tiingo EOD 가격 어댑터 (1~3단계)

- **유형**: 일반 구현
- **관련 기획/이슈**: B-pipeline 1~3단계 / [[2026-06-16-B-contract-미국계약]] (DataSource Protocol 구현) / api-spec-reference 규칙
- **시작 시점 커밋**: `982574d` → **완료 커밋**: `<커밋 시 기입>`

## 의도/목적 — 왜 이 작업을 하나

미국 주식 가격 데이터를 실제로 끌어올 첫 어댑터. `data/source.py` 의 `DataSource` Protocol 을
Tiingo EOD 로 구체화해서, 이후 Parquet 저장·라이브 파일럿·랭킹/백테스트가 단일 ticker 의 일봉
(`list[DailyBar]`)을 받을 수 있게 한다. 이 단계는 **어댑터 코드 + 모킹 단위 테스트까지만** —
라이브 API 호출은 후속(사용자와 함께).

## 계획 (개요)

1. HTTP 클라만 추가(httpx — mypy strict 네이티브 타입, 스텁 불요). pandas/pyarrow/duckdb 는 다음 단계.
2. `src/stockpick/data/tiingo.py` — `TiingoSource(DataSource)`:
   - 인증: `TIINGO_API_KEY` 를 **호출 시점** os.environ 에서, 헤더 `Authorization: Token <KEY>`(Bearer 아님).
   - `fetch_daily_bars`: `GET /tiingo/daily/{ticker}/prices` → raw OHLCV + `adj_factor=adjClose/close`(Decimal).
   - `iter_universe`: 전체 나열 수단 부재(명세 한계) → 생존편향 회피 위해 `NotImplementedError`(명시 사유).
   - 에러 분류: 429(rate limit)/401·403(auth)/기타 4xx·5xx/타임아웃, 키 비노출.
3. `tests/test_tiingo.py` — `httpx.MockTransport` 로 라이브 0, end-of-day.json 형태 픽스처.

## Before — 수행 전 실측

- `src/stockpick/data/` = `__init__.py`, `source.py`(Protocol만, 외부 의존 0).
- `pyproject.toml` `dependencies = []`. 컨테이너 .venv 에 httpx 없음.
- tests = `test_contract.py`(계약 스모크) 1개.
- 진실 원천 실측: `docs/apis/tiingo/end-of-day.json`(prices 엔드포인트·필드), `general-connecting.json`
  (Token 헤더), `utilities-search.json`(search 는 검색어 기반·전체 나열 수단 없음, `isActive` 폐지식별 가능).

## After — 수행 후 실측

- **검증**(컨테이너 정본 `docker compose exec -T app`):
  - `ruff check src tests` → All checks passed!
  - `ruff format --check src tests` → 9 files already formatted
  - `mypy` → Success: no issues found in 9 source files
  - `pytest -q` → 26 passed (test_tiingo.py 21 + test_contract.py 5), 0.07s
- **변경 규모**: `tiingo.py`(신규), `test_tiingo.py`(신규), `pyproject.toml`(+httpx>=0.28.1),
  `uv.lock`(+72줄). (compose 의 uv.lock 마운트는 **미적용** — devops-engineer 협의 후속, 아래 회고 참조.)
- **커밋**: `<SHA>` (커밋은 사용자 요청 시)

## 비교/회고

- **의도 대비 달성도**: 어댑터+모킹 테스트 완료, 검증 전부 통과. 라이브 호출 0 보장(MockTransport).
- **계획과 달라진 것 + 이유**:
  - `uv add` 가 컨테이너 권한 문제로 막힘 — 마운트된 `pyproject.toml`(호스트 uid 1000) vs 이미지내
    `uv.lock`(컨테이너 uid 999 app) 소유 불일치. `docker compose run --no-deps --user 1000:1000
    -e UV_CACHE_DIR=/tmp/uvcache -v $PWD/uv.lock:/app/uv.lock app uv add --no-sync httpx` 로 호스트
    파일 양쪽 갱신 후 `docker compose build`+재생성으로 .venv 반영. **구조적 누락**: compose 에
    `uv.lock` 바인드 마운트가 없어 다음 `uv add` 도 같은 문제 발생 → compose 마운트 추가는
    재생성·CI 영향이 있어 단독 결정 보류, devops-engineer 협의 후속으로 남김(이번엔 -v 일시 마운트로 우회).
  - `iter_universe` 는 `NotImplementedError`(명세상 전체 유니버스 나열 수단 부재). 빈 리스트로
    조용히 누락하면 생존편향 BLOCKING 위반이라 명시적 실패 선택. 본격 유니버스는 Sharadar SEP(M2).
  - `search_assets()` 추가(명세 search 엔드포인트, `isActive` 폐지식별 보존) — universe 대용 아님, raw 반환.
- **금융 BLOCKING 준수**: 수정주가 원본 불변(raw 저장 + `adj_factor=adjClose/close`), close=0/adjClose
  결측 경계는 factor=1 + WARNING(조용한 왜곡 금지), 결측 행 추측 채움 없이 누락, 키 비노출.
- **후속 작업**:
  - [ ] Parquet 저장 단계(pandas/pyarrow/duckdb 추가) — 어댑터 `list[DailyBar]` → 컬럼 저장.
  - [ ] 라이브 파일럿(사용자와 함께, 실제 키): rate limit 백오프·체크포인트 실측 보강(현재 자리만 마련).
  - [ ] compose `uv.lock` 마운트 추가가 CI/빌드에 부작용 없는지 devops-engineer 확인.
