# stockpick

개인 투자용 한국 주식(코스피/코스닥) 분석. 과거 **30년 데이터로 정량 룰 Top20** 생성 → **세션 토의로 수동 Top5** → 분산투자 → 추적·보정으로 안정화.

> ⚠️ 디렉토리/리모트 이름은 (구) AgentGrid 유지 — 2026-06-16 MCP 레지스트리에서 도메인 전환. 기획: [docs/plans/stock-1st_plan.md](docs/plans/stock-1st_plan.md)

## Tech Stack

| 영역 | 스택 |
|---|---|
| 언어 | Python ≥3.12 · uv · ruff · mypy(strict) · pytest · src 레이아웃 |
| 데이터 | 벌크 30년=FinanceDataReader+pykrx / 일일=KRX OpenAPI(공식) / 검증=KIS |
| 저장 | Parquet+DuckDB(백테스트) · PostgreSQL 18(운영) |
| 웹앱(M4) | PWA / 반응형 웹 (대시보드) |

## Getting Started

```bash
docker compose up -d                                      # PostgreSQL
# uv sync   (M1 의존성 추가 후)
ruff check src tests && mypy && PYTHONPATH=src pytest -q   # 검증
```

## 디렉토리

```
src/stockpick/   도메인 계약(types.py) + data(수집·저장)·rules(Top20 랭킹)·backtest(검증)
tests/           pytest (픽스처·모킹 — 라이브 데이터 의존 금지)
webapp/          PWA 대시보드 (M4)
docs/            옵시디언 볼트 (기획·ADR·리서치·구현 히스토리)
```

## ⚠️ 원칙 (돈 걸림)

- **백테스트 검증 안 된 룰 신뢰 금지** — 생존편향(폐지종목 포함)·룩어헤드·과적합 회피가 설계 BLOCKING
- LLM(세션 토의)은 정성 보정·리스크 플래그용 — 정량 룰이 본체
- 실패 명확 보고 — 조용히 깨진 데이터 저장 금지
