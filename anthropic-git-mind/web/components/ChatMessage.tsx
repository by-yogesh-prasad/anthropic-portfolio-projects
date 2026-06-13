"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronRight, User, GitCommit, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Message, Source } from "@/lib/types";

interface ChatMessageProps {
  message: Message;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);

  return (
    <div className="space-y-3 animate-fade-in">
      {/* Question bubble — right-aligned */}
      <div className="flex justify-end gap-3 items-end">
        <div
          className="max-w-[75%] px-4 py-3 rounded-2xl rounded-br-sm text-sm leading-relaxed"
          style={{
            background: "linear-gradient(135deg, #6366f1, #4f46e5)",
            color: "#ffffff",
          }}
        >
          {message.question}
        </div>
        <div
          className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center"
          style={{ background: "#3730a3" }}
          aria-label="You"
        >
          <User className="w-4 h-4 text-indigo-200" />
        </div>
      </div>

      {/* Answer card — left-aligned */}
      <div className="flex gap-3 items-start">
        <div
          className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-0.5"
          style={{ background: "var(--avatar-bg)", border: "1px solid var(--avatar-border)" }}
          aria-label="GitMind"
        >
          <span className="text-sm" role="img" aria-label="brain">
            🧠
          </span>
        </div>

        <div className="flex-1 min-w-0 space-y-2">
          {/* Answer content */}
          <div
            className="rounded-2xl rounded-tl-sm px-4 py-3"
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
            }}
          >
            {message.status === "error" ? (
              <div
                className="flex items-start gap-2 text-sm"
                style={{ color: "#fca5a5" }}
              >
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{message.answer}</span>
              </div>
            ) : (
              <div className="prose-content text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.answer}
                </ReactMarkdown>
                {message.status === "streaming" && (
                  <span className="cursor-blink" aria-hidden="true">
                    ▌
                  </span>
                )}
                {message.status === "streaming" && !message.answer && (
                  <span className="text-zinc-500 text-sm italic">Thinking…</span>
                )}
              </div>
            )}
          </div>

          {/* Sources accordion */}
          {message.status === "done" && message.sources.length > 0 && (
            <div
              className="rounded-xl overflow-hidden text-xs"
              style={{
                border: "1px solid var(--border)",
                background: "var(--surface)",
              }}
            >
              <button
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2 text-left transition-colors",
                  "hover:bg-white/5"
                )}
                onClick={() => setSourcesOpen((o) => !o)}
                aria-expanded={sourcesOpen}
                aria-label={`${message.sources.length} sources`}
              >
                {sourcesOpen ? (
                  <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 text-indigo-400" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 text-indigo-400" />
                )}
                <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
                  {message.sources.length} source{message.sources.length !== 1 ? "s" : ""}
                </span>
              </button>

              {sourcesOpen && (
                <div
                  className="border-t divide-y"
                  style={{
                    borderColor: "var(--border)",
                  }}
                >
                  {message.sources.map((source, idx) => (
                    <SourceItem key={`${source.full_sha}-${idx}`} source={source} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Usage footer */}
          {message.status === "done" && message.usage && (
            <div
              className="px-1 text-xs"
              style={{ color: "var(--text-muted)" }}
              aria-label="Token usage"
            >
              {message.usage.input.toLocaleString()} in &middot;{" "}
              {message.usage.output.toLocaleString()} out tokens
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SourceItem({ source }: { source: Source }) {
  const previewText =
    source.text.length > 200 ? source.text.slice(0, 200) + "…" : source.text;

  const chunkTypeColor: Record<string, string> = {
    commit: "bg-violet-900/60 text-violet-300 border-violet-800/50",
    diff: "bg-blue-900/60 text-blue-300 border-blue-800/50",
    file: "bg-emerald-900/60 text-emerald-300 border-emerald-800/50",
  };

  const badgeClass =
    chunkTypeColor[source.chunk_type] ??
    "bg-zinc-800 text-zinc-400 border-zinc-700";

  return (
    <div
      className="px-3 py-2.5 space-y-1.5"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="flex items-center gap-2 flex-wrap">
        {/* SHA chip */}
        <span
          className="inline-flex items-center gap-1 font-mono px-2 py-0.5 rounded text-xs border"
          style={{
            background: "var(--sha-bg)",
            color: "var(--sha-text)",
            borderColor: "var(--sha-border)",
          }}
          title={source.full_sha}
        >
          <GitCommit className="w-3 h-3" />
          {source.sha}
        </span>

        {/* Chunk type badge */}
        <span
          className={cn(
            "inline-flex items-center px-1.5 py-0.5 rounded text-xs border",
            badgeClass
          )}
        >
          {source.chunk_type}
        </span>

        {/* Distance score */}
        <span style={{ color: "var(--text-muted)" }}>
          dist: {source.distance.toFixed(4)}
        </span>
      </div>

      {/* Source text preview */}
      <p
        className="font-mono leading-relaxed"
        style={{ color: "var(--text-secondary)", fontSize: "11px" }}
      >
        {previewText}
      </p>
    </div>
  );
}
