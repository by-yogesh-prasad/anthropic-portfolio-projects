"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { GitBranch, MessageSquare } from "lucide-react";
import ChatMessage from "./ChatMessage";
import type { Message } from "@/lib/types";

interface ChatWindowProps {
  messages: Message[];
  selectedRepo: string | null;
  isAsking: boolean;
  onAskExample?: (question: string) => void;
}

const EXAMPLE_QUESTIONS = [
  "Why was the authentication module added?",
  "What changed in the configuration files recently?",
  "When was the database schema last refactored?",
];

export default function ChatWindow({
  messages,
  selectedRepo,
  isAsking,
  onAskExample,
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const isStreamingRef = useRef(false);

  // Detect if user has scrolled up while streaming
  function handleScroll() {
    const container = scrollContainerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    setUserScrolledUp(distanceFromBottom > 80);
  }

  // Auto-scroll to bottom when new content arrives (unless user scrolled up)
  const scrollToBottom = useCallback((force = false) => {
    if (userScrolledUp && !force) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [userScrolledUp]);

  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage) return;

    isStreamingRef.current = lastMessage.status === "streaming";

    if (lastMessage.status === "streaming" && !userScrolledUp) {
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    } else if (lastMessage.status === "done") {
      scrollToBottom(false);
    }
  }, [messages, userScrolledUp, scrollToBottom]);

  // When a new question is asked, force scroll to bottom and reset state
  useEffect(() => {
    if (isAsking) {
      setUserScrolledUp(false);
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [isAsking]);

  // No repo selected
  if (!selectedRepo) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-6 text-center">
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
          style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        >
          <GitBranch className="w-8 h-8" style={{ color: "var(--accent)" }} />
        </div>
        <h2 className="text-xl font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
          No repository selected
        </h2>
        <p className="text-sm max-w-xs" style={{ color: "var(--text-muted)" }}>
          Select or index a repository to get started asking questions about your
          Git history.
        </p>
      </div>
    );
  }

  // Repo selected but no messages yet — show hero
  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-6 text-center">
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
          style={{ background: "var(--avatar-bg)", border: "1px solid var(--avatar-border)" }}
        >
          <span className="text-3xl" role="img" aria-label="brain">
            🧠
          </span>
        </div>
        <h2 className="text-xl font-semibold mb-1" style={{ color: "var(--text-primary)" }}>
          {selectedRepo}
        </h2>
        <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>
          Ask anything about this repository&apos;s history.
        </p>

        {/* Example question chips */}
        <div className="flex flex-col gap-2 w-full max-w-sm">
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => onAskExample?.(q)}
              className="flex items-center gap-2.5 w-full px-4 py-3 rounded-xl text-sm text-left transition-all duration-150 hover:scale-[1.01]"
              style={{
                background: "var(--card)",
                border: "1px solid var(--border)",
                color: "var(--text-secondary)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--accent)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
              }}
            >
              <MessageSquare className="w-4 h-4 flex-shrink-0 text-indigo-500" />
              <span>{q}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollContainerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 py-6 space-y-6"
    >
      <div className="max-w-3xl mx-auto space-y-6">
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}
      </div>
      <div ref={bottomRef} className="h-px" />
    </div>
  );
}
