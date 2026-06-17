---
name: impl-rules-momentum
description: rules 모듈 첫 구현(M2 수직 슬라이스) — 모멘텀 팩터→랭킹. 룩어헤드 2중 가드·수정주가·동점 처리 패턴
metadata:
  type: project
---

# rules 모듈 첫 구현 — 모멘텀 팩터 → Top 랭킹 (2026-06-17, M2 수직 슬라이스)

`src/stockpick/rules/` 첫 구현. data 에 이어 두 번째 도메인 모듈. 골격 입증용 프로토타입.

**Why:** 무료 1년치 EODHD 데이터셋(9종목·251 거래일)으로 "수집→팩터→랭킹→TopEntry" 수직 슬라이스
입증. 팩터·룩백·가중치는 후보일 뿐 최종은 M2 백테스트가 결정(§4.1 과적합 경고).

**How to apply (재사용 패턴):**
- **스캔(I/O)과 팩터(계산) 분리**: `_scan.py`(DuckDB Parquet 읽기)와 `factors.py`(순수 함수)를
  나눴다. factors 가 순수 함수라 합성 `PricePoint` 로 정확값 단위 테스트(라이브 0 정책 충족).
  DuckDB I/O 단위테스트는 라이브 의존이라 범위 밖 → qa-tester 가 데모 라이브로 실동작 확인.
- **룩어헤드 2중 방어선**: _scan 이 SQL `WHERE trade_date<=as_of` 1차, factors 가 메모리에서
  `p.trade_date<=as_of` 2차. 둘 다 둔다(데이터 경계+계산 경계). 후속 팩터도 이 패턴 따를 것.
- **수정주가 = close×adj_factor 합성을 _scan 에서**: 하류(factors)는 adjusted 만 본다(raw·factor
  노출 안 함). 모멘텀은 adjusted 비율로만(raw 는 배당·분할 왜곡 — JNJ 등 배당주 차이 큼).
- **내부 Decimal, TopEntry 경계서 float**: TopEntry.score/factors=float 계약이라 경계 변환. 계산은
  Decimal(정밀도 BLOCKING).
- **동점 = competition ranking(1,1,3) + ticker 2차키**: 진짜 동점 노출 + 결정적 순서(재현성).
- **cik="" (EODHD 미제공)**: 추측 금지, 후속 EDGAR 매핑. ticker 로 식별.

**룩어헤드 sabotage 검증(필수 습관):** 룩어헤드 안전성 테스트가 공허하지 않은지 확인하려면 factors
의 as_of 필터를 일시 제거 → 테스트가 FAIL(0.2→82.325 미래누설) 하는지 본다. 복원 후 PASS. 금융
BLOCKING 회귀 봉인은 sabotage 로 증명해야 신뢰.

**⚠️ 데이터셋이 컨테이너에만 존재**(호스트 미마운트): `data/parquet` 는 app 컨테이너 안에만 있다.
호스트에서 `find data/parquet` 는 빈 결과 → 데모·검증 모두 `docker compose exec -T app` 으로.
소스는 마운트됨(호스트 편집 → 컨테이너 즉시 반영).

**ruff E501 한글 함정:** 한글 주석/docstring 은 ruff 가 폭 100 초과를 자주 잡는다(한글 1자=폭 2 체감).
한글 줄은 짧게 끊어 쓸 것 — 첫 검증에서 14건 E501 났다(전부 한글 주석).

진입점: `python -m stockpick.rules`(__main__.py→demo.main). 룩백 126·skip 21·top_n 5 후보값.
관련: [[impl-eodhd-adapter]](데이터 소스), [[gotcha-adj-factor-direction]](adjusted 정의).
