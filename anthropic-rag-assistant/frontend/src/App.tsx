import { useCallback, useEffect, useRef, useState } from "react";
import ChatWindow from "./components/ChatWindow";
import InputBar from "./components/InputBar";
import type { Citation, IngestJobStatus, Message, SSEEvent } from "./types";

// Optional API key — set VITE_API_KEY in .env to enable auth headers
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function authHeaders(): Record<string, string> {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<string | null>(null);
  const [ingestIsRunning, setIngestIsRunning] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Listen for suggested-question clicks from ChatWindow's empty state
  useEffect(() => {
    const handler = (e: Event) => {
      const question = (e as CustomEvent<string>).detail;
      if (question && !isLoading) handleSubmit(question);
    };
    window.addEventListener("suggested-question", handler);
    return () => window.removeEventListener("suggested-question", handler);
  }, [isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  // Clean up poll interval on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const handleSubmit = useCallback(async (question: string) => {
    if (isLoading) return;

    // Snapshot completed turns before adding the new pair
    const history = messages
      .filter((m) => !m.isStreaming && !m.error && m.content)
      .map((m) => ({ role: m.role, content: m.content }));

    const userMsg: Message = {
      id: generateId(),
      role: "user",
      content: question,
      citations: [],
      isStreaming: false,
    };
    const assistantId = generateId();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      citations: [],
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ question, history }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail ?? `${response.status} ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No response body");

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") continue;

          let event: SSEEvent;
          try { event = JSON.parse(raw); } catch { continue; }

          if (event.type === "token") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + event.content } : m
              )
            );
          } else if (event.type === "citations") {
            const citations: Citation[] = event.citations;
            setMessages((prev) =>
              prev.map((m) => m.id === assistantId ? { ...m, citations } : m)
            );
          } else if (event.type === "error") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, error: event.message, isStreaming: false } : m
              )
            );
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) =>
        prev.map((m) => m.id === assistantId ? { ...m, error: msg, isStreaming: false } : m)
      );
    } finally {
      setMessages((prev) =>
        prev.map((m) => m.id === assistantId ? { ...m, isStreaming: false } : m)
      );
      setIsLoading(false);
    }
  }, [isLoading, messages]);

  async function handleIngest() {
    if (ingestIsRunning) return;
    setIngestIsRunning(true);
    setIngestStatus("Queuing ingestion job…");

    try {
      const res = await fetch("/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: "{}",
      });
      const job = await res.json();

      if (!res.ok) {
        setIngestStatus(`Ingestion failed: ${job.detail ?? res.statusText}`);
        setIngestIsRunning(false);
        return;
      }

      const jobId: string = job.job_id;
      setIngestStatus("Ingestion running… (scraping & embedding docs)");

      // Poll /ingest/status/{job_id} every 4 seconds until done
      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await fetch(`/ingest/status/${jobId}`, {
            headers: authHeaders(),
          });
          if (!statusRes.ok) return;
          const status: IngestJobStatus = await statusRes.json();

          if (status.status === "running") {
            setIngestStatus("Ingestion running… (scraping & embedding docs)");
          } else if (status.status === "completed") {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            setIngestIsRunning(false);
            setIngestStatus(
              `Done — ${status.pages_processed} pages, ${status.total_chunks_added} chunks stored.`
            );
            setTimeout(() => setIngestStatus(null), 6000);
          } else if (status.status === "failed") {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            setIngestIsRunning(false);
            setIngestStatus(`Ingestion failed — check server logs.`);
            setTimeout(() => setIngestStatus(null), 8000);
          }
        } catch {
          // transient poll failure — keep trying
        }
      }, 4000);
    } catch (err) {
      setIngestStatus(`Ingestion failed: ${err instanceof Error ? err.message : "network error"}`);
      setIngestIsRunning(false);
    }
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50 font-sans">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-anthropic-orange flex items-center justify-center text-white font-bold text-sm">
            A
          </div>
          <div>
            <h1 className="text-sm font-semibold text-gray-900">Anthropic RAG Assistant</h1>
            <p className="text-xs text-gray-500">Powered by Claude + OpenAI Embeddings</p>
          </div>
        </div>
        <button
          onClick={handleIngest}
          disabled={ingestIsRunning}
          className="text-xs text-gray-500 hover:text-anthropic-orange border border-gray-200 hover:border-anthropic-orange rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {ingestIsRunning ? "Syncing…" : "Sync Docs"}
        </button>
      </header>

      {/* Ingest status banner */}
      {ingestStatus && (
        <div className="bg-blue-50 border-b border-blue-200 px-4 py-2 text-xs text-blue-700 text-center">
          {ingestStatus}
        </div>
      )}

      {/* Chat area */}
      <ChatWindow messages={messages} />

      {/* Input */}
      <InputBar onSubmit={handleSubmit} isLoading={isLoading} />
    </div>
  );
}
