---
name: research-tiingo-corporate-actions
description: Tiingo corporate-actions splits+dividends(=distributions) API 실측 — 엔드포인트·필드·인증·beta/EOD entitlement 게이팅. JS렌더 페이지는 r.jina.ai 프록시로 읽어야 함
metadata:
  type: reference
---

Tiingo 공식 문서(www.tiingo.com/documentation/*)는 JS 렌더 SPA — WebFetch 직접은 title만 반환됨. `https://r.jina.ai/<url>` 프록시 경유해야 본문 추출됨. (2026-06-16 실측)

base_url 공통: `https://api.tiingo.com`, 경로 `/tiingo/corporate-actions/...`. 인증 페이지엔 "you will need your token" 만 (헤더 vs ?token= 미명시 — connecting 문서 기준 둘 다 가능 추정).

## corporate-actions/splits (2026-06-16)
- 엔드포인트 2개 (GET):
  - `/tiingo/corporate-actions/splits` — query `exDate`(옵션). 미지정 시 당일 ex-date
  - `/tiingo/corporate-actions/{ticker}/splits` — path `ticker`, query `startExDate`(옵션)
- 응답: permaTicker, ticker, exDate, splitFrom, splitTo, splitFactor(=splitTo/splitFrom), splitStatus("a"=active/"c"=cancelled)

## corporate-actions/dividends 페이지 (2026-06-16) — 실제는 "distributions" 엔드포인트
⚠️ 페이지 제목은 dividends 지만 본문 경로/필드는 전부 "distributions". dividends 라는 경로는 없음.
- 엔드포인트 3개 (GET 추정, 메서드 미명시):
  - `/tiingo/corporate-actions/distributions` — query `exDate`(datetime, 옵션). 미지정 시 당일 ex-date. 예: `?exDate=2023-08-25`
  - `/tiingo/corporate-actions/{ticker}/distributions` — path ticker; query `startExDate`,`endExDate`(둘다 옵션). 미지정 시 전체 이력. 예: `?startExDate=2023-01-01&endExDate=2024-01-01`
  - `/tiingo/corporate-actions/{ticker}/distribution-yield` — 배당수익률 시계열
- distributions 응답 필드: permaTicker(str), ticker(str), exDate(dt), paymentDate(dt), recordDate(dt), declarationDate(dt), distribution(float), distributionFreqency(str, 오타 그대로)
- distribution-yield 응답: date(dt), trailingDiv1Y(str=이전 1년 배당수익률)
- distributionFreqency 코드: w=Weekly, bm=Bimonthly, m=Monthly, tm=Trimesterly, q=Quarterly, sa=Semiannually, a=Annually, ir=Irregular, f=Final, u=Unspecified, c=Cancelled
- 갱신: 하루 2~3회 (배당 공시 들어오는 대로)
- caveat: exDate·distribution 은 절대 null 아님, 나머지 필드는 데이터 소스 가용성 따라 null 가능

## 공통 게이팅 (splits/dividends 동일)
- beta + enterprise 조기 릴리스. EOD endpoint entitlement 보유 고객 포함. 변경일자 2023-08-28 언급
- 페이지에 응답 포맷(JSON/CSV) 명시 없음·rate limit 명시 없음·무료/유료 가격 명시 없음
- 신규 접근은 support@tiingo.com
