---
name: research-delisted-ticker-cik-mapping
description: 폐지종목 ticker→SEC CIK 매핑 판정 — EODHD Fundamentals General.CIK(2018+ 폐지·주경로)·ID-Mapping(추정·라이브필요)·SEC cik-lookup-data.txt(회사명기반·영구) 3경로. 블로커 해소(영구NULL 아님). (2026-06-29)
metadata:
  type: reference
---

2026-06-29 실측. stockpick 다팩터(ROE/PB) 피벗 핵심 블로커: 유니버스 50,106(폐지포함) 중 폐지 ticker→CIK 부재 시 폐지 재무 구조적 NULL. **판정: 해소 가능(c 영구NULL 아님)**. 노트 `docs/research/2026-06-29-폐지종목-CIK-매핑.md`.

**왜 CIK만 있으면 되나**: SEC companyfacts(CIK→재무)는 폐지사도 PIT-correct 반환(EDGAR 영구보존·CIK 재사용X). 막힌 단계는 SEC company_tickers.json=현재활성만 → 폐지 ticker→CIK 한 단계뿐.

**3경로 (우선순위)**:
1. **EODHD Fundamentals `General.CIK`(주경로·가장 확실)**: `/api/v1.1/fundamentals/{T}.US` 응답 General 객체에 CIK,EIN,IsDelisted(bool),Delisted(date) 필드 실재(캡처명세 확정). ROE/PB 받으면 CIK 딸려옴=별도호출 불요. **2018+ 폐지만**(2018이전 폐지=EOD only=fundamentals없음=CIK못얻음).
2. **EODHD ID-Mapping `/api/id-mapping?filter[symbol]=AAPL.US&fmt=json`→data[].cik**(10자리 zero-pad 문자열): 엔드포인트·필드·플랜(Free포함=현구독OK)·1콜 전부 명세 확정. ⚠️**폐지 ticker 커버 여부 명세·공식문서 모두 침묵→라이브 실측 필요**.
3. **SEC `cik-lookup-data.txt`**(www.sec.gov/Archives/edgar/, 13MB): 공식 "historically cumulative for company names, contains entities that no longer file"=폐지·구명 누적 포함. but **회사명→CIK**(ticker 아님)→ticker→명 브리지 필요·fuzzy노이즈. EODHD 의존 끊는 무료영구 백업·교차검증용.

**실질 사각지대**: 2009이전 폐지사(CIK얻어도 SEC XBRL재무 2009~만 부재). CIK매핑문제 아닌 SEC커버리지 한계. 재무 시작점 2009~로 잡으면 무관.

**라이브 샘플(메인 실행·키 .env EODHD_API_KEY 노출금지)**: IsDelisted=true 50개 샘플로 (A)ID-Mapping cik반환율 (B)Fundamentals General.CIK 측정. A≥80%면 ID-Mapping 단독채택. 폐지연도대별 CIK확보율 집계.

**Caveats BLOCKING**: ①EODHD 해지후 1개월 삭제의무→매핑테이블 영구보관 불가나 CIK는 SEC퍼블릭도메인이라 cik-lookup-data.txt로 재현하면 약관회피 ②ticker 재사용(PALM사례)→폐지시점+회사명 동시대조 필수, ticker단독매칭=오염위험 ③fundamentals 10콜추정×50,106 콜예산 확인. 6개월 주기 재확인. 관련 [[research-sec-edgar-free-financials]] [[research-eodhd]].
