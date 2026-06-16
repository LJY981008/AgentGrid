---
name: research-eodhd-matlab-connector
description: EODHD MATLAB connector 페이지 실측 — REST명세 아닌 튜토리얼. 레거시 table.csv 엔드(a/b/c/d/e/f/g 날짜파라미터)+서드파티 EODML. http nonsecure 권장
metadata:
  type: reference
---

EODHD `/financial-apis/matlab-api-connector-and-example` 실측 (2026-06-16, r.jina.ai 우회).

- 성격: 신규 REST 엔드포인트 정의 아님 = **MATLAB 통합 튜토리얼**. 기존 EOD 데이터 API를 레거시 `table.csv` 경로로 호출.
- 엔드포인트(레거시): `GET http://nonsecure.eodhd.com/api/table.csv`
  - 쿼리: `s`(심볼 AAPL.US), `api_token`(키, demo=AAPL.US만), `a/b/c`(시작 월/일/연), `d/e/f`(종료 월/일/연), `g`('d' 일간). Yahoo 레거시 스타일 파라미터.
  - 응답: CSV (Date,Open,High,Low,Close,Volume,Adjusted Close)
- ⚠️ HTTPS 아닌 **HTTP + nonsecure.eodhd.com 권장** (MATLAB 리다이렉트 회피).
- EODML: UndocumentedMatlab.com 배포 서드파티 커넥터(EODML.zip). prices/fundamental/earnings 함수 래핑.
- 페이지에 가격플랜·콜소비 명시 없음.
- KRX 한국주식과 무관(완결용). [[research-eodhd]] 본체 참조.
