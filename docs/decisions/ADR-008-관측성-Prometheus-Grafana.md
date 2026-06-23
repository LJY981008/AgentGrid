# ADR-008 — 관측성 스택: Prometheus + Grafana + 백테스트 phase/peak 계측

- 상태: 채택 (2026-06-23)
- 맥락: [[2026-06-23-관측성-스택]] · 후속 of [[ADR-007-백테스트-DuckDB-persistent-캐시]]

## 맥락

백테스트 최적화(DuckDB 푸시다운·벤치 멤버십 등)를 반복하는데 측정이 **임시방편**(`time.monotonic()` 수동 타이밍 + `resource.ru_maxrss` 전체 peak)이었다. 그 결과:
- phase별 분해가 없어 병목을 추측에 의존(벤치 멤버십 병목도 수동 분해로 겨우 발견).
- 풀 백테스트 peak **11.7GB 원천 미확정**(Python 객체 vs DuckDB C++ 버퍼) — "추측 금지" 규약인데 정밀 도구 부재.
- 최적화 before/after 진척을 기록·비교할 영속 수단 없음.

사용자 요구: Prometheus+Grafana 모니터링 장착 + 라운드별 Grafana 스냅샷 + tbbe-hub 식 레이어 대시보드.

## 결정

1. **phase 계측은 stdlib `PhaseProfile` dataclass를 `BacktestResult`에 반환**(엔진 `profile:PhaseTimer|None` 키워드·기본 None). prometheus 변환은 상위(profile CLI·api)만 — **모듈경계 BLOCKING**(data/rules/backtest는 api/prometheus 무관). 기본 None이라 **결과불변**(`profile=None`==`PhaseTimer()` bit-identical·회귀 봉인).
2. **배치(25분 백테스트) 메트릭은 격리 CLI(`python -m stockpick.backtest.profile`) + Pushgateway**. pull(scrape)은 단발 배치를 못 잡음(종료 시 프로세스 소멸). app 정지 후 격리 실행(11.7GB+12g OOM 회피·CLAUDE.md 벌크 규약).
3. **peak 메모리 범인 가림 = RSS(ru_maxrss) + tracemalloc(Python 힙) 동시 측정**. `rss_peak ≫ python_peak` 이면 native(DuckDB C++ 버퍼)·비슷하면 Python. tracemalloc/memray는 Python 힙만 보므로 RSS 대조가 1차 귀속(실측 검증: DuckDB 20M행 → tracemalloc 5KB지만 ru_maxrss 0.31GB 점프). 할당 코드 줄은 memray(런북·Prometheus 밖).
4. **라이브 곡선 + 종료 요약 둘 다**: profiler가 `/metrics` 노출(Prometheus scrape→RSS·phase 곡선·peak 시점) + 종료 시 Pushgateway round 요약(before/after 영속).
5. **Grafana 레이어 대시보드**(L1 신호등·L3 파이프라인·L4 무결성·인프라 호스트 = now / L2 외부의존·PG = scaffold) + **네이티브 Local Snapshot**(grafana.db·grafana-data 영속·데이터 동결 before/after).
6. **버전핀(실측)**: `prom/prometheus:v3.12.0`(⚠️ latest=2.x)·`grafana/grafana:13.0.2`·`prom/pushgateway`·`prometheus-fastapi-instrumentator>=8,<9`(starlette 1.3.1 호환)·`prometheus-client`·`memray`(dev).

## 기각된 대안

- **Observer Protocol(ports.py)**: 3 포트 구현체 수정+핫루프 콜백 → 결과불변 검증 부담. dataclass 반환이 기존 `BacktestResult` 계약과 일관·더 단순.
- **라이브 25분 동기 `/api/backtest` scrape**: pull이 단발 배치 못 잡음·uvicorn worker 점유·app 12g와 11.7GB 동시적재 OOM. Pushgateway가 정답.
- **RSS Gauge 상시 수집만**: 순간값이라 peak 못 잡고 **할당 지점도 모름**. tracemalloc peak + RSS 대조 + memray가 상위호환.
- **memray 상시 코드화**: 진단 도구를 상시화 = 과투자. 런북 1회 실행으로 충분.
- **평면 단일 대시보드**: 레이어 분류(tbbe-hub 모델·신호등→drill-down)가 가독·확장 우위.

## 결과

- ⊕ phase별 병목·peak 범인을 데이터로 측정(추측 제거). 최적화 before/after Grafana 스냅샷 누적.
- ⊕ 결과불변·모듈경계 유지(엔진은 stdlib만·prometheus는 상위만).
- ⊖ compose 4서비스·deps 추가(1인 로컬엔 다소 무겁지만 사용자 명시 요구·핵심 레이어부터·과투자 회피).
- ⊖ `meta.validated=false` 불변(관측성=속도/메모리 최적화용·룰 검증 아님).
- 후속: L2 외부의존·PG 대시보드(exporter)·peak 범인 확정 후 메모리 최적화(DuckDB memory_limit or Python).
