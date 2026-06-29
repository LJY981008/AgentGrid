# 설계 — 다팩터 피벗 Sub-project A: 재무 데이터 PIT 파운데이션

- 날짜: 2026-06-29
- 상태: 설계(브레인스토밍 산출·미승인)
- 맥락: 공식 신뢰성 게이트(2000~2026·10fold) 완주 → momentum 단일팩터 decile = **깨끗한 측정에서 진짜 무알파**(validated=false·R-2 PASS·폭발 0). plan §4.1 "깨끗한 측정 후 fail → 다팩터 결합 피벗 정당" 도달.
- 근거: 다관점 설계 워크플로우(4 렌즈 + 적대 비판·만장일치 survivorship_safe=FALSE) + 사용자 결정(폐지재무 실측 먼저·PIT 브리지 먼저·ROE-only 하드필터) + [[../../research/2026-06-29-폐지종목-CIK-매핑]].

## 1. 문제 — 왜 데이터 파운데이션이 선결인가

다팩터(momentum + 재무 ROE/P/B) 결합의 병목은 **결합법이 아니라 재무 데이터**다. 실측:

- **커버리지 ≈ 0** — financials.json = 단 9 cik(파일럿). 리밸시점 ROE 산출가능 종목: 2015=7·2020=8·2024=8 / 멤버 ~22,000 → **0.03%**. 재무 팩터가 영향 줄 종목이 2만 중 8개 = 무의미.
- **ticker→cik 비-PIT(BLOCKING)** — `EdgarSnapshotResolver.cik_for(ticker, on=t)` 의 시점 `on` 무시(`data/universe.py:41 _SNAPSHOT_FLOOR=date(1900,1,1)` 단일 스냅샷). 결과: (a) 폐지사 cik 미해소 → 침묵 탈락 → 재무 차원 생존자-틸트, (b) ticker 재사용 시 과거 회사 가격에 현재 cik 재무 오조인 = **룩어헤드 엔티티 누설**.
- **소스 한계** — 재무 = SEC EDGAR companyfacts(유일·EODHD 구독엔 fundamentals 없음). XBRL 의무화 ~2009 → pre-2009 structured 재무 부재. ETF/ADR/외국주/SPAC = SEC common-stock 미신고 → 영구 NULL.

즉 어떤 결합 룰도 이 데이터 위에선 측정 불가(garbage-in). **생존편향-안전 + PIT-correct 재무 데이터 확보가 다팩터의 전제**다.

## 2. 범위

- **이번 스펙(Sub-project A)**: 재무 데이터를 생존편향-안전·PIT-correct 하게 확보·저장·시점조회 가능케 하는 데이터 파운데이션. 끝나면 "임의 시점 t·임의 유니버스 종목의 ROE/P/B 를 PIT(disclosed_at≤t)·올바른 엔티티로 얻는다"가 성립.
- **범위 밖(Sub-project B·별도 스펙)**: ROE 결합 룰(방식 C 하드필터)·신규 G-5c 재무커버리지 게이트·pre-registration·게이트 실행·validated 판정. A 완료 + 커버리지 실측 후 착수.
- **범위 밖(영구)**: 가중치 데이터 튜닝(과적합)·EODHD fundamentals(구독 외)·재무 팩터를 가격 유니버스 멤버십 결정에 사용(생존편향).

## 3. 컴포넌트 (각 단일 책임·독립 테스트 가능)

### A1 — 폐지 ticker→cik 복구 (`data/cik_mapping.py` 신규)
- **책임**: 유니버스의 폐지 ticker 에 대한 SEC CIK 매핑 산출(현재 신고사는 기존 `company_tickers.json` 으로 충분).
- **입력**: MasterUniverse 의 폐지 ticker 목록 + 폐지일(`delisted_at`).
- **출력**: `{ticker: (cik, delisted_date)}` — ticker 재사용 구분용 폐지일 동반.
- **경로(우선순위·실측 게이트)**:
  1. **EODHD ID-Mapping**(`GET /api/id-mapping?filter[symbol]={T}.US&api_token=…&fmt=json` → `data[].cik`). **50 폐지샘플 라이브 실측**으로 커버율 측정 — **≥80% 면 ID-Mapping 단독 채택**, 미달이면 ↓.
  2. **SEC `cik-lookup-data.txt`**(회사명→cik·폐지/구명 누적·퍼블릭도메인·영구) fallback. EODHD delisted 리스트의 회사명으로 매칭, **폐지일+회사명 동시 대조**(ticker 단독 금지·SEC PALM 경고·룩어헤드 가드).
