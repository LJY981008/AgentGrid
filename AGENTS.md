# AGENTS.md

Codex/Gemini 등 코딩 에이전트용 진입 문서.

> ⚠️ **얇은 포인터 정책**: 규칙 본문 복제 금지. 원본 우선.
> ⚠️ 2026-06-16 도메인 전환: **stockpick(개인 투자용 미국 주식(NYSE/NASDAQ/AMEX) 분석, Python)** (같은 날 한국→미국 2차 전환 ADR-002). 구 MCP 레지스트리 컨텍스트 폐기.

## 필수 참조

| 내용 | 원본 |
|---|---|
| 역할·원칙·절차·구조 | [CLAUDE.md](CLAUDE.md) |
| Python 컨벤션 | [.claude/rules/python-conventions.md](.claude/rules/python-conventions.md) |
| 로깅 | [.claude/rules/logging-rules.md](.claude/rules/logging-rules.md) |
| 웹앱(PWA, M3 — 구현 완료) | [.claude/rules/webapp-conventions.md](.claude/rules/webapp-conventions.md) |
| 기획 현황 | [docs/plans/PLAN_STATUS.md](docs/plans/PLAN_STATUS.md) |

## 최소 불변 규칙 (훅 없는 에이전트도 준수)

- 한국어 소통·커밋. 커밋 태그: `feat|fix|refactor|docs|test|chore|perf`
- **금융 BLOCKING**: 생존편향(폐지종목 포함)·룩어헤드(≤t 데이터)·수정주가 통일·백테스트 검증 전 룰 신뢰 금지
- 모듈 경계: data/rules/backtest — 하위는 상위 import 금지. 실패 명확 보고(조용한 결측 금지)
- 검증: `ruff check src tests && mypy && PYTHONPATH=src pytest -q`. push 는 사용자 요청 시(기본 브랜치 main)
