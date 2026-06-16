---
name: research-us-free-data-sources
description: 미국주식 무료/초저가 데이터소스 5종(yfinance/Alpaca/Tiingo/Alpha Vantage/Stooq) 실측 — 무료 한도·생존편향·재현성 한계 (2026-06-16). 미국주식 전환 파일럿용.
metadata:
  type: reference
---

2026-06-16 실측. stockpick이 미국주식 주력으로 전환, '무료 파일럿($0)→필요시 유료' 방침. 현재 상장 10~15종목 수집→저장→검증 파일럿엔 무료로 충분, 단 본격 30년 백테스트엔 무료 소스 부적합(아래 BLOCKING). 한국주식 소스는 [[research-data-source-api-surface]].

**파일럿($0) 권장**: yfinance(빠른 시작·재무 일부) 또는 Tiingo(EOD 안정·약관 명확·일1000콜). 둘 다 무료로 10~15종목 충분.

**미국 무료 소스 공통 BLOCKING(본격 백테스트 부적합 이유)**:
1. **생존편향**: yfinance·Tiingo·Alpha Vantage·Stooq 모두 *현재 상장 심볼 기준 조회* — 폐지 심볼은 티커 재사용/제거로 과거 가격 유실 빈번. 무료 소스 중 '폐지종목 리스트+가격'을 survivorship-bias-free로 광고하는 곳 없음(QuantRocket: 미국은 10년 전으로 가면 당시 거래종목의 75%가 빠짐). → 본격 백테스트는 유료 CRSP/Sharadar/QuantConnect/Norgate 필요.
2. **재현성(동적 수정주가)**: yfinance auto_adjust 수정종가는 최신 배당/분할 기준으로 매 조회 재계산 → 같은 과거일도 시점마다 값 변동. 2026년 yf.download의 auto_adjust 기본값 False→True 변경으로 기존 스크립트 깨짐. 백테스트는 적재시점 raw+adj 스냅샷 고정 필수(auto_adjust=False로 둘 다 받아 동결).

**소스별 무료 한도(2026 실측)**:
- yfinance: 무료·비공식(Yahoo v8 chart 엔드포인트). rate limit 비공식·차단 빈번, history 수십년이나 종목별 편차. 2026년 Yahoo가 일부 history를 premium 제한 시도 정황 → 안정성 보장 못 함. ToS상 개인 비상업만, 재배포 불가.
- Alpaca: 무료=IEX(미국 거래량 ~2.5%만, EOD 종가 편향 가능). SIP(100% 통합) = Algo Trader Plus $99/월. 무료도 15분 지연 넘는 historical은 모든 피드 접근 가능하나 무료는 IEX 한정. history ~7년. 공식 SDK(alpaca-py).
- Tiingo: 무료 50req/h·1000req/day·500 unique symbol/month. EOD 수십년, 미국 65000+ 종목. fundamentals는 유료 add-on(무료는 5년). Power $30/월. 약관 명확(공식).
- Alpha Vantage: 무료 25req/day·5req/min(과거 500→100→25로 축소) — 파일럿도 빡빡. TIME_SERIES_DAILY_ADJUSTED 무료 제공(수정종가). Premium $49.99/월~(75rpm).
- Stooq: 무료 벌크 다운로드(미국 포함). 수정종가만(미수정 별도 없음). rate limit 공식 미명시, 비공식.

**미확인**: Alpaca 무료 IEX historical 정확한 시작연도, Tiingo 무료 폐지종목 포함 여부 명문, Alpha Vantage 개인 재배포 약관 세부. 6개월 재검증.
