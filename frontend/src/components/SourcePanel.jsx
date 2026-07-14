/**
 * SourcePanel
 * ===========
 * The right-hand panel. Two modes:
 *
 *   "sources" - the code chunks that were retrieved to answer the last
 *               question, each with its similarity score
 *   "file"    - the full contents of a file the user clicked in the sidebar
 *
 * WHY THIS PANEL IS THE MOST IMPORTANT PART OF THE DEMO
 * -----------------------------------------------------
 * Anyone can wire an LLM to a text box. What makes this a RAG system - and
 * what an interviewer will actually care about - is that the answer is
 * GROUNDED and you can PROVE it.
 *
 * Showing the retrieved chunks turns the LLM from a black box into
 * something auditable. The user can see exactly which 5 pieces of code the
 * model was looking at. If the answer is wrong, you can immediately tell
 * WHY: was it bad retrieval (wrong chunks fetched) or bad generation (right
 * chunks, model misread them)? Without this panel you cannot debug that
 * distinction at all.
 *
 * That single diagnostic - "retrieval failure vs generation failure" - is
 * the most common RAG interview question there is.
 */
export default function SourcePanel({
  sources,
  fileContent,
  activeFile,
  onClose,
}) {
  const showingFile = Boolean(fileContent);

  return (
    <div className="flex h-full flex-col border-l border-slate-800 bg-slate-900">
      {/* ------------------------------------------------------- header -- */}
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
        <h2 className="truncate text-xs font-medium text-slate-300">
          {showingFile ? (
            <span className="font-mono text-emerald-400">{activeFile}</span>
          ) : (
            <>
              Retrieved Sources
              {sources.length > 0 && (
                <span className="ml-1.5 text-slate-600">{sources.length}</span>
              )}
            </>
          )}
        </h2>

        {showingFile && (
          <button
            onClick={onClose}
            className="ml-2 whitespace-nowrap text-xs text-slate-500 transition hover:text-slate-300"
          >
            ✕ Close
          </button>
        )}
      </div>

      {/* ------------------------------------------------------ content -- */}
      <div className="flex-1 overflow-y-auto">
        {/* Mode 1: viewing a file the user clicked */}
        {showingFile && (
          <pre className="overflow-x-auto p-4 font-mono text-xs leading-relaxed text-slate-300">
            <code>{fileContent}</code>
          </pre>
        )}

        {/* Mode 2: showing the chunks used to answer the last question */}
        {!showingFile && sources.length === 0 && (
          <div className="flex h-full items-center justify-center p-6 text-center">
            <p className="text-xs text-slate-600">
              Ask a question and the code chunks used to answer it will appear
              here.
            </p>
          </div>
        )}

        {!showingFile &&
          sources.map((source, index) => (
            <div key={index} className="border-b border-slate-800 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="truncate font-mono text-[11px] text-emerald-400">
                  {source.file_path}
                </span>

                {/* The similarity score. Higher = the embedding of this chunk
                    was closer to the embedding of the question. Surfacing it
                    makes retrieval quality visible instead of magic. */}
                <span
                  className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400"
                  title="Cosine similarity to the question (higher is better)"
                >
                  {source.score.toFixed(3)}
                </span>
              </div>

              <pre className="max-h-56 overflow-auto rounded bg-slate-950 p-2.5 font-mono text-[11px] leading-relaxed text-slate-400">
                <code>{source.text}</code>
              </pre>
            </div>
          ))}
      </div>
    </div>
  );
}
