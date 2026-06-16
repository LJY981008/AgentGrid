# 🔄 작업 재개 플랜 (compact 생존용 — 이 문서 하나로 바로 이어가기)

> **compact된 Claude 읽는 법**: CLAUDE.md → [PLAN_STATUS](PLAN_STATUS.md) → 이 문서. 결정은 ADR(`docs/decisions/`), 데이터 스펙은 [M1-데이터파이프라인](M1-데이터파이프라인.md). 최신 갱신 2026-06-16.
> **현 위치 한 줄**: 미장(미국주식) stockpick. M0 전환 + M1 파일럿(Tiingo) 검증 + Tiingo·EODHD 명세 + **TASK-A~D 완료**(EODHD 명세·게이트 소실탐지·adj_factor quantize·EodhdSource 어댑터, 전부 모킹 검증 77 passed). **다음 = TASK-E(S5 전체 유니버스) — EODHD 결제 후 라이브** (라이브 전 httpx 토큰누출 가드 필수, 아래 TASK-E). 무료 개발분은 사실상 소진 — 남은 건 결제 + EDGAR 재무층 + db-architect 마이그레이션.

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
- 명세: `docs/apis/tiingo/`(16섹션). 규칙: `.claude/rules/api-spec-reference.md`(data/** 편집 시 자동 로드).
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
- 선결: ①EODHD expected 원천=종목마스터(TASK-B 후속) ②EDGAR 재무층 구현(edgartools, `financial` fiscal_period≠disclosed_at) + **cik 매핑**(EODHD가 CIK 미제공 → EDGAR ticker→CIK 보강, 조인 기준) ③alembic 마이그레이션(stock cik PK·ticker_history·daily_bar — db-architect).

## 미해결·주의
- EDGAR 재무층 미구현(M2 직전) — edgartools ~15필드 정규화 정확도 표본검증 필요.
- EODHD 폐지 가격 깊이·배당 정확도 = 가입 후 표본 실측.
- alembic 마이그레이션·`ticker_history` 테이블 미구현(db-architect, S5 선결).
- 6개월 주기 데이터소스 약관·가격 재검증.

## 핵심 파일 인덱스
- 결정: `docs/decisions/ADR-001~003`. 기획: `docs/plans/stock-1st_plan.md`(기준선)·`M1-데이터파이프라인.md`(스펙)·`PLAN_STATUS.md`(현황).
- 리서치: `docs/research/2026-06-16-미국주식-데이터소스.md`. 명세: `docs/apis/tiingo/`(+ 예정 eodhd/).
- 코드: `src/stockpick/{types.py, data/{source,tiingo,storage,pilot}.py}`. 계약 규칙: `.claude/rules/{python-conventions,api-spec-reference,logging-rules}.md`.
- 커밋 흐름: 7d60ab9(M0)→606ba0b(M1 S0-S1)→8e5d136(미장아키)→24b030b(Docker)→2f4d496(계약)→e57b8d6·982574d(Tiingo명세)→61b55c0(어댑터)→0f69a53(저장·파일럿)→096e7f3(키주입)→11fedce(EODHD확정).
