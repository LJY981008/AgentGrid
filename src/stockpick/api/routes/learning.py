"""학습 노트(docs/learning) API — 트리 스캔 + 마크다운 콘텐츠.

- GET /api/learning/tree     docs/learning 디렉토리 재귀 스캔(마크다운만 잎, 디렉토리는 노드)
- GET /api/learning/content?path=...  마크다운 원문 + dir(상대 이미지 URL 재작성 기준)

⚠️ path traversal BLOCKING: content 의 path 는 사용자 입력이다. resolve() 후 learning_dir 의
하위인지 검증하고, 벗어나면 **404**(존재 여부·내부 경로 비노출 — `../../etc/passwd` 류 차단).
심볼릭 링크 우회도 resolve() 가 실제 경로로 펼쳐 막는다. 마크다운(.md)만 허용(임의 파일 읽기 차단).

이미지(112개)는 app.py 가 StaticFiles 로 /learning-assets 에 마운트한다(이 라우터 밖). 프론트는
content.dir + 상대 src 로 `/learning-assets/{dir}/{src}` URL 을 합성한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_learning_dir
from ..models import LearningContent, LearningNode, LearningTree

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/learning")

_MARKDOWN_SUFFIX = ".md"


def _build_tree(directory: Path, root: Path) -> list[LearningNode]:
    """디렉토리 재귀 스캔 → LearningNode 리스트. 마크다운 파일과 하위 디렉토리만 포함(이미지 제외).

    정렬: 이름 오름차순(00.caveats.md 류 숫자 접두사가 자연 정렬돼 트리 최상단에 옴 — 의도된 순서).
    path 는 root(learning_dir) 기준 상대경로(슬래시 구분, POSIX).
    """
    nodes: list[LearningNode] = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        rel = entry.relative_to(root).as_posix()
        if entry.is_dir():
            children = _build_tree(entry, root)
            # 마크다운이 하나도 없는 빈 디렉토리(이미지뿐)는 트리에서 생략(노이즈 제거).
            if children:
                nodes.append(LearningNode(name=entry.name, path=rel, type="dir", children=children))
        elif entry.is_file() and entry.suffix == _MARKDOWN_SUFFIX:
            nodes.append(LearningNode(name=entry.name, path=rel, type="file", children=[]))
    return nodes


@router.get("/tree", response_model=LearningTree)
def learning_tree(learning_dir: Path = Depends(get_learning_dir)) -> LearningTree:
    if not learning_dir.is_dir():
        # 학습 디렉토리 부재(마운트 누락 등)는 명시 기록하되 빈 트리 응답(200 — 프론트 빈 상태).
        logger.warning("학습 디렉토리 없음 — 빈 트리: dir=%s", learning_dir)
        return LearningTree(root=[])
    return LearningTree(root=_build_tree(learning_dir, learning_dir))


def _resolve_within(learning_dir: Path, rel_path: str) -> Path:
    """rel_path 를 learning_dir 하위로 안전 해소. 벗어나면 404(path traversal 차단).

    resolve() 로 `..`·심볼릭 링크를 실제 경로로 펼친 뒤, learning_dir(역시 resolve)의 하위인지
    is_relative_to 로 검증한다. 벗어나면 존재 여부·내부 경로를 노출하지 않고 404.
    """
    base = learning_dir.resolve()
    target = (base / rel_path).resolve()
    if not target.is_relative_to(base):
        logger.warning("learning content 경로 이탈 차단(traversal): path=%s", rel_path)
        raise HTTPException(status_code=404, detail="학습 문서를 찾을 수 없음")
    return target


@router.get("/content", response_model=LearningContent)
def learning_content(
    path: str = Query(..., description="docs/learning 기준 상대경로(.md)"),
    learning_dir: Path = Depends(get_learning_dir),
) -> LearningContent:
    target = _resolve_within(learning_dir, path)

    if target.suffix != _MARKDOWN_SUFFIX or not target.is_file():
        # 마크다운 아님·부재 → 404(임의 파일 읽기 차단, 존재 여부 비노출).
        logger.info("learning content 미존재/비마크다운 — 404: path=%s", path)
        raise HTTPException(status_code=404, detail="학습 문서를 찾을 수 없음")

    base = learning_dir.resolve()
    rel = target.relative_to(base)
    parent_rel = rel.parent.as_posix()
    # 최상위 파일이면 parent 가 "." → 빈 문자열로 정규화(프론트 URL 합성 단순화).
    dir_rel = "" if parent_rel == "." else parent_rel

    content = target.read_text(encoding="utf-8")
    return LearningContent(path=rel.as_posix(), dir=dir_rel, content=content)