- **검증**: 알려진 폐지사(예 ENRON·LEH) ticker→cik 정확 매핑·ticker 재사용 케이스서 폐지일로 올바른 cik 선택.

### A2 — PIT ticker_history (S5-d·`data/universe.py` 확장 + `data/edgar.py` resolver 교체)
- **책임**: `cik_for(ticker, on=t)` 가 **시점 t 에 유효한 cik** 반환(현 단일 스냅샷 제거).
- **데이터**: `(ticker, cik, valid_from, valid_to)` 행집합. 현재신고사 = `(ticker, cik, listed_at, None)`. 폐지(A1) = `(ticker, cik, listed_at, delisted_at)`. ticker 재사용 = 비중첩 구간 다행.
- **조회**: `valid_from ≤ t AND (valid_to IS NULL OR t < valid_to)` 인 행의 cik. 다중매칭(데이터오류)=명시 실패(조용한 추측 금지).
- **인터페이스**: 기존 `IdentityResolver` Protocol(`cik_for(ticker, *, on)`) 구현 교체 — engine/api 는 DI 라 코드 0 변경(`backtest/identity.py` 주석대로). 신규 `PitIdentityResolver`.
- **저장**: ticker_history 테이블(~50k 행·소규모). PG(alembic·기존 `_snapshot_ticker_history` 자리) 또는 Parquet. **결정 필요(§6)**.
- **검증**: ticker 재사용 합성 케이스(T=cik1[2000~2010]·cik2[2015~])서 `cik_for(T, 2008)=cik1`·`cik_for(T, 2018)=cik2`·`cik_for(T, 2012)=""`(공백구간). 룩어헤드 sabotage(미래 재할당이 과거 조회 불변).

### A3 — SEC companyfacts 백필 (`data/edgar.py` 확장·격리 실행)
- **책임**: 해소된 전 cik(현재+폐지)의 companyfacts 수집 → ROE/P/B 산출용 PIT 재무 저장(현 9 → 만 단위).
- **수집**: SEC `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`·3 concept(StockholdersEquity·NetIncomeLoss·EntityCommonStockSharesOutstanding)·User-Agent=`EDGAR_IDENTITY`·~10req/s·**2009+ 만**(XBRL).
- **견고성(BLOCKING)**: **cik 단위 증분 저장 + resume**(현 `fetch_dataset_financials` all-or-nothing 메모리누적 → 만 cik 전손 위험). 체크포인트(완료 cik 기록)·재시작 시 스킵. 격리 컨테이너(상주 app 과 메모리 경쟁 회피·CLAUDE.md 벌크 규약).
- **저장**: 현 `edgar/financials.json`(list) → **만 단위는 Parquet `financial_facts` 데이터셋**(cik·concept·value·disclosed_at·period_end·fiscal_period·form). 백테스트는 DuckDB 스캔(daily_bar 동형·`:memory:` memory_limit 캡 패턴 재사용). `rules/_financials.load_financial_facts` 가 Parquet 읽도록 교체(JSON 폴백 유지 가능).
- **PIT**: `disclosed_at=filed`(공시일·`end` 아님·룩어헤드 차단). `latest_as_of(disclosed_at≤t)` 재사용. NetIncomeLoss 연간만(fp='FY') 필터(분기 혼재 주의).
- **검증**: 알려진 cik(AAPL) ROE 값 SEC 공시와 대조·resume(중단 후 재개 시 중복 0·누락 0)·PIT(미래 공시 미포함).

### A4 — 커버리지 재측정 (probe·`scripts` 또는 진단)
- **책임**: A1~A3 후 실제 결합 가능 수준 정량 확정 — fold별 (cik해소 ∧ facts ∧ ROE산출) 종목 비율.
- **출력**: 리밸시점별 커버율 + 결측 사유 분류(폐지-매핑부재 / pre-2009-XBRL / 비신고사-ETF/ADR / 신고사-미수집). MAR vs MNAR 진단(결측이 무작위인지 폐지/소형 집중인지).
- **판정**: Sub-project B 의 G-5c 재무커버리지 임계 설계 입력. 커버율이 결합을 정직하게 지지하는지(특히 OOS fold top-decile 후보 중 재무평가 비율) 확정.

## 4. 데이터 흐름

