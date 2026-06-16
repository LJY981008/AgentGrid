---
name: research-tiingo-news-api
description: Tiingo News API REST 명세 실측 — 엔드포인트/파라미터/인증/응답필드/기관전용 bulk (2026-06-16)
metadata:
  type: project
---

Tiingo News API (https://www.tiingo.com/documentation/news) 실측 결과.

**Why:** 미국주식 무료/유료 데이터소스 리서치([[research-us-free-data-sources]]) 후속 — 뉴스 API 명세를 코드 환각 없이 참조하기 위함.

**How to apply:** Tiingo 뉴스 연동/스크래핑 코드 작성 시 아래 사실 사용. 단 응답 필드는 공식 페이지에서 직접 못 읽음(JS 렌더, WebFetch 불가) — 공식 Python 클라이언트(hydrosquall/tiingo-python api.py) + readthedocs 미러에서 교차검증한 것.

핵심 사실:
- base_url: `https://api.tiingo.com`, auth = HTTP 헤더 `Authorization: Token <APIKEY>` (헤더 방식, ?token= 도 일반적으로 허용되나 클라는 헤더 사용). 응답 기본 JSON.
- GET `/tiingo/news` — params: tickers, tags, sources(쉼표결합, 클라 내부키 `source`), startDate, endDate(YYYY-MM-DD), limit(기본100·최대1000), offset(기본0), sortBy(`publishedDate`|`crawlDate`, 기본 publishedDate 내림차순), onlyWithTickers(bool, 기본 false).
- 응답 article 필드: id, title, url, description, publishedDate, crawlDate, source, tickers[], tags[].
- GET `/tiingo/news/bulk_download` (+`/{file_id}`) — **기관 클라이언트 전용**. file_id 없으면 사용가능 file_id 배열, 있으면 다운로드 URL+메타데이터.
- 함정: 공식 docs 페이지는 SPA(JS)라 WebFetch로 본문 추출 불가 — 명세는 클라 소스/미러 기반. 무료티어 뉴스 접근 가능 여부·rate limit 은 페이지에서 직접 확인 못함(미확인).
