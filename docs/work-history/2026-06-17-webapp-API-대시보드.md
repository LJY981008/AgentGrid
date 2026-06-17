# 2026-06-17 webapp PWA 대시보드 + API 층 (M3)

- **유형**: 플랜모드 승인
- **관련 기획/이슈**: [[plans/작업재개-RESUME]] · webapp-conventions(M4 앞당김) · ADR-002/003(데이터) · M2 룰엔진(ec9d3b0)
- **시작 시점 커밋**: `df4da62` → **완료 커밋**: A=`2c9ab10`(API) · B+C=이 커밋(webapp·compose·권한수정·하네스 drift)

## 의도/목적 — 왜
데이터 파이프라인·룰엔진(모멘텀→Top 랭킹)이 **CLI로만** 동작. 사용자 의도: 백테스트 구현 전에 **프론트를 먼저 완성**해 (1) 현재 기능을 UI로 실행·확인 (2) `docs/learning`(투자 학습노트)을 프론트에서 학습. 이후 백테스트를 만들어 프론트로 실행·검증. → 이 작업 = **FastAPI API 층 + 전체 PWA 대시보드(Vite+React+TS) + 학습 페이지**. 끝나면 수집·유니버스·Top 랭킹·학습을 브라우저에서 사용 가능.

## 계획 (승인된 플랜 전문 백업)
> 전문: `/home/code/.claude/plans/snappy-greeting-canyon.md` (승인). 핵심:

- **결정**: Vite+React+TS PWA / 전체 대시보드 한 번에 / API=FastAPI(계산은 서버, 프론트 읽기위주) / ⭐§4.1 미검증 경고 배지 상시 / 버전은 착수 시 tech-researcher 실측.
- **A. API `src/stockpick/api/`**(python-expert): health·dataset·ingest(라이브 EODHD·configure_logging)·ranking(meta.validated=false)·학습(tree·content·StaticFiles `/learning-assets`, path traversal 화이트리스트). CORS localhost:5173. 키 비노출. fastapi·uvicorn 추가. tests/test_api.py(TestClient·라이브0).
- **B. 프론트 `webapp/`**(frontend-expert): pages Dashboard(랭킹+경고배지+빈상태 유도)·Data(dataset+ingest 트리거·rate-limit 고지)·Universe·Learning(react-markdown+remark-gfm+rehype-slug, 상대경로 재작성→`/learning-assets`, lazy img)·Backtest placeholder. score 바 1차 CSS(Recharts는 백테스트 곡선 때). PWA(manifest·SW: 앱셸 precache·학습이미지 CacheFirst·API NetworkOnly). 모바일우선 TabBar.
- **C. devops compose**: app uvicorn `127.0.0.1:8000`·web node `127.0.0.1:5173`·**data 바인드(`./data:/app/data` 영속성)**·CI webapp 잡.
- **빌드순서**: 버전실측→API+app서버화→webapp 스캐폴드→타입/클라이언트(응답 실측캡처)→레이아웃→Dashboard→Data→Universe→Learning→Backtest placeholder→PWA→compose web→E2E→/harness-update·CLAUDE drift.
- **docs/learning 참고**: M2 백테스트·팩터 설계 시 00.caveats(생존편향·룩어헤드)·재무제표 등 반영(메모).
- **비목표**: 인증·rate limit 없음(1인 로컬)·/api/universe 보류·ingest 동기·백테스트 본문은 다음 마일스톤.

## Before — 수행 전 실측
- `webapp/` 미생성(영점). compose 에 web/node 서비스 없음(app+postgres만). fastapi/uvicorn/node 의존성 0(런타임 deps=duckdb·httpx·pyarrow).
- 백엔드 진입점: `ingest_tickers`(IngestSummary)·`rules.ranking.rank_by_momentum`(TopEntry)·`data/parquet`(gitignore, 컨테이너 한정·현재 9종목 적재).
- docs/learning: 5토픽 마크다운 12 + 이미지 112(상대경로), 한국어.
- 테스트 현황: 컨테이너 114 passed(이전 M2 슬라이스까지).

## After — 수행 후 실측
- **검증**: 컨테이너 pytest `134 passed`(M2 114 → +20 API 테스트, 라이브 0). webapp `npm run build` 타입체크+빌드 통과(node:22, 296 모듈). API 스모크(dataset·ingest·ranking·learning) wire-shape 캡처.
- **E2E (Playwright, http://localhost:5174)**: ① 빈 대시보드 → "수집 먼저" 안내 → DataPage `데모 9종목 수집` 버튼 → **라이브 EODHD 수집** → Parquet(named volume) → 검증 통과(9종목 2259행). ② 대시보드 랭킹 표시(NASDAQ GOOGL 0.3858/NVDA/AAPL/AMZN/META · NYSE XOM 0.3668/JNJ/JPM · `v0-momentum-126`) + **§4.1 미검증 경고 배지 상시**. ③ 학습 페이지 docs/learning 마크다운+이미지(`/learning-assets`)+표+토픽트리 렌더. 스크린샷 `dashboard-empty/ranking·learning-page.png`.
- **변경 규모**: A(`2c9ab10`) src/stockpick/api/** + tests/test_api.py. B webapp/ 36파일(src 18 ts/tsx + 설정/public). C compose.yaml +56/-9·Dockerfile +1·.dockerignore +4·ci.yml +19(webapp 잡). 하네스 drift: CLAUDE.md(Build·구조)·webapp-conventions(M4초안→M3실측)·webapp/.gitignore(*.tsbuildinfo).
- **⚠️ 블로킹 버그 1건 (수정)**: 프론트 ingest HTTP 500 — `data/parquet` `PermissionError`. 원인(로그+테스트 실측, 추측 아님): `./data` 호스트 바인드가 uid 1000 소유 vs 컨테이너 app uid 999 → Parquet 쓰기 거부. **수정**: Dockerfile `mkdir -p /app/data`(app 소유) + compose `./data` 호스트바인드 → **named volume `parquet-data`**(소유권 상속·포터블). 재빌드·재생성 후 UI 재수집 PASS.

## 비교/회고
- **의도 달성**: 사용자 의도("백테스트 전에 프론트부터 완성해 모든 기능 UI 실행·확인 + docs/learning 학습")를 충족 — 수집·유니버스·Top 랭킹·학습 전부 브라우저에서 동작. 첫 실행 흐름(빈→수집→랭킹) E2E 확인.
- **계획과 달라진 것**: ⭐ 데이터 영속을 플랜의 `./data` 호스트 바인드로 했더니 uid 권한 버그 발생 → **named volume** 으로 변경(플랜보다 나은 해법, 포터블). web/postgres 호스트 포트는 타 프로젝트(AiCrawl) 점유로 5174/5433 리맵. score 차트는 계획대로 순수 CSS(Recharts 미도입).
- **후속(다음 마일스톤)**: 백테스트 엔진(rolling as_of·CAGR/Sharpe/MDD·생존편향·거래비용) → `BacktestPage` placeholder 본문 채움. 설계 시 `docs/learning`(00.caveats 생존편향·룩어헤드, 재무제표) 참고. EODHD 결제 후 다년 history(ingest `start=None` 무변경 자동 확장) + EDGAR cik 매핑.
