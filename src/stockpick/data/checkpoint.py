"""재개(resume) 체크포인트 — 처리 단위 상태 추적 JSONL(벌크 가격·재무 백필 공유 leaf).

`{item: 'done'|'empty'|'failed'}` 를 append-only JSONL 로 보존한다. 진입점(bulk 가격·edgar 재무)이
재개 시 done/empty 를 skip(failed·미기록은 재시도)해 **중복0·누락0**을 보장한다.

⚠️ 모듈 경계: stdlib 만 의존하는 leaf — `data` 의 어느 모듈도 안전하게 import(순환 없음). 원래
`bulk` 내부에 있었으나 재무 백필(`edgar`)도 재사용해야 하는데 edgar→bulk→universe→edgar 순환이
생겨 여기로 추출했다(bulk 는 re-export 유지).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_SKIP_STATUSES = frozenset({"done", "empty"})  # 재개 시 skip(failed 는 재시도)


class Checkpoint:
    """item 처리 상태 {item: 'done'|'empty'|'failed'} — JSONL append(O(1)). 재개 진실원천.

    append-only 라인(`item\\tstatus`) — 같은 item 재기록 시 마지막 라인 우선(load 가 순차 덮음).
    크래시 시 마지막 라인 부분기록 가능 → load 가 형식불량 라인 skip(보수적·재시도 회복).
    item = ticker(가격 벌크) 또는 cik(재무 백필) — 진입점이 키 의미를 정한다.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._status: dict[str, str] = {}

    @classmethod
    def load(cls, path: Path) -> Checkpoint:
        cp = cls(path)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                parts = line.split("\t")
                if len(parts) == 2 and parts[0]:
                    cp._status[parts[0]] = parts[1]  # 마지막 기록 우선
        return cp

    def mark(self, item: str, status: str) -> None:
        """⚠️ 적재(write) 완료 **후에만** 호출(write→체크포인트 순서 — 부분적재 재개 회복)."""
        self._status[item] = status
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"{item}\t{status}\n")

    def should_skip(self, item: str) -> bool:
        """done/empty 면 skip(재개). failed/미기록 은 (재)처리 대상."""
        return self._status.get(item, "") in _SKIP_STATUSES

    def counts(self) -> dict[str, int]:
        """상태별 집계 {done, empty, failed} — 진행/요약 보고용."""
        tally = {"done": 0, "empty": 0, "failed": 0}
        for status in self._status.values():
            if status in tally:
                tally[status] += 1
        return tally
