---
name: impl-fastapi-api
description: FastAPI API 층(src/stockpick/api/) 구현 패턴 — DI 테스트·키비노출·path-traversal·계약 wire-shape·fastapi 0.137/mypy 함정
metadata:
  type: project
---

`src/stockpick/api/` = M3 HTTP 층(상위 모듈, data·rules·types 조합·역 import 금지). fastapi 0.137.1
+ uvicorn[standard] 0.49(pydantic 2.13·starlette 1.3 동반). 구조: `app.py`(create_app·CORS·startup
configure_logging·StaticFiles `/learning-assets`)·`models.py`(pydantic 계약=프론트 단일출처)·
`deps.py`(get_base_dir/get_learning_dir/get_cors_origins/get_source — DI 함수, 테스트 override 지점)·
`routes/{health,dataset,ingest,ranking,learning}.py`·`__main__.py`(uvicorn 0.0.0.0:8000).

**계약 wire-shape (프론트 단일출처 — 변경 시 프론트 깨짐):**
- 전부 snake_case·날짜 ISO `YYYY-MM-DD` 문자열·score=float·cik=""(미국 어댑터 미제공, 키는 ticker).
- `ranking?group=exchange`(기본) → **거래소별 rank 각각 1부터**(NASDAQ·NYSE 블록 이어붙임). `all`=통합.
- ⭐ `ranking.meta.validated` **항상 false** + warning 상시(§4.1 — 프론트 경고배지 fail-safe). 빈 데이터도 warning 유지·200.
- ingest 에러 **키비노출**: 502(EodhdAuthError)·429(EodhdRateLimitError)·500(VerificationError) 모두 상수 detail(원문 예외 메시지=토큰 실릴 여지 비노출). 종목별 실패는 results.error 집계(200·passed=false).

**검증된 패턴:**
- 테스트 라이브 0: TestClient + `app.dependency_overrides`(get_base_dir→tmp·get_source→FakeSource) + 합성 Parquet(write_daily_bars). FakeSource=DataSource Protocol 직접 구현(name·iter_universe·fetch_daily_bars).
- learning content **path-traversal 화이트리스트**: `(base/rel).resolve()` 후 `is_relative_to(base.resolve())` 아니면 404(존재여부 비노출). 심볼릭링크도 resolve 가 펼침. .md 만 허용(임의파일 차단).
- dataset/ranking 은 api 가 DuckDB 직접 스캔 허용(상위 모듈, 저장 레이아웃 읽기만). SQL 경로는 `read_parquet($glob, hive_partitioning=true)` $glob 바인딩(_scan.py 규약). source=파일내부컬럼·exchange=Hive 파티션.

**함정(실측):**
- **fastapi 0.137 include_router** → `app.routes` 에 `_IncludedRouter` lazy 등록, `APIRoute` 평탄목록 비어보임(실동작 정상 — TestClient 로 검증).
- **starlette TestClient `.app` = ASGIApp(Callable)** → `client.app.dependency_overrides` mypy attr-defined 에러. fixture 가 FastAPI app 을 별도 속성(`fastapi_app`)으로 부착해 해소(동적 부착은 mypy Any 통과).
- **B008**(Depends/Query in default) FastAPI 오탐 → pyproject `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls=["fastapi.Depends","fastapi.Query"]`. ⚠️ 이 설정은 단일파일 바인드+atomic Edit 으로 컨테이너 미반영될 수 있음 → [[env-docker-uv-add]] 참고(재기동 필요).
- 컨테이너에 **curl 없음** → 스모크는 `python -c "import httpx; httpx.get(...)"` 로(라이브 서버 대상).
- `_DEMO_UNIVERSE`(9종목) data.ingest **private** → api/routes/ingest.py 가 복제 보유(data 데모 변경 시 동반 갱신).

**미바인드(devops 후속 C층):** compose volumes=src·tests·pyproject 만 → `docs/learning`·`data/parquet` 컨테이너 미바인드. 스모크는 컨테이너 내부 임시 생성(호스트 미바인드라 git 누수 0·재기동 시 소멸). 실운영 learning·랭킹엔 `./docs`·`./data` 바인드 필요.
