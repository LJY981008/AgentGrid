/**
 * 학습 토픽 트리 — /api/learning/tree 응답(재귀 노드)을 렌더. 파일 클릭 시 선택 콜백.
 *
 * 00.caveats(생존편향·룩어헤드 주의)를 최상단에 정렬해 노출(서버 트리에서도 이름순이면 00.* 이
 * 먼저 오지만, 방어적으로 한 번 더 정렬). 디렉토리는 펼친 상태로 단순 표시(1인용 — 접기 생략).
 */

import type { LearningNode } from "../../api/types";

/** 디렉토리 먼저·이름순(00.caveats 등 숫자 프리픽스가 자연 정렬되어 최상단). */
function sortNodes(nodes: LearningNode[]): LearningNode[] {
  return [...nodes].sort((a, b) => {
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

function NodeView({
  node,
  activePath,
  onSelect,
}: {
  node: LearningNode;
  activePath: string | null;
  onSelect: (path: string) => void;
}) {
  if (node.type === "dir") {
    return (
      <li>
        <div className="node-dir">{node.name}</div>
        <ul>
          {sortNodes(node.children).map((c) => (
            <NodeView key={c.path} node={c} activePath={activePath} onSelect={onSelect} />
          ))}
        </ul>
      </li>
    );
  }
  // 파일 — .md 표시명에서 확장자 제거(가독성).
  const label = node.name.replace(/\.md$/i, "");
  return (
    <li>
      <button
        className={`node-file${node.path === activePath ? " active" : ""}`}
        onClick={() => onSelect(node.path)}
      >
        {label}
      </button>
    </li>
  );
}

export function TopicTree({
  root,
  activePath,
  onSelect,
}: {
  root: LearningNode[];
  activePath: string | null;
  onSelect: (path: string) => void;
}) {
  return (
    <nav className="topic-tree card" aria-label="학습 목차">
      <ul>
        {sortNodes(root).map((n) => (
          <NodeView key={n.path} node={n} activePath={activePath} onSelect={onSelect} />
        ))}
      </ul>
    </nav>
  );
}
