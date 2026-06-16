---
name: research-eodhd-live-v2-quotes
description: EODHD Live v2 US stocks extended quotes (/api/us-quote-delayed) REST 명세 실측 — 지연 호가·50+필드·미국전용
metadata:
  type: reference
---

EODHD Live (delayed) v2 for US stocks extended quotes 실측 (2026-06-16, r.jina.ai 경유).
source: https://eodhd.com/financial-apis/live-v2-for-us-stocks-extended-quotes-2025

- 단일 엔드포인트: GET https://eodhd.com/api/us-quote-delayed
- 인증 ?api_token=, DEMO 키로 소수 티커(AAPL.US/TSLA.US/VTI.US/AMZN.US/BTC-USD.CC/EURUSD.FOREX) 테스트 가능
- 파라미터: s(필수, 콤마구분 멀티심볼), page[limit](max 100), page[offset], fmt(json/csv)
- 응답: meta.count + data{심볼키} + links.next(페이지네이션). 심볼당 50+필드(가격/bid-ask/52주/마켓캡/pe/배당 등)
- 콜 소비: 티커당 1콜
- 플랜: All-In-One / EOD All World / EOD+Intraday All World Extended / Free
- ⚠️ 지연 분 수 페이지에 미명시("delayed exchange-compliant"). 실시간 호가/체결은 stockpick(한국 주식 EOD 백테스트) 도메인과 무관 — 미국 전용·인트라데이 스냅샷이므로 직접 사용 안 함. 관련: [[research-eodhd]]
