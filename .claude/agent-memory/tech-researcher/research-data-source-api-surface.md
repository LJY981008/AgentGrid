---
name: research-data-source-api-surface
description: 한국주식 데이터소스 3종(FDR/pykrx/KRX OpenAPI) 실제 API 표면·수정주가·생존편향 실측 (2026-06-16). M1 파이프라인용.
metadata:
  type: reference
---

2026-06-16 실측. 버전: FinanceDataReader 0.9.202(2026-05-13), pykrx 1.2.8(2026-05-04). 상세 리서치는 [[project-domain-pivot]] 의 데이터소스 문서 보강.

**핵심 BLOCKING 트레이드오프 (생존편향 vs 수정주가)** — pykrx issue #89 (github.com/sharebook-kr/pykrx/issues/89):
- 네이버 소스 = 수정종가 O, **폐지종목 X** (생존편향)
- KRX 소스 = 수정종가 X, **폐지종목 O**
- → "수정주가 + 폐지종목" 동시 제공 단일 무료 소스 없음. FDR `KRX-DELISTING`(폐지 리스트) + 별도 가격 결합 필요.

**재현성(룩어헤드 인접) 함정**: pykrx `get_market_ohlcv(adjusted=True)` 수정주가는 "최근 영업일 기준" 으로 동적 변동 → 같은 과거일도 조회 시점마다 값이 달라짐. 백테스트는 적재 시점 고정 스냅샷 필수.

**KRX OpenAPI 약관 실측** (openapi.krx.co.kr): 비상업 전용·재배포 금지·일 10,000건 제한·출처표기·12개월 미사용 키 삭제. base `http://data-dbg.krx.co.kr/svc/apis/{모듈}/{tr}`, 헤더 `AUTH_KEY`, 파라미터 `basDd`(YYYYMMDD), 응답 JSON OutBlock. 커버리지 2010-01-04~. 개인투자용은 비상업이라 적합.

**미확인(재검증 필요)**: KRX OpenAPI 분당/초당 rate limit(일 한도만 확정), wikidocs(403)·FDR docs 의 수정주가 명문 정의. 6개월 주기 재검증.
