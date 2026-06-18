# 🔄 작업 재개 플랜 (compact 생존용 — 이 문서 하나로 바로 이어가기)

> **compact된 Claude 읽는 법**: CLAUDE.md → [PLAN_STATUS](PLAN_STATUS.md) → 이 문서. 결정은 ADR(`docs/decisions/`), 데이터 스펙은 [M1-데이터파이프라인](M1-데이터파이프라인.md). 최신 갱신 2026-06-17(M3 API+webapp 반영).
> 💡 **EODHD 무료티어 실측(2026-06-17)**: 가격 history=**최신 1년(251 거래일)만**, 과거 범위 요청은 무시. **유니버스는 무료 전체**(활성 51,705 + 폐지 57,825 = 109,530, 폐지 리스트 포함). 파이프라인 end-to-end(EodhdSource→Parquet→검증 게이트)가 무료 실데이터로 PASS. → **M2(룰·백테스트) 개발은 무료 1년치로 가능**, 전체 다년 history만 유료($19.99) 전환. 결제를 M2 끝까지 미룰 수 있음.

> **현 위치 한 줄**: 미장(미국주식) stockpick. M0~M1 파일럿·전체점검·코드리뷰 완료. **+ M2 착수**: EODHD generic 적재(`ingest.py`, history 무관·결제후 자동확장)로 무료 1년치 9종목 데이터셋 + **룰엔진 수직슬라이스**(`src/stockpick/rules/` 모멘텀 팩터→Top 랭킹, 룩어헤드 sabotage 검증, 114 passed). Top 랭킹 라이브 동작 확인(GOOGL 38.58%·XOM 36.68% 등). **+ M3 착수·완료**(2c9ab10·b7c5b21): FastAPI API층(`src/stockpick/api/` — routes/{health,dataset,ingest,ranking,learning}로 수집·랭킹·학습 HTTP 노출, `ranking`에 `meta.validated=false` 하드코딩 §4.1 미검증 경고 상시) + webapp PWA(`webapp/` Vite8/React19, pages 5화면: Dashboard(랭킹)·Data·Universe·Learning·Backtest placeholder + 404) + compose 풀스택(postgres+app+web). **+ M2 백테스트 엔진 골격 완료**(`src/stockpick/backtest/` 14모듈·자체구현 ADR-004·룩어헤드(진입 t+1)/생존편향(UniversePort)/폐지청산 가드·CAGR/Sharpe/MDD·IS/OOS 워크포워드·purge·decay·등가중 벤치, 173 passed, 데모 9종목 13기간 동작·룰이 등가중벤치 언더퍼폼=미검증 입증). **+ M3 후속 완료**(#4·#2·#5, 푸시됨): `/api/backtest`+BacktestPage(Recharts 자산곡선·벤치·미검증경고) · EDGAR cik resolver(`data/edgar`·`EdgarSnapshotResolver`, 라이브 10,414건·`/api/ranking` 실 CIK) · 리밸 루프 공유헬퍼(`calendar.holding_periods`). 197 passed. **다음 = S6 데이터 신뢰성 게이트**(EODHD 결제 $19.99·다년·전체유니버스·실폐지) 후 백테스트 실검증 — 그 전 `meta.validated=true` 금지. 상세 백로그 ↓.
> ⚠️ **데이터셋은 컨테이너 내부 `data/parquet`만**(호스트 미마운트·gitignore) — 컨테이너 재생성 시 소실, `python -m stockpick.data.ingest` 재실행으로 복원. 룰 데모/백테스트는 `docker compose exec` 로.

## 확정 결정 (변경 금지 — 근거는 ADR)
- **시장**: 미국(NYSE/NASDAQ/AMEX). 한국 보류(나중 재사용 가능).
- **가격**: Tiingo(파일럿·무료)→**EODHD**(본격 $19.99/월, [ADR-003](../decisions/ADR-003-M2-가격소스-EODHD.md)). **재무**: SEC EDGAR(무료·`filed`=PIT)+edgartools ([ADR-002](../decisions/ADR-002-미국-데이터소스-아키텍처.md)).
- **결합**: 가격↔재무 `merge_asof` PIT 조인(disclosed_at≤t). **마이그레이션**: alembic ([ADR-001](../decisions/ADR-001-마이그레이션-도구-alembic.md)).
- **종목 식별**: CIK(안정·무재사용)+ticker(시변·재사용) → `ticker_history` 브리지로 재사용 생존편향 누수 차단.
- **기각**: SimFin(PIT 미충족), RabbitMQ(1인 배치 과설계), LLM 런타임 정규화(무결성), yfinance(생존편향).
- **history**: 30년 강제 아님(예시였음) — 데이터 가용범위 전부(많을수록 검증 정확도↑).
- **재현성 vs 해지-삭제 조항**: 무관(과거 EOD 불변·재구독 동일데이터 재취득). 개인·비배포 사용. 시스템에 위반 인코딩 안 함.
- **신뢰성 게이트**: M1 넓게 수집+품질꼬리표 / 표준(1%)·엄격(0.5%) 임계는 M2 민감도분석 gap(과적합 금지). **폐지 fallback**: 확보분+누락 정량고지, 커버리지 하한 미달 시 M1 차단.

## 현 코드 상태 (HEAD 기준)
- `src/stockpick/types.py`: `Exchange`(StrEnum), `Stock`(cik+ticker), `DailyBar`(ticker·Decimal OHLC·adj_factor), `TopEntry`(cik앵커). `Financial`은 EDGAR 단계 보류(주석).
- `src/stockpick/data/source.py`: `DataSource` Protocol(runtime_checkable) — `iter_universe(include_delisted=True)`·`fetch_daily_bars`.
- `src/stockpick/data/tiingo.py`: `TiingoSource` — EOD, `Authorization: Token`(Bearer아님), adj_factor=adjClose/close. 모킹 테스트 `tests/test_tiingo.py`.
- `src/stockpick/data/storage.py`: Hive Parquet(`exchange=/year=`, decimal128 정밀보존, 멱등 **ticker별 파일**, source/ingested_at) + DuckDB 검증 게이트. `tests/test_storage.py`.
- `src/stockpick/data/pilot.py`: 라이브 파일럿(`python -m stockpick.data.pilot`). `tests/test_pilot.py`.
- `src/stockpick/data/eodhd.py`: `EodhdSource(DataSource)` — `GET /api/eod/{TICKER}.{EX}`, `?api_token=` 쿼리 인증, raw OHLC+adjusted_close→adj_factor, 폐지 포함 유니버스. `tests/test_eodhd.py`.
- `src/stockpick/data/_adjust.py`: 공유 `compute_adj_factor`(adjusted/raw 12자리 quantize). `src/stockpick/data/ingest.py`: 소스무관 generic 적재(history 무관·결제후 자동확장). `tests/test_{adjust,ingest}.py`.
- `src/stockpick/rules/`: `factors.py`(모멘텀)·`ranking.py`(Top 랭킹·TopEntry)·`_scan.py`(룩어헤드 as_of 가드)·`demo.py`·`__main__.py`. `tests/test_rules.py`.
- `src/stockpick/api/`: FastAPI(`app.py`·`deps.py`·`models.py` pydantic 계약·`routes/{health,dataset,ingest,ranking,learning}.py`). `python -m stockpick.api` 기동. `tests/test_api.py`. ⚠️ ranking `meta.validated=false` 상시(백테스트 엔진은 구현됐으나 S6 미통과·골격이라 룰 미입증).
- `webapp/`: PWA(Vite8/React19/react-router7/TS) — `src/{api,components,pages}`, 5 nav 화면+404. compose `web` 서비스.
- `src/stockpick/backtest/`: **M2 엔진 골격**(config·calendar·costs·strategy·ports·adapters·fakes·metrics·engine·benchmark·validation·demo). 룩어헤드(진입 t+1)·생존편향(UniversePort.constituents)·폐지청산(recovery_rate)·IS/OOS 워크포워드·purge·decay·등가중 벤치. ⚠️ 골격 유니버스=가격기반(FakeUniversePort)·cik 미해소 — 실데이터(종목마스터·ticker_history)는 S6 후.
- 명세: `docs/apis/{tiingo,eodhd}/`(tiingo 16섹션·eodhd 62섹션). 규칙: `.claude/rules/api-spec-reference.md`(data/** 편집 시 자동 로드).
- **검증됨**: 라이브 5종목(AAPL/NVDA/TSLA/MSFT/JNJ)×2124행, 분할 교차검증 통과(AAPL 4:1 adj 0.2425·NVDA 10:1 0.0998·TSLA 3:1 0.3333), 중복 0.

## 환경·검증·하네스 (compact-me 필독 — 안 그러면 재발견에 시간낭비)
- **검증(컨테이너 정본)**: `docker compose exec -T app sh -c 'ruff check src tests && ruff format --check src tests && mypy && pytest -q'`
- **의존성 추가(컨테이너 권한 함정)**: 그냥 `exec uv add` 안 됨 → CLAUDE.md Build 섹션의 우회 절차(uv.lock 바인드+`--no-sync`→`build`) 사용.
- **라이브 키**: `.env`(gitignore)에 `TIINGO_API_KEY`·`EODHD_API_KEY`(EODHD 결제 전·무료티어). compose가 interpolation 주입 — 키 변경 후 `docker compose up -d --no-deps app` 재생성.
- **하네스 BLOCKING**: ①`src/**` 변경 커밋엔 `docs/work-history/` 엔트리 필수(drift 차단) ②외부 API 코드는 `docs/apis/` 명세 참조(환각 금지) ③커밋 태그 강제(feat/fix/refactor/docs/test/chore/perf) ④푸시는 사용자 요청 시만 ⑤docs/plans→PLAN_STATUS·decisions/research→HOME·compose/pyproject→CLAUDE.md drift 동반.
- ⚠️ **커밋 메시지 함정**: 본문에 `(명령어)` 괄호 넣으면 verify-commit-msg 훅이 subject로 오파싱→차단. **메시지를 파일로 써서 `git commit -F <file>`** 로 커밋.
- ⚠️ **문서 페치**: 벤더 docs가 JS SPA면 `https://r.jina.ai/{url}` 렌더 프록시 경유(Tiingo 교훈).
- **work-history**: `docs/work-history/` + INDEX. **docs/learning/은 사용자 소유** — 건드리지 말 것.

## 🎯 남은 작업 (순서·실행단위 — "이거 하자" 하면 바로)

> ⚠️ 진행 순서 실측: 무료 1년치로 **M2 룰 슬라이스·M3 API/webapp·M2 백테스트 엔진 골격·#4·#2·#5 까지 코드층 완료**(데이터 신뢰성과 독립). **남은 핵심 = 결제 후 데이터 신뢰성(S6) + 백테스트 실검증** — 생존편향·룩어헤드는 실데이터(폐지 포함)라야 의미.

### 📋 후속 백로그 (M2 엔진+#4·#2·#5 후 — 영속 todo)

> 💰 = EODHD 결제 잠금해제(✅ **2026-06-18 결제 완료** — EOD Historical $19.99) → 이제 actionable / 🔮 = 무료 가능하나 가치는 데이터 후 / 🧹 = 코드 품질
> ⚠️ EODHD 플랜 능력(허용/미허용) = [[../apis/eodhd/pricing_plan/PLANS|PLANS.md]]. 우리 플랜은 가격(EOD·수정주가·폐지·분할배당·30년+) 전부 ✅, **재무(Fundamentals)는 ❌** → 재무는 SEC EDGAR(#재무-1 구현됨). 결제만으로 validated=true 아님 — 다년 수집+S6 게이트 필요.

- [ ] 💰→🟢 **TASK-E/S5**(결제됨·actionable·**4분해 a→b→c→d**): 다년 history + 전체 유니버스(폐지 포함) 적재 + 종목마스터(listed/delisted). 설계 `docs/superpowers/specs/2026-06-18-S5a-적재안전성-설계.md`
  - [x] ✅ **S5-a 적재 안전성**(2026-06-18): PG 코어 스키마(alembic 첫 실사용·stock+ticker_history+daily_bar·ADR-006)·G1 write read-merge-write(소실 봉인)·`data/db.py`(Parquet→PG 단방향 동기·cik""≡NULL). 237 passed. [[../work-history/2026-06-18-S5a-적재안전성]]
  - [x] ✅ **S5-b 종목마스터 채움**(2026-06-18): EODHD Common Stock 유니버스(`data/universe.py`)→PG stock 50,184 security(active 18,316+delisted 31,868)·listing_status·cik EDGAR enrich(16.4%)·ticker_history 스냅샷·G2 master_tickers. 다중클래스주 보존((cik,ticker) UNIQUE·migration 0003·GOOGL 버그수정)·demo 9/9. 246 passed. [[../work-history/2026-06-18-S5b-종목마스터]]
  - [ ] 🟢 **S5-c 벌크 오케스트레이션**: 유니버스 자동조회→가격 적재 루프(G5)·체크포인트/재시도(G4)·검증 병목(G8)·실벌크 PG 동기·**날짜 backfill(listed_at/delisted_at=가격 min/max trade_date)**·expected shortfall wiring. ⚠️ 진입점 configure_logging() 호출(G6)
  - [ ] 🟢 **S5-d 실 UniversePort+S6**: 종목마스터 기반 UniversePort(G7)·**ticker_history EXCLUDE 구간중첩 제약(C2 — S5-b 무한스냅샷 대체 후)**·시점 cik 해소(TickerHistoryResolver·G9)·거래소 정밀화(EODHD OTC 폴백 보강)·S6 게이트→validated=true
- [ ] 💰 **실 UniversePort**: 종목마스터 기반 `UniversePort`(현 골격 `PriceDerivedUniverse` 가격기반 교체 — survivorship 정답)
- [ ] 💰 **S6 신뢰성 게이트** 통과 → 백테스트 수치 신뢰 → `meta.validated=true` 전환(§4.1)
- [ ] 🔮 **TickerHistoryResolver**: 시점별 ticker↔cik(SEC submissions 이력 — ticker 재사용 생존편향 정답). 현 `EdgarSnapshotResolver`는 현재 스냅샷만
- [x] ✅ **EDGAR 재무층 슬라이스(#재무-1, 2026-06-18)**: companyfacts 직접 JSON 파싱([ADR-005](../decisions/ADR-005-재무-직접파싱.md))·`FinancialFact`·PIT(filed<=as_of)·ROE/P/B 팩터→ranking factors 노출(결합 안함·§9-2). 라이브 9종목 4571 fact·7/9 ROE·5/9 P/B 실값. [[../work-history/2026-06-18-EDGAR-재무층]]
  - 후속 [ ] 🔮 **재무 커버리지 확장**: ① StockholdersEquity 변형 태그 폴백(JNJ=NCI 포함 태그라 연간 0) ② 다중클래스 주식수 합산(GOOGL/META dei shares=0 → P/B 불가) ③ TTM(4분기합) ROE ④ edgartools 광범위 정규화(~15필드) — ADR-005 재검토 트리거
- [ ] 🔮 **walk-forward·decay UI**: BacktestPage 에 IS/OOS·민감도(다년 데이터라야 통계 유의) / 파라미터 전체폼
- [ ] 🧹 **recharts 청크 코드스플릿**(>500KB) · 거래비용/벤치 비대칭 등 리뷰 Open Question(work-history 참조)

> 위 백로그 원천 = 각 work-history "후속" 섹션(2026-06-17 M2백테스트·#4·#2·#5). 이 목록이 단일 진입점.

### TASK-A: EODHD 명세 캐처 ✅ **완료**(커밋 397b244)
- `docs/apis/eodhd/` 62섹션 JSON + `_index.json` + README(HOME 링크). 워크플로우 `eodhd-spec-capture`(discover→capture). 189 엔드포인트, OK 54/PARTIAL 8.
- 인증 실측 = `?api_token=<KEY>` 쿼리, base `https://eodhd.com/api`, 심볼 `{TICKER}.{EX}`. 핵심 EOD = `GET /api/eod/{SYM}`(raw OHLC + `adjusted_close`→adj_factor).
- bulk-api-eod-splits-dividends 만 partial(보강 여지). 비핵심(intraday/options/crypto 등)도 전부 저장됨.

### TASK-B: 게이트 소실 미탐지 보강 ✅ **완료**(734a52f)
- `storage.py` `verify_parquet(expected=)` — 적재 전후 ticker 집합·행수 대조, missing/shortfall→VerificationError. `build_expected()`·`TickerExpectation`. pilot 누적 expected 전달. sabotage 검증 완료.
- ⚠️ S5 연결 시: expected 원천을 **종목마스터(상장+폐지 합집합)**로 교체해야 진짜 생존편향 가드(M1 §5 폐지 하한 결합, db-architect).

### TASK-C: adj_factor quantize ✅ **완료**(42df8d1)
- `src/stockpick/data/_adjust.py` 공유 `compute_adj_factor` — adjusted/raw 소수 12자리 quantize. storage scale 37→12. tiingo·eodhd 공용. (방향=adjusted/raw, 계약 adjusted=raw*adj_factor)

### TASK-D: EodhdSource 어댑터 ✅ **완료**(42df8d1)
- `src/stockpick/data/eodhd.py`: `EodhdSource(DataSource)`. `GET /api/eod/{TICKER}.{EX}`, 인증 `?api_token=`(쿼리), raw OHLC+`adjusted_close`→adj_factor(공유헬퍼), value=None. `iter_universe` 폐지 포함(exchange-symbol-list 활성+delisted=1 병합). cik="" (EODHD 미제공). 모킹 26테스트.

### TASK-E: S5 전체 유니버스 + S6 게이트 (EODHD 결제 $19.99 후 라이브)
- 전체 미국 종목(폐지 포함) 벌크 적재 → 생존편향-correct. + 재무 EDGAR 결합(merge_asof PIT). S6 신뢰성 게이트 전항목 PASS → **M1 완료 선언** → M2 백테스트.
- ⛔ **라이브 전 BLOCKING(키 누출)**: EODHD 토큰이 URL 쿼리(`?api_token=`)라 **httpx 자체 INFO 로거가 완성 url(토큰 포함)을 로깅**. 우리 코드는 비노출이나 httpx 라이브러리 로거는 못 끔 → **진입점/로깅설정에서 `logging.getLogger("httpx").setLevel(WARNING)` 필수**(EODHD 라이브 실행 전).
- 선결: ①EODHD expected 원천=종목마스터(TASK-B 후속) ②EDGAR 재무층 구현(edgartools, `financial` fiscal_period≠disclosed_at) + **cik 매핑**(EODHD가 CIK 미제공 → EDGAR ticker→CIK 보강, 조인 기준) ③alembic 마이그레이션(stock cik PK·ticker_history·daily_bar — db-architect) ④**write read-merge-write 전환**(현 `(ticker,year)` 통파일 덮어쓰기는 같은연도 증분 부분호출 시 소실 — 일일증분 전 필수, docstring 경고만 박힘) ⑤EODHD 라이브 진입점은 `configure_logging()` 호출 확인(httpx 토큰가드 — 코드화됨, pilot.main 적용).
- ✅ 리뷰 반영(커밋 7f3b286): 양수성 게이트(음수/0 가격·adjusted 차단) · httpx 가드 코드화 · _adjust 단위테스트 · nits. 미반영(선택): iter_universe 부분실패·교차거래소 중복 테스트.

## 미해결·주의
- EDGAR 재무층 미구현(M2 직전) — edgartools ~15필드 정규화 정확도 표본검증 필요.
- EODHD 폐지 가격 깊이·배당 정확도 = 가입 후 표본 실측.
- alembic 마이그레이션·`ticker_history` 테이블 미구현(db-architect, S5 선결).
- 6개월 주기 데이터소스 약관·가격 재검증.

## 핵심 파일 인덱스
- 결정: `docs/decisions/ADR-001~003`. 기획: `docs/plans/stock-1st_plan.md`(기준선)·`M1-데이터파이프라인.md`(스펙)·`PLAN_STATUS.md`(현황).
- 리서치: `docs/research/2026-06-16-미국주식-데이터소스.md`·`2026-06-17-webapp-stack-버전.md`. 명세: `docs/apis/{tiingo,eodhd}/`.
- 코드: `src/stockpick/{types.py, data/{source,tiingo,eodhd,_adjust,ingest,storage,pilot}.py, rules/{factors,ranking,_scan}.py, api/{app,deps,models,routes/*}.py, backtest/{config,calendar,costs,strategy,ports,adapters,fakes,metrics,engine,benchmark,validation,demo}.py}` + `webapp/src/`. 계약 규칙: `.claude/rules/{python-conventions,api-spec-reference,logging-rules,webapp-conventions}.md`.
- 커밋 흐름: 7d60ab9(M0)→606ba0b(M1 S0-S1)→8e5d136(미장아키)→24b030b(Docker)→2f4d496(계약)→e57b8d6·982574d(Tiingo명세)→61b55c0(어댑터)→0f69a53(저장·파일럿)→096e7f3(키주입)→11fedce(EODHD확정).
