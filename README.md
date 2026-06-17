# stockpick

개인 투자용 **미국 주식(NYSE/NASDAQ/AMEX)** 분석. 과거 데이터로 **정량 룰 Top20** 생성 → **세션 토의로 수동 Top5** → 분산투자 → 추적·보정으로 안정화.

> ⚠️ 디렉토리/리모트 이름은 (구) AgentGrid 유지 — 2026-06-16 MCP 레지스트리에서 도메인 전환(같은 날 한국→미국 2차 전환 [ADR-002](docs/decisions/ADR-002-미국-데이터소스-아키텍처.md)). 기획: [docs/plans/stock-1st_plan.md](docs/plans/stock-1st_plan.md)

## Tech Stack

| 영역 | 스택 |
|---|---|
| 언어 | Python ≥3.12 · uv · ruff · mypy(strict) · pytest · src 레이아웃 |
| 데이터 | 가격 Tiingo(파일럿)→EODHD(M2·폐지 포함) / 재무 SEC EDGAR(filed=PIT)+edgartools |
| 저장 | Parquet+DuckDB(백테스트) · PostgreSQL 18(운영) |
| API(M3) | FastAPI + uvicorn[standard] (`src/stockpick/api/`) |
| 웹앱(M3 — 구현 완료) | PWA (Vite8/React19/react-router7/TS, `webapp/`) |

## Getting Started

```bash
docker compose up -d                                      # 풀스택: postgres + app(FastAPI:8000) + web(Vite:5174)
# 검증은 app 컨테이너에서:
docker compose exec app sh -c 'ruff check src tests && mypy && pytest -q'
```

## 디렉토리

```
src/stockpick/   도메인 계약(types.py) + data(수집·저장)·rules(Top20 랭킹)·backtest(⚠️스텁, M2)·api(FastAPI M3)
tests/           pytest (픽스처·모킹 — 라이브 데이터 의존 금지)
webapp/          PWA 대시보드 (M3 — 구현 완료, Vite8/React19)
docs/            옵시디언 볼트 (기획·ADR·리서치·구현 히스토리)
```

## ⚠️ 원칙 (돈 걸림)

- **백테스트 검증 안 된 룰 신뢰 금지** — 생존편향(폐지종목 포함)·룩어헤드·과적합 회피가 설계 BLOCKING
- LLM(세션 토의)은 정성 보정·리스크 플래그용 — 정량 룰이 본체
- 실패 명확 보고 — 조용히 깨진 데이터 저장 금지
