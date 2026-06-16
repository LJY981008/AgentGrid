---
name: research-tiingo-api
description: Tiingo REST API 공통 규약 실측 — 인증(Token 헤더 또는 ?token=)·base_url·rate limit·포맷·약관 (2026-06-16)
metadata:
  type: reference
---

Tiingo API 공통 규약 ([[research-us-free-data-sources]] 보강). 출처: tiingo.com/documentation/general/overview + /connecting (JS SPA — WebFetch 직접 불가, r.jina.ai 렌더링 경유로 verbatim 확보). 2026-06-16 실측.

- base_url: `https://api.tiingo.com`
- 인증 2가지 (택1): ① URL 쿼리 `?token=YOURTOKEN` ② 헤더 `Authorization: Token YOURTOKEN` (앞에 문자열 "Token " 접두사 필수 — Bearer 아님)
- 연결 테스트 엔드포인트: `GET https://api.tiingo.com/api/test/` → `{"message":"You successfully sent a request"}`
- 포맷: `format` 쿼리 파라미터 = `json`(기본, 메타데이터 포함) | `csv`(JSON보다 4~5배 빠름). 엔드포인트별 지원 포맷은 각 문서 상단 표기.
- rate limit: 시간당/일일(자정 EST 리셋)/월 대역폭(매월 1일 자정 EST 리셋) 기준. 분·초 단위 제한 없음. 구체 수치는 pricing 페이지(문서엔 미기재).
- 플랜: Basic/Power/Commercial. 전부 가입은 무료(All accounts are free), 상위 플랜은 한도 상향.
- 약관(BLOCKING): Basic/Power = 내부·개인용만, 재배포 금지. Commercial = 내부 상업용, 재배포는 별도 라이선스(sales@tiingo.com). → stockpick 개인용은 OK.
- 심볼 체계: 클래스 구분에 점(.) 아닌 대시(-) 사용. 예 BRK-A, SPG-P-J. 전체 티커: apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip (매일 갱신).
- 웹소켓: wss://api.tiingo.com/{service}, authToken을 eventData에 실어 subscribe. messageType A/U/D/I/E/H, 30초 HeartBeat.
- overview 페이지 자체엔 데이터 엔드포인트 없음 — 사이드바로 분기(daily/iex/fx/news 등 별도 페이지).
- 함정: 문서가 SPA라 WebFetch가 <title>만 반환 → 렌더 프록시 필요. WebSearch 요약은 패러프레이즈라 verbatim 근거로 불가.
