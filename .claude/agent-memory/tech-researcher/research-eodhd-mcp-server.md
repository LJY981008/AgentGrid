---
name: research-eodhd-mcp-server
description: EODHD MCP Server 페이지 실측 — REST 명세 아닌 MCP 서버 개요. 엔드포인트=MCP URL, 77툴, stdio/SSE/http, OAuth/apikey
metadata:
  type: reference
---

EODHD "MCP Server for Financial Data" 페이지(https://eodhd.com/financial-apis/mcp-server-for-financial-data-by-eodhd) 실측 (2026-06-16, r.jina.ai 렌더 프록시 경유 — SPA 라 WebFetch 직접은 빈 본문).

**핵심: 이 페이지는 REST API 명세가 아니라 MCP 서버 개요/설정 페이지다.** 명시적 REST 엔드포인트(HTTP method, path/query 파라미터, 응답 스키마)는 없음. 77개 read-only 툴이 각 EODHD REST API 문서 페이지로 링크만 됨.

- 원격 서버 URL: v1 `https://mcpv2.eodhd.dev/v1/mcp?apikey=YOUR_API_KEY` (API키 쿼리), v2 `https://mcpv2.eodhd.dev/v2/mcp` (OAuth 2.1 빌트인 서버)
- 전송: streamable-http(기본), SSE, stdio(Claude Desktop/Claude Code)
- 77 read-only 툴 (EODHD 본 데이터셋 + UnicornBay 마켓플레이스 + 서드파티). 예: resolve_ticker, get_historical_stock_prices, get_live_price_data, get_technical_indicators, get_support_resistance_levels
- 프롬프트 템플릿 3종: analyze_stock(ticker), compare_stocks(t1,t2), market_overview(exchange)
- 문서 100+ 페이지를 MCP 리소스로 임베드 → 엔드포인트 조회에 API 콜 미소비
- 무료 플랜은 "limited data" — 정확한 필요 구독 티어는 페이지 미명시
- 오픈소스, Python 3.10–3.13 CI, 197 자동 테스트. PyPI 패키지명/pip 명령은 페이지 미기재
- stockpick(한국주식) 관점: KRX 커버리지나 MCP 의 한국 데이터 가용성 언급 없음. 실제 데이터는 각 REST API 약관/커버리지 따름(기존 EODHD 리서치 참조)

관련: [[research-eodhd]] (가격 데이터 본체), [[research-eodhd-splits-dividends]] 등 EODHD 시리즈
