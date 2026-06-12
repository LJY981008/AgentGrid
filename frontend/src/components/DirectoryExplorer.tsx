"use client";

import { useMemo, useState } from "react";
import ToolCard from "@/components/ToolCard";
import { GRADE_RANK, type Category, type Grade, type Tool } from "@/lib/mock/types";

const GRADES: Grade[] = ["A", "B", "C", "D", "F"];
const CATEGORIES: Category[] = ["DB 연동", "API 연동", "브라우저 제어", "기타"];
type SortKey = "latest" | "grade";

/**
 * 디렉토리 인터랙션 영역 (F3) — 검색/필터/정렬만 클라이언트 상태.
 * 목록 데이터는 서버 컴포넌트(page.tsx)에서 props 로 전달받는다.
 */
export default function DirectoryExplorer({ tools }: { tools: Tool[] }) {
  const [keyword, setKeyword] = useState("");
  const [grade, setGrade] = useState<Grade | "전체">("전체");
  const [category, setCategory] = useState<Category | "전체">("전체");
  const [sort, setSort] = useState<SortKey>("latest");

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return tools
      .filter((t) => {
        if (kw && !`${t.name} ${t.description}`.toLowerCase().includes(kw)) return false;
        if (grade !== "전체" && t.grade !== grade) return false;
        if (category !== "전체" && t.category !== category) return false;
        return true;
      })
      .sort((a, b) => {
        if (sort === "grade") {
          const byGrade = GRADE_RANK[a.grade] - GRADE_RANK[b.grade];
          return byGrade !== 0 ? byGrade : b.finalScore - a.finalScore;
        }
        return b.analyzedAt.localeCompare(a.analyzedAt); // 최신 분석순
      });
  }, [tools, keyword, grade, category, sort]);

  const selectClass =
    "rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="이름·설명 키워드 검색"
          className="w-full max-w-xs rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm placeholder:text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900"
        />
        <select
          aria-label="등급 필터"
          value={grade}
          onChange={(e) => setGrade(e.target.value as Grade | "전체")}
          className={selectClass}
        >
          <option value="전체">등급: 전체</option>
          {GRADES.map((g) => (
            <option key={g} value={g}>
              등급: {g}
            </option>
          ))}
        </select>
        <select
          aria-label="카테고리 필터"
          value={category}
          onChange={(e) => setCategory(e.target.value as Category | "전체")}
          className={selectClass}
        >
          <option value="전체">카테고리: 전체</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          aria-label="정렬"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className={selectClass}
        >
          <option value="latest">최신 분석순</option>
          <option value="grade">등급순</option>
        </select>
        <span className="ml-auto text-sm text-zinc-500 dark:text-zinc-400">
          {filtered.length}개 / 전체 {tools.length}개
        </span>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-lg border border-dashed border-zinc-300 p-10 text-center text-sm text-zinc-500 dark:border-zinc-700">
          조건에 맞는 도구가 없습니다. 검색어나 필터를 조정해 보세요.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((tool) => (
            <ToolCard key={tool.slug} tool={tool} />
          ))}
        </div>
      )}
    </div>
  );
}
