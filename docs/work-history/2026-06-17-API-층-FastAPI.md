# 2026-06-17 API 층 (FastAPI) — M3 A층

- **유형**: 일반 구현 (상위 플랜모드 작업 [[2026-06-17-webapp-API-대시보드]] 의 A층)
- **관련 기획/이슈**: webapp+API 통합 플랜(`snappy-greeting-canyon.md`) §A · API 상세 플랜(`snappy-greeting-canyon-agent-aad54bf0f6f8ff393.md`)
- **시작 시점 커밋**: `333fb3e` → **완료 커밋**: (커밋 시 기입)

## 의도/목적 — 왜
데이터 파이프라인(EODHD 수집→Parquet→검증)·룰엔진(모멘텀→Top 랭킹)이 **CLI로만** 동작. 프론트(Vite+React PWA, 후속)가 소비할 **HTTP API 층**을 만든다. 계산은 전부 서버(단일 진실), 프론트는 읽기 위주. ⭐ 핵심 산출물 = **명확한 응답 계약(pydantic)** = 프론트 TypeScript 타입의 단일 출처. 직전 시도가 서버 rate limit으로 코드 0(api/ 미생성) 중단 → 재개.

## Before — 수행 전 실측
- `src/stockpick/api/` 미생성(영점). 런타임 deps = duckdb·httpx·pyarrow(fastapi/uvicorn 0).
- 하위 진입점 실측: `ingest_tickers(source, targets, *, base_dir, start, end) -> IngestSummary`(data.ingest) / `load_adjusted_series`·`load_ticker_exchanges`(rules._scan) · `momentum_universe`(rules.factors) · `rank_by_momentum`(rules.ranking) → `TopEntry`. `_DEMO_UNIVERSE`(9종목)·`VerificationReport.shortfall_tickers`=(ticker,expected,actual) 튜플.
- `data/parquet`·`docs/learning` 모두 컨테이너에 **미바인드**(compose volumes=src·tests·pyproject만). docs/learning 호스트엔 5토픽 마크다운+이미지 112.
- 테스트 현황: 컨테이너 114 passed(M2까지).

## 계획 (요약 — 전문은 위 두 플랜 파일)
- `api/` = 상위 모듈(data·rules·types import, 역 금지). `app.py`(CORS·startup configure_logging)·`models.py`(pydantic 계약)·`deps.py`(base_dir·CORS·source factory = dependency_overrides 테스트 지점)·`routes/{health,dataset,ingest,ranking,learning}.py`·`__main__.py`(uvicorn 0.0.0.0:8000).
- 엔드포인트: health·dataset(DuckDB 집계)·ingest(라이브 EODHD·configure_logging 선행·에러 키비노출 502/429/500)·ranking(**meta.validated=false+warning §4.1**·422 검증)·learning(tree·content path-traversal 화이트리스트·StaticFiles `/learning-assets`).
- 테스트 `tests/test_api.py`: TestClient + dependency_overrides + 합성 Parquet + FakeSource(라이브 0).

## After — 수행 후 실측
- **검증(컨테이너 정본)**: `ruff check && ruff format --check && mypy && pytest -q` → 전부 PASS. **pytest 134 passed**(기존 114 + 신규 20).
- **기동 스모크**(uvicorn 0.0.0.0:8000, 합성 9종목 Parquet + 임시 learning):
  - `GET /api/health` → `{"status":"ok","version":"0.0.1"}`
  - `GET /api/dataset` → ticker_count=9·total_rows=540·sources=["synthetic-smoke"]·tickers[].snake_case
  - `GET /api/ranking?top_n=3` → 거래소별 랭킹(NVDA rank1 NASDAQ / XOM rank1 NYSE)·score float·cik="" · **meta.validated=false + warning("§4.1")** 확인
  - `GET /api/learning/tree`·`content`(dir 필드)·**traversal `../../etc/passwd` → 404 차단**·`/learning-assets/*.png` 200·**CORS preflight(localhost:5173) → allow-origin 정상**
- **변경 규모**: 신규 api 11파일 + tests/test_api.py(합계 ~1202줄). pyproject(+7: fastapi·uvicorn·bugbear immutable-calls)·uv.lock(37 packages resolved).
- **커밋**: (커밋 시 기입)

## ⭐ API 계약 (프론트 단일 출처 — wire-shape 실측)
- 모든 필드 snake_case, 날짜 ISO `YYYY-MM-DD` 문자열, score = JSON number(float), cik = "" (미국 어댑터 미제공 — 표시 키는 ticker).
- `ranking?group=exchange`(기본): **거래소별로 rank 가 각각 1부터**(NASDAQ 블록·NYSE 블록 이어붙임). `group=all` 이면 통합 단일 랭킹.
- `ranking.meta.validated` 는 **항상 false** + warning 상시 → 프론트 경고 배지 fail-safe.
- 에러 키비노출: ingest 502(인증)/429(rate limit)/500(검증) 모두 상수 detail(EODHD 토큰 비포함).

## 회고 / 함정
1. **컨테이너 단일 파일 바인드 마운트 + atomic Edit 함정**: 호스트 `pyproject.toml` Edit(atomic write=inode 교체)이 `./pyproject.toml:/app/pyproject.toml` 바인드를 끊어 컨테이너가 옛 내용을 봄(ruff bugbear 설정 미반영). → **컨테이너 재기동(`up -d --force-recreate`)으로 마운트 재연결** 후 반영. 단일 파일 바인드 마운트 편집 시 주의.
2. **ruff 0.15(컨테이너) vs 0.8(호스트) 버전 격차** → format 결정이 갈릴 수 있어 호스트 format 미사용, 컨테이너 정본 diff를 호스트 Edit으로 수기 반영(E501 한글 width 2 계산 함정 포함).
3. **fastapi 0.137 include_router**: `app.routes` 에 `_IncludedRouter` 로 lazy 등록 → `APIRoute` 평탄 목록이 비어 보임(실동작은 정상, TestClient 로 검증).
4. **starlette TestClient `.app` 타입 = ASGIApp(Callable)** → `client.app.dependency_overrides` 가 mypy attr-defined 에러. fixture 가 FastAPI app 을 별도 속성(`fastapi_app`)으로 노출해 해소.
5. **B008(Depends/Query in default)**: FastAPI 관례 오탐 → `flake8-bugbear.extend-immutable-calls=["fastapi.Depends","fastapi.Query"]` 로 한정 허용(가변 기본값 list() 등은 여전히 잡힘).

## 미해결 / 다음
- **docs/learning·data/parquet 컨테이너 미바인드**: 스모크는 임시 생성으로 우회. 실운영 learning 라우트·`/learning-assets` 동작에는 **compose 에 `./docs`·`./data` 바인드 필요(devops 후속, C층)**. 안 하면 learning 빈 트리·랭킹 빈 응답.
- **compose 포트매핑(127.0.0.1:8000)·uvicorn command·web 서비스** = devops 후속.
- `_DEMO_UNIVERSE` 9종목을 api(ingest.py)가 **복제 보유**(data.ingest private 라 import 불가). data 모듈 데모 변경 시 함께 갱신 필요(향후 public 승격 검토).
- 프론트(B층)는 이 계약(snake_case·거래소별 rank·validated=false)을 1:1 미러.
