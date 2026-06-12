# Agent Grid

AI 에이전트 & MCP 서버의 **시스템 신뢰성을 검증·평가**하는 개발자 중심 레지스트리 플랫폼.

단순 큐레이션을 넘어 예외 처리·타임아웃·재시도·서킷 브레이커·멱등성 등 아키텍처 안정성을 정적 분석해 등급(A~F)으로 제공한다.

> 기획: [docs/plans/1st_plan.md](docs/plans/1st_plan.md)

## Tech Stack

| 영역 | 스택 |
|---|---|
| Backend | Java 21 · Spring Boot 4.1 · JPA · Flyway |
| Frontend | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind 4 |
| Infra | PostgreSQL 18 · Redis 8 · RabbitMQ 4.3 |
| Pattern | Transactional Outbox · 비동기 스크래핑/헬스체크 파이프라인 |

## Getting Started

```bash
# 1. 로컬 인프라
docker compose up -d

# 2. 백엔드 (:8080)
cd backend && ./gradlew bootRun

# 3. 프론트엔드 (:3000)
cd frontend && npm install && npm run dev
```

## 디렉토리

```
backend/    Spring Boot API + 비동기 파이프라인
frontend/   Next.js 공개 디렉토리/검색 UI
docs/       기획(plans) · 아키텍처 결정 기록(decisions)
.claude/    Claude Code 하네스 (hooks·rules·skills·agents)
```
