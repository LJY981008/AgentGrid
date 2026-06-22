# 2026-06-22 S5-c 후처리 버그 수정 + S5-d 실 UniversePort (MasterUniverse)

- **유형**: 플랜모드 승인
- **관련 기획/이슈**: S5(다년·전체유니버스) 4분해 마지막(S5-d) + **풀백필 완주 후 발견한 S5-c 후처리 버그 수정**(선행). [[2026-06-18-S5c-벌크가격]] 후속·[[decisions/ADR-006-PG스키마-alembic-첫실사용]]. S6 신뢰성 게이트·`validated=true` 의 선결.
- **시작 시점 커밋**: `fc6edfd` → **완료 커밋**: (완료 시 기입, Task5 마지막)

## 의도/목적 — 왜 이 작업을 하나

S5-c 가 종목마스터 50,184(폐지 포함) 대상 다년 EOD 를 Parquet 에 적재(풀백필 완주·5.1G). S5-d 는 그 마스터의 listed_at/delisted_at 기반 **`MasterUniverse`(시점별 거래가능 집합·폐지 청산)로 백테스트 유니버스를 교체**(G7) — 현 골격 `PriceDerivedUniverse`(가격 존재로 도출·미래상장 미배제·폐지 항상 None)의 생존편향/룩어헤드 갭 해소. 이게 S6 게이트(validated=true)의 선결.

**그러나 풀백필 완주 검증 중 S5-c 후처리 버그 발견** — 체크포인트 50,184 done인데 PG `stock` 날짜가 29개만 backfill. 원인 = run_bulk 후처리에서 `verify_parquet`(≥400s·미완)이 `update_stock_dates`·commit 을 막음. MasterUniverse 는 stock 날짜에 의존하므로 **이 버그 수정이 S5-d 직접 선결** → 두 작업을 한 플랜으로 통합. ⚠️ S5-d 자체는 `meta.validated=false` 불변(정확한 유니버스 제공이지 룰 검증 아님 — validated=true 는 S6 후).

## 계획 (승인 플랜 백업)

**전문**: `.claude/plans/pro-3-5-twinkling-adleman.md` (승인본).

**핵심 5 Task**(Task별 구현→리뷰 2종[convention-reviewer + code-reviewer]→게이트→커밋, 누적 일괄 금지):
1. work-history 백업(이 문서).
2. `db.export_stock_snapshot(conn, base_dir)` — stock→`stock_snapshot.json`(`{generated_at, stocks:[...]}`·dates ISO·None→null·atomic temp→replace·conn 재사용).
3. `MasterUniverse`(adapters) + `_select_universe` — 스냅샷 읽어 시점 멤버십·폐지 청산. `_select_universe` 스냅샷 유무 분기(폴백 PriceDerivedUniverse).
4. bulk 후처리 재구조화 + `--finalize` + 배선(demo·api).
5. 복구 실행(`--finalize`로 날짜 backfill) + 라이브 검증 + 문서 + 이 문서 After.

**critic 검증 반영**(REVISE 2C+3M 전부 선반영):
- C1(BLOCKING): `conn.commit()` 은 run_bulk/finalize **코어에 넣지 않고 호출부(main/CLI)** 가 소유 — 코어에 commit 넣으면 test rollback 격리(TRUNCATE→yield→rollback) 깨져 **라이브 PG 마스터 파괴**. export 는 같은 conn read-your-own-writes(중간 commit 불요). 테스트는 코어 함수 구동(main 아님).
- C2: `--finalize` 멱등은 `listing_status`·Parquet 불변 시. active→delisted 전환은 S6 reconciliation 범위.
- M1: verify 옵션화(`--verify`·기본 off) 시 summary `verify_passed` 키 계약 변경 → `test_bulk.py:192` 단언 갱신.
- M2: 복구 게이트는 `count(listed_at) == len(load_trade_date_bounds)`(Parquet-파생) — 50,184 하드코딩 금지(price-less 종목 NULL 정상).
- M3: 무결성 verify 1회 = **S6 진입 필수 게이트**("권장" 아님) — 옵션화로 빠진 무결성(중복·음수가격·OHLC위반·부분쓰기)을 S6 전 1회 강제.
- delisted_at+1 경계변환의 주말 엣지 = half-open 구간이라 정상(critic 확인).

**핵심 계약 — `delisted_at` 경계 변환(BLOCKING)**: 프로덕션 `delisted_at`=마지막 실거래일(추정)인데 engine/Fake/Protocol 은 경계를 "첫 거래불가일"로 해석 → MasterUniverse 가 로드 시 `delisted_at + 1day` 로 변환해야 마지막 실봉 안 잃고 경계 정확(engine/ports/fakes/benchmark 불변·변환은 어댑터 내부에만).

## Before — 수행 전 실측 (HEAD `fc6edfd`)

- **Parquet daily_bar**: `list_dataset_tickers` = **50,184 ticker**(5.1G)·`load_trade_date_bounds` = **50,184 정상 반환**(WDC 1978~2026 등). 데이터 완전.
- **PG `stock`**: TOTAL 50,184(active 18,316·delisted 31,868)인데 **listed_at 채워진 행 29개**(active 14·delisted 15·이전 `--limit 20` 스모크 잔재)·delisted_at 15개. → 본런 `update_stock_dates` 미반영.
- **verify_parquet 진단**: 50,184·5.1G 직접 실행 시 **≥400초 미완**(timeout 143). run_bulk 후처리(verify→update→commit)에서 verify 가 update·commit 을 막은 유력 원인(정확 죽음원은 `--rm` 컨테이너라 미확정).
- 체크포인트 `bulk_checkpoint.jsonl` = 50,184 done(failed/empty 0).
- `run_bulk`(bulk.py): 후처리 `verify_parquet → update_stock_dates → (main)commit`. `verify_parquet`(storage.py:398-461)·`load_trade_date_bounds`(557-582)·`update_stock_dates`(db.py:133-158). `PriceDerivedUniverse`·`_select_universe` 없음(adapters.py). 테스트 fixture = 트랜잭션 TRUNCATE→rollback 격리(test_bulk.py:130-142·test_db.py).
- compose `app.mem_limit:12g`(이전 OOM 방어·41b0e6f). alembic head=0003(S5-d 마이그레이션 0).

## After — 수행 후 실측 (완료 시 기입)

- 검증 결과:
- 변경 규모:
- 커밋:

## 비교/회고

- 의도 대비 달성도:
- 계획과 달라진 것 + 이유:
- 후속 작업: [ ] S6 신뢰성 게이트(+무결성 verify 1회·full_series 경량화) [ ] full_series 구조 수정(OOM 근본) [ ] 증분 스케줄러
