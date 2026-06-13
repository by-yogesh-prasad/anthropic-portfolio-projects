"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Menu, X, Sun, Moon } from "lucide-react";
import { cn } from "@/lib/utils";
import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import QuestionInput from "./QuestionInput";
import { fetchRepos, indexRepo, clearRepo, streamAsk } from "@/lib/api";
import type { RepoInfo, Message } from "@/lib/types";

let messageCounter = 0;
function nextId() {
  return `msg-${++messageCounter}-${Date.now()}`;
}

export default function AppShell() {
  const [repos, setRepos] = useState<RepoInfo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isIndexing, setIsIndexing] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  // Sync isDark with whatever the no-flash script applied
  useEffect(() => {
    setIsDark(document.documentElement.classList.contains("dark"));
  }, []);

  const toggleTheme = useCallback(() => {
    const next = !isDark;
    setIsDark(next);
    document.documentElement.classList.toggle("dark", next);
    try { localStorage.setItem("theme", next ? "dark" : "light"); } catch {}
  }, [isDark]);

  // Load repos on mount
  useEffect(() => {
    fetchRepos()
      .then((data) => {
        setRepos(data);
        if (data.length === 1) setSelectedRepo(data[0].name);
      })
      .catch(console.error);
  }, []);

  // Close sidebar on outside click (mobile)
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (overlayRef.current && e.target === overlayRef.current) {
        setSidebarOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Close sidebar on Escape
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") setSidebarOpen(false);
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const handleIndexRepo = useCallback(async (path: string) => {
    setIsIndexing(true);
    try {
      const meta = await indexRepo(path);
      setRepos((prev) => {
        const filtered = prev.filter((r) => r.name !== meta.name);
        return [...filtered, meta];
      });
      setSelectedRepo(meta.name);
    } finally {
      setIsIndexing(false);
    }
  }, []);

  const handleClearRepo = useCallback(async (name: string) => {
    await clearRepo(name);
    setRepos((prev) => prev.filter((r) => r.name !== name));
    setSelectedRepo((cur) => (cur === name ? null : cur));
    setMessages((prev) => prev); // keep chat history (it's session-scoped)
  }, []);

  const handleAsk = useCallback(
    async (question: string, topK: number) => {
      if (!selectedRepo || isAsking) return;

      const id = nextId();
      const newMsg: Message = {
        id,
        question,
        answer: "",
        sources: [],
        status: "streaming",
      };

      setMessages((prev) => [...prev, newMsg]);
      setIsAsking(true);
      setSidebarOpen(false); // close mobile drawer on ask

      try {
        await streamAsk(question, selectedRepo, topK, {
          onChunk(text) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === id ? { ...m, answer: m.answer + text } : m
              )
            );
          },
          onDone(sources, usage) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === id ? { ...m, sources, usage, status: "done" } : m
              )
            );
          },
          onError(message) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === id ? { ...m, answer: message, status: "error" } : m
              )
            );
          },
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === id ? { ...m, answer: msg, status: "error" } : m
          )
        );
      } finally {
        setIsAsking(false);
      }
    },
    [selectedRepo, isAsking]
  );

  const handleAskExample = useCallback(
    (question: string) => {
      handleAsk(question, 10);
    },
    [handleAsk]
  );

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: "var(--background)" }}
    >
      {/* ── Desktop sidebar (always visible on md+) ── */}
      <aside
        className="hidden md:flex flex-col w-72 flex-shrink-0 border-r"
        style={{ borderColor: "var(--border)" }}
        aria-label="Repository sidebar"
      >
        <Sidebar
          repos={repos}
          selectedRepo={selectedRepo}
          onSelectRepo={setSelectedRepo}
          onIndexRepo={handleIndexRepo}
          onClearRepo={handleClearRepo}
          isIndexing={isIndexing}
          isDark={isDark}
          onToggleTheme={toggleTheme}
        />
      </aside>

      {/* ── Mobile sidebar overlay ── */}
      {sidebarOpen && (
        <div
          ref={overlayRef}
          className="fixed inset-0 z-40 md:hidden"
          style={{ background: "rgba(0,0,0,0.6)" }}
          aria-hidden="true"
        />
      )}
      <aside
        className={cn(
          "fixed top-0 left-0 bottom-0 z-50 w-72 flex-col border-r flex md:hidden transition-transform duration-250 ease-out",
          sidebarOpen ? "translate-x-0 animate-slide-in" : "-translate-x-full"
        )}
        style={{ borderColor: "var(--border)" }}
        aria-label="Repository sidebar"
        aria-hidden={!sidebarOpen}
      >
        <Sidebar
          repos={repos}
          selectedRepo={selectedRepo}
          onSelectRepo={(name) => {
            setSelectedRepo(name);
            setSidebarOpen(false);
          }}
          onIndexRepo={handleIndexRepo}
          onClearRepo={handleClearRepo}
          isIndexing={isIndexing}
          isDark={isDark}
          onToggleTheme={toggleTheme}
        />
      </aside>

      {/* ── Main content ── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Mobile top bar */}
        <header
          className="flex items-center gap-3 px-4 py-3 border-b md:hidden flex-shrink-0"
          style={{ borderColor: "var(--border)", background: "var(--surface)" }}
        >
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
            className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
            style={{ color: "var(--text-secondary)" }}
          >
            <Menu className="w-5 h-5" />
          </button>
          <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            🧠 GitMind
          </span>
          {selectedRepo && (
            <>
              <span style={{ color: "var(--border)" }}>·</span>
              <span className="text-sm truncate" style={{ color: "var(--text-muted)" }}>
                {selectedRepo}
              </span>
            </>
          )}
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={toggleTheme}
              aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
              className="p-1.5 rounded-lg transition-colors"
              style={{ color: "var(--text-secondary)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--hover-bg)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            {sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(false)}
                aria-label="Close sidebar"
                className="p-1.5 rounded-lg transition-colors"
                style={{ color: "var(--text-secondary)" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--hover-bg)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>
        </header>

        {/* Chat area (scrollable) */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <ChatWindow
            messages={messages}
            selectedRepo={selectedRepo}
            isAsking={isAsking}
            onAskExample={handleAskExample}
          />

          <QuestionInput
            onAsk={handleAsk}
            disabled={isAsking}
            selectedRepo={selectedRepo}
          />
        </div>
      </div>
    </div>
  );
}
