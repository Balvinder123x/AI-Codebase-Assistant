/**
 * App
 * ===
 * The root component. It owns ALL the shared state and passes it down.
 *
 * WHY DOES STATE LIVE HERE AND NOT IN THE CHILDREN?
 * ------------------------------------------------
 * Because siblings need to share it. When you ask a question:
 *   - ChatBox     needs the answer      (to render the message)
 *   - SourcePanel needs the sources     (to render the chunks)
 *
 * ChatBox and SourcePanel are siblings; they cannot see each other's state.
 * So we "lift state up" to their nearest common parent - this file. This is
 * the standard React answer to "two components need the same data", and it
 * is the reason we do not need Redux or Context for an app this size.
 *
 * LAYOUT
 * ------
 *   +--------------------------------------------------+
 *   |                   RepoInput                      |
 *   +----------+---------------------------+-----------+
 *   | Sidebar  |         ChatBox           | SourcePanel|
 *   | (files / |    (messages + input)     | (chunks or |
 *   |  search) |                           |  file view)|
 *   +----------+---------------------------+-----------+
 */
import { useEffect, useState } from "react";

import ChatBox from "./components/ChatBox";
import RepoInput from "./components/RepoInput";
import Sidebar from "./components/Sidebar";
import SourcePanel from "./components/SourcePanel";
import {
  askQuestion,
  checkHealth,
  indexRepository,
  listFiles,
  readFile,
  searchKeyword,
} from "./api";

export default function App() {
  // --- repository state ---
  const [repoName, setRepoName] = useState(null);
  const [files, setFiles] = useState([]);
  const [isIndexing, setIsIndexing] = useState(false);

  // --- chat state ---
  const [messages, setMessages] = useState([]);
  const [sources, setSources] = useState([]);
  const [isAsking, setIsAsking] = useState(false);

  // --- file viewer state ---
  const [activeFile, setActiveFile] = useState(null);
  const [fileContent, setFileContent] = useState(null);

  // --- keyword search state ---
  const [searchHits, setSearchHits] = useState([]);
  const [isSearching, setIsSearching] = useState(false);

  // --- global ---
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);

  // Ping the backend once on mount, so we can warn the user immediately if
  // uvicorn isn't running or the API key is missing - rather than letting
  // them wait two minutes for an index to fail.
  useEffect(() => {
    checkHealth()
      .then(setHealth)
      .catch((e) => setError(e.message));
  }, []);

  async function handleIndex(repoUrl) {
    setIsIndexing(true);
    setError(null);
    // Clear everything from the previous repo. Leaving stale messages and
    // sources on screen while a new repo loads is deeply confusing.
    setMessages([]);
    setSources([]);
    setFiles([]);
    setActiveFile(null);
    setFileContent(null);
    setSearchHits([]);

    try {
      const result = await indexRepository(repoUrl);
      setRepoName(result.repo_name);

      const fileList = await listFiles(result.repo_name);
      setFiles(fileList.files);

      setMessages([
        {
          role: "assistant",
          content:
            `Indexed **${result.repo_name}** — ` +
            `${result.files_indexed} files, ${result.chunks_created} chunks. ` +
            `Ask me anything about this codebase.`,
        },
      ]);
    } catch (e) {
      setError(e.message);
      setRepoName(null);
    } finally {
      setIsIndexing(false);
    }
  }

  async function handleAsk(question) {
    if (!repoName) return;

    // Optimistic update: show the user's message immediately, before the
    // network call finishes. Waiting for the server to echo it back makes
    // the UI feel sluggish.
    setMessages((previous) => [
      ...previous,
      { role: "user", content: question },
    ]);
    setIsAsking(true);
    setError(null);
    setFileContent(null); // switch the right panel back to Sources
    setActiveFile(null);

    try {
      const result = await askQuestion(repoName, question);
      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: result.answer },
      ]);
      setSources(result.sources);
    } catch (e) {
      setError(e.message);
      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: `⚠️ ${e.message}` },
      ]);
    } finally {
      setIsAsking(false);
    }
  }

  async function handleOpenFile(path) {
    setError(null);
    try {
      const result = await readFile(repoName, path);
      setActiveFile(path);
      setFileContent(result.content);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleSearch(query) {
    if (!repoName) return;
    setIsSearching(true);
    setError(null);
    try {
      const result = await searchKeyword(repoName, query);
      setSearchHits(result.hits);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsSearching(false);
    }
  }

  function handleCloseFile() {
    setActiveFile(null);
    setFileContent(null);
  }

  return (
    <div className="flex h-screen flex-col bg-slate-950">
      <RepoInput
        onIndex={handleIndex}
        isIndexing={isIndexing}
        indexedRepo={repoName}
      />

      {/* Warn early if the API key is missing, instead of failing on /ask */}
      {health && !health.api_key_configured && (
        <div className="border-b border-amber-900 bg-amber-950 px-6 py-2 text-xs text-amber-300">
          ⚠️ GOOGLE_API_KEY is not set. Copy backend/.env.example to
          backend/.env and add your key.
        </div>
      )}

      {error && (
        <div className="flex items-center justify-between border-b border-red-900 bg-red-950 px-6 py-2 text-xs text-red-300">
          <span>⚠️ {error}</span>
          <button
            onClick={() => setError(null)}
            className="ml-4 text-red-400 hover:text-red-200"
          >
            ✕
          </button>
        </div>
      )}

      {isIndexing && (
        <div className="border-b border-slate-800 bg-slate-900 px-6 py-2 text-xs text-slate-400">
          Cloning and embedding the repository. This can take 1–2 minutes on
          first run (the embedding model downloads once, then it's cached).
        </div>
      )}

      {/* grid-cols-12 gives a responsive 3-column layout. The chat gets the
          most room; the panels are fixed-ish. On small screens the sidebar
          and source panel hide (`hidden md:flex`) so chat stays usable. */}
      <div className="grid flex-1 grid-cols-12 overflow-hidden">
        <aside className="col-span-3 hidden overflow-hidden md:flex md:flex-col lg:col-span-2">
          <Sidebar
            files={files}
            onOpenFile={handleOpenFile}
            onSearch={handleSearch}
            searchHits={searchHits}
            isSearching={isSearching}
            activeFile={activeFile}
          />
        </aside>

        <main className="col-span-12 overflow-hidden md:col-span-9 lg:col-span-6">
          <ChatBox
            messages={messages}
            onAsk={handleAsk}
            isAsking={isAsking}
            repoName={repoName}
          />
        </main>

        <aside className="hidden overflow-hidden lg:col-span-4 lg:flex lg:flex-col">
          <SourcePanel
            sources={sources}
            fileContent={fileContent}
            activeFile={activeFile}
            onClose={handleCloseFile}
          />
        </aside>
      </div>
    </div>
  );
}
