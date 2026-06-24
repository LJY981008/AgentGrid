---
name: duckdb-native-peak-analysis
description: 백테스트 12.8GB native peak 정적분석 — DuckDB window CTE 물질화·load_range fetchall·verify_parquet 동시연결 가설 (2026-06-24)
metadata:
  type: project
---

S6-b 게이트 백테스트 1회 peak ~12.8GB(rss_peak) ≫ python_peak 0.36GB ≫ DuckDB memory_limit 6GB cap. 즉 native(C++) 할당이 cap 밖. 정적 코드 분석으로 좁힌 후보(측정은 게이트 완주 후 memray --native 필요).

**Why:** validated=true 의 선결 = 게이트 완주인데 12g OOM·18g 프리즈로 못 돈다. native 출처 규명이 mem<12g 의 전제.

**How to apply:** 게이트 완주 후 memray --native·구간별 RSS 로 아래 가설 검증. 수정은 결과불변(bit-identical)·룩어헤드/생존편향 불변 필수.

핵심 코드 근거:
- `momentum_endpoints` SQL(duckdb_cache.py:160-166): WHERE(18k tradable × window 324캘린더일≈220거래일) = 220만~390만행을 `w` CTE 물질화 후 ROW_NUMBER/COUNT window. window sort 버퍼는 cap 안이나 spill 미동작 시 ballooning.
- 벤치 `load_range`(benchmark.py:80): members 18k × 보유구간 → fetchall result chunk native 변환. 2026-06-22 실측 3.65M PricePoint·+2.6GB/리밸(window 경로). 보유경로는 ~38만/리밸.
- 연결 재사용(adapters.py:124): 단일 con 으로 수백 리밸 × (momentum_endpoints+load_range) fetchall 반복 — malloc arena 미반환 누적 의심.
- 게이트 곱: walk_forward 10폴드×3비용 + verify_parquet(별도 :memory: 연결·storage.py:434) 게이트 첫 단계 5.1G 스캔.
- threads 미설정(전 connect): DuckDB 기본=코어수 스레드, 스레드별 native morsel/버퍼 — cap 과 별개로 RSS 증폭.

연결: [[m1-storage-schema]] [[s5a-pg-schema-design]]
