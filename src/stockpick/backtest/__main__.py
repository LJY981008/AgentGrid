"""`python -m stockpick.backtest` 진입점 — 골격 백테스트 데모 실행.

base_dir 는 STOCKPICK_DATA_DIR(없으면 data/parquet). 데모 본체는 demo.run_demo.
"""

from __future__ import annotations

import os
from pathlib import Path

from .demo import run_demo

raise SystemExit(run_demo(Path(os.environ.get("STOCKPICK_DATA_DIR", "data/parquet"))))
