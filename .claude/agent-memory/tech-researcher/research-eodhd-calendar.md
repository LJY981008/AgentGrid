---
name: research-eodhd-calendar
description: EODHD Calendar API 실측 — /api/calendar/{earnings,trends,ipos,splits,dividends} 5엔드. earnings/splits/ipos는 from/to+symbols, dividends만 filter[]+page[] JSON:API식. 데이터 IPO/Split는 2015-01~, splits 필드=old_shares/new_shares(ratio 아님). All-In-One/Fundamentals 플랜, 1콜/요청. KRX 무관 (2026-06-16).
metadata:
  type: reference
---

2026-06-16 실측(r.jina.ai 프록시 경유, 2회 교차검증). base_url=https://eodhd.com/api/calendar/, auth=?api_token=. format json/csv(trends·dividends는 json only).

**5 엔드포인트**: /earnings · /trends(earnings trends) · /ipos · /splits · /dividends

**파라미터 패턴 2종**:
- earnings/ipos/splits: from/to(YYYY-MM-DD, 미지정시 today~today+7d) + symbols(콤마, 설정시 from/to 무시) + fmt
- dividends: JSON:API식 — filter[symbol]/filter[date_eq](둘 중 하나 필수)·filter[date_from]/filter[date_to]·page[limit](1~1000,기본1000)·page[offset]. 응답에 meta/data/links.next 페이지네이션

**필드 함정**:
- splits 응답 = code/split_date/optionable(Y/N)/old_shares/new_shares — "4:1 ratio" 문자열 아님(직접 비율 필드 없음). Corporate Actions Splits/Dividends API와 별개
- earnings 응답 top-level에 symbols 필드 없음(type/description/from/to/earnings만). 레코드=code/report_date/date(fiscal end)/before_after_market/currency/actual/estimate/difference/percent
- trends 응답 = trends가 심볼별 배열의 배열, 값들이 stringified 숫자

**데이터 커버리지**: IPOs 2015-01~ +2-3주 미래 / Splits 2015-01~ +수개월 미래. (가격전용 EOD 메모 [[research-eodhd]]의 폐지 2000~과 별개 데이터셋 — calendar는 2015 시작, 30년 백테스트 부적합)

**플랜/콜**: All-In-One·Fundamentals Data Feed·"Corporate Events Calendar & News Feed" 상품에 포함(EOD All World엔 없음 추정). 1콜/요청.

**stockpick 관련성**: KRX(코스피/코스닥) 미언급, 예시 전부 US/PA(유럽). 한국 주식 earnings/ipo/split 캘린더로는 부적합 가능성 — 우리 도메인엔 직접 활용도 낮음. KRX 커버리지 미확인.
