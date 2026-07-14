/**
 * API Layer
 * =========
 * Every network call to the FastAPI backend goes through this file.
 *
 * WHY CENTRALISE THIS?
 * If a component calls axios directly, the base URL gets copy-pasted into
 * six files. Change the port and you break five of them. Here, the backend
 * URL lives in exactly one place.
 *
 * It also gives us one place to normalise errors. FastAPI returns errors as
 * { detail: "..." }, so we unwrap that once here instead of in every catch
 * block in the UI.
 */

import axios from "axios";

const BASE_URL = "http://127.0.0.1:8000";

const client = axios.create({
  baseURL: BASE_URL,
  // Indexing a repo is slow (clone + embed on CPU). The default axios
  // timeout would abort a perfectly healthy request halfway through.
  timeout: 300000, // 5 minutes
});

/** Pull a readable message out of a FastAPI error response. */
function toMessage(error) {
  if (error.response?.data?.detail) return error.response.data.detail;
  if (error.code === "ECONNABORTED") return "Request timed out.";
  if (error.message === "Network Error")
    return "Cannot reach the backend. Is uvicorn running on port 8000?";
  return error.message || "Something went wrong.";
}

/** GET /health */
export async function checkHealth() {
  try {
    const { data } = await client.get("/health");
    return data;
  } catch (error) {
    throw new Error(toMessage(error));
  }
}

/** POST /index - clone, chunk, and embed a repository. */
export async function indexRepository(repoUrl) {
  try {
    const { data } = await client.post("/index", { repo_url: repoUrl });
    return data;
  } catch (error) {
    throw new Error(toMessage(error));
  }
}

/** POST /ask - ask a question, get an answer plus its sources. */
export async function askQuestion(repoName, question) {
  try {
    const { data } = await client.post("/ask", {
      repo_name: repoName,
      question,
    });
    return data;
  } catch (error) {
    throw new Error(toMessage(error));
  }
}

/** GET /files - the file tree. */
export async function listFiles(repoName) {
  try {
    const { data } = await client.get("/files", {
      params: { repo_name: repoName },
    });
    return data;
  } catch (error) {
    throw new Error(toMessage(error));
  }
}

/** GET /file - one file's contents. */
export async function readFile(repoName, path) {
  try {
    const { data } = await client.get("/file", {
      params: { repo_name: repoName, path },
    });
    return data;
  } catch (error) {
    throw new Error(toMessage(error));
  }
}

/** GET /search - literal keyword search across the repo. */
export async function searchKeyword(repoName, query) {
  try {
    const { data } = await client.get("/search", {
      params: { repo_name: repoName, q: query },
    });
    return data;
  } catch (error) {
    throw new Error(toMessage(error));
  }
}
