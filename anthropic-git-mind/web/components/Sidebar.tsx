"use client";

import { useState, useRef } from "react";
import { Trash2, Loader2, FolderOpen, Plus, Check, AlertCircle, Sun, Moon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RepoInfo } from "@/lib/types";

interface SidebarProps {
  repos: RepoInfo[];
  selectedRepo: string | null;
  onSelectRepo: (name: string) => void;
  onIndexRepo: (path: string) => Promise<void>;
  onClearRepo: (name: string) => Promise<void>;
  isIndexing: boolean;
  isDark: boolean;
  onToggleTheme: () => void;
}

export default function Sidebar({
  repos,
  selectedRepo,
  onSelectRepo,
  onIndexRepo,
  onClearRepo,
  isIndexing,
  isDark,
  onToggleTheme,
}: SidebarProps) {
  const [indexPath, setIndexPath] = useState("");
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indexSuccess, setIndexSuccess] = useState(false);
  const [clearingRepo, setClearingRepo] = useState<string | null>(null);
  const [hoveredRepo, setHoveredRepo] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleIndex() {
    const path = indexPath.trim();
    if (!path) return;
    setIndexError(null);
    setIndexSuccess(false);
    try {
      await onIndexRepo(path);
      setIndexPath("");
      setIndexSuccess(true);
      setTimeout(() => setIndexSuccess(false), 3000);
    } catch (err) {
      setIndexError(err instanceof Error ? err.message : "Failed to index repository");
    }
  }

  async function handleClear(name: string) {
    const confirmed = window.confirm(
      `Remove "${name}" from GitMind?\n\nThis deletes the index but does not affect your local repository.`
    );
    if (!confirmed) return;
    setClearingRepo(name);
    try {
      await onClearRepo(name);
    } finally {
      setClearingRepo(null);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      handleIndex();
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: "var(--surface)" }}>
      {/* Logo */}
      <div
        className="px-5 py-5 border-b flex-shrink-0"
        style={{ borderColor: "var(--border)" }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="text-2xl" role="img" aria-label="brain">🧠</span>
          <h1 className="text-lg font-bold tracking-tight flex-1" style={{ color: "var(--text-primary)" }}>
            GitMind
          </h1>
          <button
            onClick={onToggleTheme}
            aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
            className="p-1.5 rounded-lg transition-colors"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--hover-bg)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Ask your Git history
        </p>
      </div>

      {/* Repositories list */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        <div className="mb-2 px-2">
          <span
            className="text-xs font-semibold uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Repositories
          </span>
        </div>

        {repos.length === 0 ? (
          <div
            className="px-2 py-4 text-center text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            No repos indexed yet.
          </div>
        ) : (
          <ul className="space-y-0.5">
            {repos.map((repo) => {
              const isSelected = repo.name === selectedRepo;
              const isClearing = clearingRepo === repo.name;
              return (
                <li key={repo.name}>
                  <div
                    className={cn(
                      "group flex items-center gap-2.5 px-2 py-2.5 rounded-lg cursor-pointer transition-all duration-150",
                      isSelected
                        ? "border border-indigo-500/30"
                        : "border border-transparent"
                    )}
                    onClick={() => onSelectRepo(repo.name)}
                    onMouseEnter={() => setHoveredRepo(repo.name)}
                    onMouseLeave={() => setHoveredRepo(null)}
                    style={isSelected ? { background: "var(--hover-bg)", borderColor: "rgba(99,102,241,0.3)" } : {}}
                    onMouseEnter={(e) => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "var(--hover-bg)"; }}
                    onMouseLeave={(e) => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectRepo(repo.name);
                      }
                    }}
                  >
                    {/* Status dot */}
                    <div
                      className="w-2 h-2 rounded-full flex-shrink-0 transition-colors"
                      style={{ background: isSelected ? "var(--accent)" : "var(--text-muted)" }}
                    />

                    {/* Repo info */}
                    <div className="flex-1 min-w-0">
                      <div
                        className="text-sm font-semibold truncate transition-colors"
                        style={{ color: isSelected ? "var(--accent)" : "var(--text-primary)" }}
                        title={repo.name}
                      >
                        {repo.name}
                      </div>
                      <div className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                        {repo.total_commits.toLocaleString()} commits · {repo.chunk_count.toLocaleString()} chunks
                      </div>
                    </div>

                    {/* Trash icon */}
                    <button
                      className={cn(
                        "flex-shrink-0 p-1 rounded transition-all duration-150",
                        hoveredRepo === repo.name || isSelected
                          ? "opacity-100"
                          : "opacity-0",
                        "hover:bg-red-500/20 text-zinc-500 hover:text-red-400"
                      )}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleClear(repo.name);
                      }}
                      disabled={isClearing}
                      aria-label={`Remove ${repo.name}`}
                    >
                      {isClearing ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Index new repo */}
      <div
        className="px-3 py-4 border-t flex-shrink-0 space-y-2"
        style={{ borderColor: "var(--border)" }}
      >
        <div className="px-1 mb-1">
          <span
            className="text-xs font-semibold uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Index Repository
          </span>
        </div>

        <div className="flex gap-2">
          <div className="relative flex-1">
            <FolderOpen
              className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
              style={{ color: "var(--text-muted)" }}
            />
            <input
              ref={inputRef}
              type="text"
              value={indexPath}
              onChange={(e) => setIndexPath(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="/path/to/repo"
              disabled={isIndexing}
              aria-label="Repository path to index"
              className={cn(
                "w-full pl-8 pr-2 py-2 text-xs rounded-lg border outline-none transition-all",
                "placeholder:text-zinc-600 disabled:opacity-50 disabled:cursor-not-allowed",
                "focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30"
              )}
              style={{
                background: "var(--card)",
                borderColor: "var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </div>

          <button
            onClick={handleIndex}
            disabled={isIndexing || !indexPath.trim()}
            aria-label="Index repository"
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150",
              "bg-indigo-600 hover:bg-indigo-500 text-white",
              "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-indigo-600",
              "focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            )}
          >
            {isIndexing ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Indexing…</span>
              </>
            ) : (
              <>
                <Plus className="w-3.5 h-3.5" />
                <span>Index</span>
              </>
            )}
          </button>
        </div>

        {/* Feedback messages */}
        {indexError && (
          <div
            className="flex items-start gap-2 px-2.5 py-2 rounded-lg text-xs animate-fade-in"
            style={{
              background: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.25)",
              color: "#fca5a5",
            }}
          >
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span className="break-all">{indexError}</span>
          </div>
        )}

        {indexSuccess && (
          <div
            className="flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs animate-fade-in"
            style={{
              background: "rgba(34,197,94,0.1)",
              border: "1px solid rgba(34,197,94,0.25)",
              color: "#86efac",
            }}
          >
            <Check className="w-3.5 h-3.5 flex-shrink-0" />
            <span>Repository indexed successfully!</span>
          </div>
        )}
      </div>
    </div>
  );
}
