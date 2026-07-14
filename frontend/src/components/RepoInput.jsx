/**
 * RepoInput
 * =========
 * The URL bar. Takes a GitHub URL and triggers POST /index.
 *
 * This is a CONTROLLED COMPONENT: React state is the single source of
 * truth for the input's value, and every keystroke flows through setUrl.
 * The DOM never holds state that React doesn't know about.
 */
import { useState } from "react";

export default function RepoInput({ onIndex, isIndexing, indexedRepo }) {
  const [url, setUrl] = useState("https://github.com/psf/requests");

  function handleSubmit() {
    const trimmed = url.trim();
    if (trimmed && !isIndexing) onIndex(trimmed);
  }

  return (
    <div className="border-b border-slate-800 bg-slate-900 px-6 py-4">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2 whitespace-nowrap">
          <span className="text-lg">🤖</span>
          <h1 className="text-base font-semibold text-slate-100">
            AI Codebase Assistant
          </h1>
        </div>

        <div className="flex flex-1 gap-2">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            // Enter should submit. Users expect this and get annoyed when
            // they have to reach for the mouse.
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="https://github.com/owner/repo"
            disabled={isIndexing}
            className="flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-emerald-500 disabled:opacity-50"
          />
          <button
            onClick={handleSubmit}
            disabled={isIndexing || !url.trim()}
            className="whitespace-nowrap rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isIndexing ? "Indexing..." : "Index Repo"}
          </button>
        </div>

        {indexedRepo && !isIndexing && (
          <span className="whitespace-nowrap rounded-full bg-emerald-950 px-3 py-1 text-xs text-emerald-400">
            ● {indexedRepo}
          </span>
        )}
      </div>
    </div>
  );
}