```
MasterUniverse(폐지 포함 유니버스)
   │ 폐지 ticker + delisted_at
   ▼
[A1] cik_mapping ── EODHD ID-Mapping(≥80%?) → / SEC cik-lookup-data.txt(fallback·명+폐지일)
   │ {ticker:(cik,delisted_date)}        현재신고사: company_tickers.json
   ▼
[A2] ticker_history (ticker,cik,valid_from,valid_to) ── PitIdentityResolver.cik_for(ticker,on=t)
   │ 해소 cik 집합(현재+폐지)
   ▼
[A3] SEC companyfacts 백필(2009+·증분resume) → Parquet financial_facts
   │
   ▼
[A4] coverage probe → 결합 가능성 판정 → (Sub-project B 입력)
```
백테스트 시점 조회: `cik=PitIdentityResolver.cik_for(ticker, on=t)` → `facts=load_financial_facts(t)` → `financial_factors(facts, ciks, as_of=t, price_by_cik)` → ROE/P/B (전부 PIT·filed≤t).

## 5. 가드 (BLOCKING)

- **생존편향**: 유니버스 멤버십은 가격기반 MasterUniverse 단일 출처 — 재무 유무가 백테스트 포함 여부를 **절대** 안 바꿈. 재무 NULL = 팩터 결측(B 에서 명시제외+카운트), 행 제외 아님.
- **룩어헤드**: (a) `disclosed_at=filed≤t` PIT. (b) `cik_for(on=t)` 시점 유효 cik 만(ticker 재사용 미래 재할당 차단). (c) A3 백필은 과거 공시만(미래 데이터 주입 0).
- **엔티티 정합**: ticker 재사용 = 폐지일+회사명 대조(잘못된 cik=데이터 오염).
- **모듈 경계**: 전부 `data` 층(rules/backtest 가 의존). data 는 상위(api) import 금지.
- **재현성**: 수집 `source`·`ingested_at` 기록. 결과 결정성.
- **약관**: EODHD 매핑은 해지 후 삭제 의무 → CIK(SEC 퍼블릭도메인)는 `cik-lookup-data.txt` 로 재현/교차검증해 영구 보관 회피.

## 6. 미해결 결정 (구현 전·사용자/스펙리뷰)

1. **저장소**: ticker_history + financial_facts 를 PG(alembic·운영서빙) vs Parquet(백테스트 스캔). 백테스트 핫패스(cik_for per 리밸·facts per 리밸)는 Parquet/DuckDB 가 자연스러우나, 운영 서빙은 PG. → **권장: financial_facts=Parquet(daily_bar 동형·백테스트 주소비자)·ticker_history=Parquet(소규모·resolver 로드)**. PG 동기는 후속.
2. **A1 실측 우선순위**: EODHD ID-Mapping 50샘플을 A2/A3 전에 단독 선행(폐지 cik 가능성 확정 후 진행) vs 병렬. → **권장: 선행**(폐지 cik 결과가 A2 ticker_history 범위 결정).
3. **백필 규모/시간**: 해소 cik 만 단위 × 10req/s + companyfacts JSON 대용량 → 수 시간. 격리·resume 필수. 1차를 현재신고사만(빠른 커버)→폐지 추가(2차)로 단계화할지.

## 7. 테스트 전략

- **A1**: 합성/알려진 폐지사 매핑(픽스처·라이브 0)·ticker 재사용 폐지일 구분. EODHD/SEC 응답 모킹.
- **A2**: ticker_history 시점조회 단위테스트(경계·공백·재사용·다중매칭 실패)·룩어헤드 sabotage(미래 재할당 불변).
- **A3**: companyfacts 파싱(픽스처·PIT filed 필터·fp=FY)·resume(중단/재개 중복0·누락0)·Parquet 저장 라운드트립.
- **A4**: probe 결정성. 전체 ruff/mypy/pytest green·`.claude/hooks/tests/run.sh`.

## 8. 리스크

- 폐지사 cik 커버 < 기대(ID-Mapping/SEC 모두 한계) → 폐지 재무 부분 NULL 잔존 → B 의 G-5c 가 정직 노출.
- 백필 만 cik 시간·SEC rate limit(10req/s)·일부 cik companyfacts 없음(정상).
- pre-2009 inert 는 데이터 문제 아니라 SEC 한계 — B 가 inert 폴드 분리집계로 처리.
- ticker_history 데이터 품질(listed/delisted 날짜 정확도)이 PIT 정합 좌우.
- 결합해도 무알파일 현실적 가능성(B 단계·정직 fail 수용) — A 는 측정 가능성만 보장, 알파 보장 아님.
