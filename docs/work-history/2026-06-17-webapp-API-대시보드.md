# 2026-06-17 webapp PWA 대시보드 + API 층 (M3)

- **유형**: 플랜모드 승인
- **관련 기획/이슈**: [[plans/작업재개-RESUME]] · webapp-conventions(M4 앞당김) · ADR-002/003(데이터) · M2 룰엔진(ec9d3b0)
- **시작 시점 커밋**: `df4da62` → **완료 커밋**: (완료 시 기입)

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

## After — 수행 후 실측 (완료 시 기입)
- 검증 결과: (npm build·컨테이너 ruff/mypy/pytest·API 스모크·E2E)
- 변경 규모: (diff stat)
- 커밋: (SHA)

## 비교/회고
- (완료 시) 의도 대비 달성·계획과 달라진 것·후속(백테스트 본문)
