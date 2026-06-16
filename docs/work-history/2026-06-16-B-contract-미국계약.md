# 2026-06-16 B-contract — 미국 도메인 계약 재설계

- **유형**: 일반 구현
- **관련 기획/이슈**: [[plans/M1-데이터파이프라인]] §3 스키마 / [[decisions/ADR-002-미국-데이터소스-아키텍처]] / B 단계(계약)
- **시작 시점 커밋**: `24b030b` → **완료 커밋**: `<미커밋 — 사용자 요청 시>`

## 의도/목적 — 왜 이 작업을 하나

2026-06-16 한국주식 → 미국주식 전환(ADR-002). 도메인 계약 `types.py` 가 한국용
(Market KOSPI/KOSDAQ, Stock.code 6자리)으로 남아 있어 미국 데이터층(B-pipeline)·DB
스키마(db-architect)가 진행 불가. 이 작업으로 **CIK(안정 식별자)+ticker(가격 키·시변)**
모델을 계약에 봉인하고, 가격 소스 교체(Tiingo→Sharadar)를 위한 `DataSource` 어댑터
Protocol 을 추가해 B-pipeline 의 구현 기준선을 확정한다.

## 계획 (개요)

1. `types.py`: `Market`→`Exchange`(StrEnum, 미 거래소). `Stock` cik+ticker+exchange,
   `delisted_at` 보존. `DailyBar`/`TopEntry` code→ticker, TopEntry 는 cik 앵커. Financial
   은 범위 제외(주석으로 PIT 설계 유효성만 명시).
2. `data/source.py`: `DataSource` typing.Protocol — 유니버스(폐지 포함)·일봉 조회. stdlib only.
3. `tests/test_contract.py`: 새 계약 + Protocol 런타임 스모크.
4. M1 §3 스키마 문서: cik+ticker 구조 + ticker_history(재사용 대응) 갱신.
5. 검증: 컨테이너에서 ruff(UP042 포함)+format+mypy(strict)+pytest 전부 통과.

## Before — 수행 전 실측

- `types.py`: `Market(str, Enum)` KOSPI/KOSDAQ, `Stock.code`(6자리), `DailyBar.code`,
  `TopEntry.code`+market. 4 dataclass, Financial 없음.
- `tests/test_contract.py`: 4 테스트(market enum/stock delisted/top entry/daily bar).
- `src/stockpick/data/`: `__init__.py` 만(스텁), source.py 없음.
- 컨테이너 검증 baseline: 기존 통과(전환 전 한국 계약 기준).

## After — 수행 후 실측

- 컨테이너 검증(정본 환경) — 전부 통과:
  ```
  docker compose exec -T app sh -c 'ruff check src tests && ruff format --check src tests && mypy && pytest -q'
  All checks passed!            # ruff (UP042 포함)
  7 files already formatted     # ruff format --check
  Success: no issues found in 7 source files   # mypy --strict
  .....                         # pytest 5 passed
  ```
  - 1차 시도서 `tests/test_contract.py:44` E501(103>100) 1건 → 도크스트링 단축 후 통과(실측 교정).
- 변경 규모(`git diff --stat`, source.py 신규 제외):
  ```
  docs/plans/M1-데이터파이프라인.md |  18 ++--
  src/stockpick/types.py           |  77 ++++++++++----
  tests/test_contract.py           | 115 +++++++++++++++------
  3 files changed, 150 insertions(+), 60 deletions(-)
  + src/stockpick/data/source.py (신규)
  ```
- 커밋: 미커밋(작업 지시 = 파일 작성·컨테이너 검증만, 커밋은 사용자 요청 시).

## 비교/회고

- 의도 대비 달성도: 계약 4타입 미국화 + DataSource Protocol + 테스트 5건 + M1 §3 문서 갱신
  완료. 컨테이너 검증(UP042 포함) 전부 통과.
- 계획과 달라진 것: TopEntry 에 cik 만이 아니라 ticker·exchange 동반(as_of 가독성·가격 조인).
  M1 §3 은 7→8테이블(`ticker_history` 신설)로 확장 — ticker 재사용/심볼 변경의 PIT 조인
  해소 키가 스키마에 없으면 생존편향 누수라 BLOCKING 으로 명시.
- 금융 BLOCKING 보존: 생존편향=delisted_at nullable + iter_universe include_delisted=True 기본,
  ticker 재사용 누수=cik 앵커 + ticker_history, 룩어헤드=fetch_daily_bars 구간필터·financial
  disclosed_at<=t 주석 유지.
- 후속 작업:
  - [ ] B-pipeline: Tiingo 어댑터로 `DataSource` 구체 구현(HTTP·rate-limit·체크포인트)
  - [ ] db-architect: §3 stock(cik PK)·ticker_history·daily_bar(ticker PK) alembic 마이그레이션
  - [ ] Financial 타입 코드화(EDGAR 재무층 착수 시, M2 직전)
