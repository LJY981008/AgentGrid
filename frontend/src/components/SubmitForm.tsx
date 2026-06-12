"use client";

import { useState } from "react";
import Link from "next/link";
import { RECEIVED_TOKEN } from "@/lib/mock/submissions";
import type { Category } from "@/lib/mock/types";

const CATEGORIES: Category[] = ["DB 연동", "API 연동", "브라우저 제어", "기타"];

/**
 * 제출 폼 (F1) — 프로토타입: 실제 저장 없이 클라이언트 상태로만 동작.
 * 제출 시 mock 추적 토큰을 발급하고 상태 페이지 링크를 안내한다.
 */
export default function SubmitForm() {
  const [repoUrl, setRepoUrl] = useState("");
  const [email, setEmail] = useState("");
  const [category, setCategory] = useState("");
  const [issuedToken, setIssuedToken] = useState<string | null>(null);

  if (issuedToken) {
    return (
      <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-6 dark:border-emerald-700 dark:bg-emerald-500/10">
        <h2 className="text-lg font-semibold text-emerald-800 dark:text-emerald-300">
          제출이 접수되었습니다
        </h2>
        <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
          아래 추적 토큰으로 분석 진행 상태를 확인할 수 있습니다. 분석이 완료되면
          디렉토리에 등급과 함께 게시됩니다.
        </p>
        <div className="mt-4 rounded-md border border-emerald-200 bg-white px-4 py-3 font-mono text-sm dark:border-emerald-800 dark:bg-zinc-900">
          {issuedToken}
        </div>
        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          <Link
            href={`/submissions/${issuedToken}`}
            className="rounded-md bg-emerald-600 px-4 py-2 font-medium text-white hover:bg-emerald-700"
          >
            상태 추적 페이지로 이동
          </Link>
          <button
            type="button"
            onClick={() => {
              setIssuedToken(null);
              setRepoUrl("");
              setEmail("");
              setCategory("");
            }}
            className="rounded-md border border-zinc-300 px-4 py-2 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            다른 도구 제출
          </button>
        </div>
        <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
          프로토타입 안내: 실제 저장 없이 데모 토큰이 발급됩니다.
        </p>
      </div>
    );
  }

  const inputClass =
    "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm placeholder:text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setIssuedToken(RECEIVED_TOKEN); // mock 발급 — 실제 백엔드 연동 시 POST 응답의 토큰 사용
      }}
      className="space-y-5 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <div>
        <label htmlFor="repoUrl" className="block text-sm font-medium">
          GitHub 저장소 URL <span className="text-red-500">*</span>
        </label>
        <input
          id="repoUrl"
          type="url"
          required
          pattern="https://github\.com/.+/.+"
          title="https://github.com/{owner}/{repo} 형식"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/owner/my-mcp-server"
          className={`mt-1.5 ${inputClass}`}
        />
        <p className="mt-1.5 text-xs text-zinc-500 dark:text-zinc-400">
          공개 저장소만 가능 · TypeScript/Python 외 언어는 분석 불가로 거부됩니다
        </p>
      </div>

      <div>
        <label htmlFor="email" className="block text-sm font-medium">
          연락 이메일 <span className="text-zinc-400">(선택)</span>
        </label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="분석 실패 시 안내받을 주소"
          className={`mt-1.5 ${inputClass}`}
        />
      </div>

      <div>
        <label htmlFor="category" className="block text-sm font-medium">
          카테고리 제안 <span className="text-zinc-400">(선택 — 최종 분류는 운영자 확정)</span>
        </label>
        <select
          id="category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className={`mt-1.5 ${inputClass}`}
        >
          <option value="">선택 안 함</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <button
        type="submit"
        className="w-full rounded-md bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
      >
        분석 요청 제출
      </button>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        제출 후 자동 분석(코드 비실행 정적 분석)을 거쳐 등급과 산출 근거가 공개
        디렉토리에 게시됩니다. IP 당 제출 횟수 제한이 적용될 수 있습니다.
      </p>
    </form>
  );
}
