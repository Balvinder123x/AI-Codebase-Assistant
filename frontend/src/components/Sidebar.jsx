/**
 * Sidebar
 * =======
 * Two tabs:
 *   Files  - the indexed file tree (GET /files), click to open a file
 *   Search - literal keyword search (GET /search), click a hit to jump
 *
 * This is where the "simple backend utilities" from the spec surface in the
 * UI. Note that the LLM is not involved here at all: the user clicks, we
 * fetch, we display. No agent deciding what to open.
 *
 * WHY OFFER KEYWORD SEARCH WHEN WE HAVE SEMANTIC SEARCH?
 * They fail in opposite directions. Semantic search is great at concepts
 * ("how does auth work?") and bad at exact strings - ask it for the constant
 * MAX_RETRIES_v2 and the embedding blurs it into "retry-ish things".
 * Keyword search is the exact reverse. Having both covers both gaps.
 */
import { useState } from "react";

export default function Sidebar({
  files,
  onOpenFile,
  onSearch,
  searchHits,
  isSearching,
  activeFile,
}) {
  const [tab, setTab] = useState("files");
  const [query, setQuery] = useState("");

  function handleSearch() {
    const trimmed = query.trim();
    if (trimmed && !isSearching) onSearch(trimmed);
  }

  return (
    <div className="flex h-full flex-col border-r border-slate-800 bg-slate-900">
      {/* --------------------------------------------------------- tabs -- */}
      <div className="flex border-b border-slate-800">
        {["files", "search"].map((name) => (
          <button
            key={name}
            onClick={() => setTab(name)}
            className={
              "flex-1 px-4 py-2.5 text-xs font-medium capitalize transition " +
              (tab === name
                ? "border-b-2 border-emerald-500 text-emerald-400"
                : "text-slate-500 hover:text-slate-300")
            }
          >
            {name}
            {name === "files" && files.length > 0 && (
              <span className="ml-1.5 text-slate-600">{files.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* -------------------------------------------------------- files -- */}
      {tab === "files" && (
        <div className="flex-1 overflow-y-auto p-2">
          {files.length === 0 ? (
            <p className="p-4 text-center text-xs text-slate-600">
              No repository indexed yet.
            </p>
          ) : (
            files.map((file) => (
              <button
                key={file.path}
                onClick={() => onOpenFile(file.path)}
                title={file.path}
                className={
                  "block w-full truncate rounded px-2 py-1.5 text-left font-mono text-xs transition " +
                  (activeFile === file.path
                    ? "bg-slate-800 text-emerald-400"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200")
                }
              >
                {file.path}
              </button>
            ))
          )}
        </div>
      )}

      {/* ------------------------------------------------------- search -- */}
      {tab === "search" && (
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="border-b border-slate-800 p-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Find exact text..."
              className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 outline-none focus:border-emerald-500"
            />
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            {isSearching && (
              <p className="p-4 text-center text-xs text-slate-600">
                Searching...
              </p>
            )}

            {!isSearching && searchHits.length === 0 && (
              <p className="p-4 text-center text-xs text-slate-600">
                No matches.
              </p>
            )}

            {!isSearching &&
              searchHits.map((hit, index) => (
                <button
                  key={index}
                  onClick={() => onOpenFile(hit.file_path)}
                  className="mb-1 block w-full rounded px-2 py-1.5 text-left transition hover:bg-slate-800"
                >
                  <div className="truncate font-mono text-[10px] text-emerald-500">
                    {hit.file_path}:{hit.line_number}
                  </div>
                  <div className="truncate font-mono text-xs text-slate-400">
                    {hit.line}
                  </div>
                </button>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
