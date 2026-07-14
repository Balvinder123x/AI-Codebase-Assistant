/**
 * ChatBox
 * =======
 * The conversation view. Renders the message list and the input box.
 *
 * DESIGN NOTE: this component is "dumb" (presentational). It holds no
 * conversation state of its own - the messages array lives in App.jsx and
 * is passed down as a prop.
 *
 * Why? Because the Sources panel ALSO needs to know about the latest
 * answer's sources. If ChatBox owned the messages, SourcePanel could not
 * see them. So the state is "lifted up" to the nearest common parent (App),
 * which is the standard React answer to "two siblings need the same data".
 */
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import Loader from "./Loader";

export default function ChatBox({ messages, onAsk, isAsking, repoName }) {
  const [question, setQuestion] = useState("");
  const bottomRef = useRef(null);

  // Auto-scroll to the newest message whenever the list grows.
  // useRef gives us a handle on a real DOM node without re-rendering.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isAsking]);

  function handleSubmit() {
    const trimmed = question.trim();
    if (!trimmed || isAsking || !repoName) return;
    onAsk(trimmed);
    setQuestion("");
  }

  const EXAMPLES = [
    "What does this repository do?",
    "Explain the overall architecture.",
    "How is error handling implemented?",
  ];

  return (
    <div className="flex h-full flex-col">
      {/* ---------------------------------------------------- messages -- */}
      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {messages.length === 0 && !isAsking && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-3 text-4xl">💬</div>
            <p className="mb-1 text-sm text-slate-400">
              {repoName
                ? `Ask anything about "${repoName}"`
                : "Index a repository to get started"}
            </p>

            {repoName && (
              <div className="mt-4 flex flex-col gap-2">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    onClick={() => onAsk(example)}
                    className="rounded-md border border-slate-800 px-3 py-1.5 text-xs text-slate-400 transition hover:border-slate-600 hover:text-slate-200"
                  >
                    {example}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((message, index) => (
          <div
            key={index}
            className={
              message.role === "user" ? "flex justify-end" : "flex justify-start"
            }
          >
            <div
              className={
                message.role === "user"
                  ? "max-w-[80%] rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white"
                  : "max-w-[90%] rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-200"
              }
            >
              {message.role === "user" ? (
                message.content
              ) : (
                // The LLM replies in markdown (headings, bullet lists, fenced
                // code). Rendering it as plain text would show literal ```
                // backticks, so we parse it properly.
                <div className="prose-sm max-w-none">
                  <ReactMarkdown
                    components={{
                      code: ({ inline, children }) =>
                        inline ? (
                          <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs text-emerald-300">
                            {children}
                          </code>
                        ) : (
                          <pre className="my-2 overflow-x-auto rounded-md bg-slate-950 p-3">
                            <code className="font-mono text-xs text-emerald-300">
                              {children}
                            </code>
                          </pre>
                        ),
                      p: ({ children }) => (
                        <p className="mb-2 last:mb-0">{children}</p>
                      ),
                      ul: ({ children }) => (
                        <ul className="mb-2 list-disc space-y-1 pl-5">
                          {children}
                        </ul>
                      ),
                      ol: ({ children }) => (
                        <ol className="mb-2 list-decimal space-y-1 pl-5">
                          {children}
                        </ol>
                      ),
                      strong: ({ children }) => (
                        <strong className="font-semibold text-slate-100">
                          {children}
                        </strong>
                      ),
                    }}
                  >
                    {message.content}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        ))}

        {isAsking && (
          <div className="flex justify-start">
            <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3">
              <Loader message="Searching the codebase..." />
            </div>
          </div>
        )}

        {/* Invisible anchor: we scroll to this after every new message. */}
        <div ref={bottomRef} />
      </div>

      {/* ------------------------------------------------------- input -- */}
      <div className="border-t border-slate-800 bg-slate-900 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder={
              repoName ? "Ask about the code..." : "Index a repository first"
            }
            disabled={!repoName || isAsking}
            className="flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-emerald-500 disabled:opacity-50"
          />
          <button
            onClick={handleSubmit}
            disabled={!repoName || isAsking || !question.trim()}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Ask
          </button>
        </div>
      </div>
    </div>
  );
}
