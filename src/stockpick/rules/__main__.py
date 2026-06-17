"""`python -m stockpick.rules` 진입 — 데모(스캔→모멘텀→랭킹→Top 출력)를 실행한다.

실제 로직은 demo.main 에 있다(이 파일은 모듈 실행 진입점만). 종료코드를 그대로 전파한다.
"""

from __future__ import annotations

from .demo import main

raise SystemExit(main())
