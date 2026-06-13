import type { RepoInfo, Source, Usage, SSEEvent } from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchRepos(): Promise<RepoInfo[]> {
  const res = await fetch(`${BASE_URL}/repos`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch repos: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function indexRepo(repoPath: string): Promise<RepoInfo> {
  const res = await fetch(`${BASE_URL}/repos/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_path: repoPath }),
  });
  if (!res.ok) {
    const errorText = await res.text().catch(() => res.statusText);
    throw new Error(`Failed to index repo: ${errorText}`);
  }
  return res.json();
}

export async function clearRepo(name: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/repos/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(`Failed to clear repo: ${res.status} ${res.statusText}`);
  }
}

export interface StreamAskCallbacks {
  onChunk: (text: string) => void;
  onDone: (sources: Source[], usage: Usage) => void;
  onError: (message: string) => void;
}

export async function streamAsk(
  question: string,
  repo: string,
  topK: number,
  callbacks: StreamAskCallbacks
): Promise<void> {
  const res = await fetch(`${BASE_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ question, repo, top_k: topK }),
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => res.statusText);
    callbacks.onError(`Request failed: ${errorText}`);
    return;
  }

  const body = res.body;
  if (!body) {
    callbacks.onError("No response body received");
    return;
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by double newlines
      const lines = buffer.split("\n");
      // Keep the last incomplete line in the buffer
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        if (!trimmed.startsWith("data:")) continue;

        const jsonStr = trimmed.slice("data:".length).trim();
        if (!jsonStr) continue;

        try {
          const event = JSON.parse(jsonStr) as SSEEvent;

          if (event.type === "chunk") {
            callbacks.onChunk(event.text);
          } else if (event.type === "done") {
            callbacks.onDone(event.sources, event.usage);
          } else if (event.type === "error") {
            callbacks.onError(event.message);
          }
        } catch {
          // Silently skip malformed SSE lines
        }
      }
    }

    // Process any remaining buffer content
    if (buffer.trim().startsWith("data:")) {
      const jsonStr = buffer.trim().slice("data:".length).trim();
      if (jsonStr) {
        try {
          const event = JSON.parse(jsonStr) as SSEEvent;
          if (event.type === "chunk") {
            callbacks.onChunk(event.text);
          } else if (event.type === "done") {
            callbacks.onDone(event.sources, event.usage);
          } else if (event.type === "error") {
            callbacks.onError(event.message);
          }
        } catch {
          // Silently skip malformed remaining buffer
        }
      }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "Stream read error";
    callbacks.onError(message);
  } finally {
    reader.releaseLock();
  }
}
