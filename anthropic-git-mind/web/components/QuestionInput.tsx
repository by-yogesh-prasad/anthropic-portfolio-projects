"use client";

import { useRef, useState, useEffect } from "react";
import { Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface QuestionInputProps {
  onAsk: (question: string, topK: number) => void;
  disabled: boolean;
  selectedRepo: string | null;
}

export default function QuestionInput({
  onAsk,
  disabled,
  selectedRepo,
}: QuestionInputProps) {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(10);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  function adjustHeight() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    // Limit to ~4 rows (approx 96px at 24px line-height)
    const maxH = 96;
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`;
  }

  useEffect(() => {
    adjustHeight();
  }, [question]);

  function handleSubmit() {
    const q = question.trim();
    if (!q || disabled || !selectedRepo) return;
    onAsk(q, topK);
    setQuestion("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Cmd+Enter or Ctrl+Enter to submit
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  }

  const isDisabled = disabled || !selectedRepo;
  const placeholder = !selectedRepo
    ? "Select a repository to start asking…"
    : disabled
    ? "Waiting for answer…"
    : "Ask about your Git history…";

  return (
    <div
      className="relative flex-shrink-0"
      style={{ borderTop: "1px solid var(--border)" }}
    >
      {/* Gradient fade above input */}
      <div
        className="absolute -top-10 left-0 right-0 h-10 pointer-events-none"
        style={{
          background:
            "linear-gradient(to bottom, transparent, var(--background))",
        }}
      />

      <div
        className="px-4 py-3"
        style={{ background: "var(--background)" }}
      >
        <div className="max-w-3xl mx-auto">
          <div
            className={cn(
              "rounded-xl transition-all duration-150",
              "focus-within:ring-2 focus-within:ring-indigo-500/40 focus-within:border-indigo-500/60",
              isDisabled ? "opacity-60" : ""
            )}
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
            }}
          >
            {/* Textarea */}
            <textarea
              ref={textareaRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={isDisabled}
              rows={1}
              aria-label="Ask a question about your Git history"
              className={cn(
                "w-full px-4 pt-3 pb-2 bg-transparent resize-none outline-none",
                "text-sm leading-6 placeholder:text-zinc-600",
                "disabled:cursor-not-allowed"
              )}
              style={{
                color: "var(--text-primary)",
                maxHeight: "96px",
                overflowY: "auto",
              }}
            />

            {/* Bottom row: top-k + submit */}
            <div className="flex items-center justify-between px-3 pb-3 pt-1">
              {/* Top K control */}
              <div className="flex items-center gap-2">
                <label
                  htmlFor="top-k"
                  className="text-xs font-medium"
                  style={{ color: "var(--text-muted)" }}
                >
                  Top K
                </label>
                <input
                  id="top-k"
                  type="number"
                  value={topK}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10);
                    if (!isNaN(v)) setTopK(Math.max(3, Math.min(30, v)));
                  }}
                  min={3}
                  max={30}
                  disabled={isDisabled}
                  aria-label="Number of sources to retrieve"
                  className={cn(
                    "w-14 px-2 py-1 text-xs text-center rounded-md outline-none border transition-colors",
                    "focus:border-indigo-500/60 disabled:cursor-not-allowed"
                  )}
                  style={{
                    background: "var(--surface)",
                    borderColor: "var(--border)",
                    color: "var(--text-secondary)",
                  }}
                />
              </div>

              {/* Submit button */}
              <button
                onClick={handleSubmit}
                disabled={isDisabled || !question.trim()}
                aria-label="Submit question (Cmd+Enter)"
                title="Submit (Cmd+Enter)"
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150",
                  "bg-indigo-600 hover:bg-indigo-500 text-white",
                  "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-indigo-600",
                  "focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                )}
              >
                {disabled ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Thinking…</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Ask</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Keyboard hint */}
          <p
            className="text-center text-xs mt-2"
            style={{ color: "var(--text-muted)" }}
          >
            {!isDisabled && "Press Cmd+Enter to submit"}
          </p>
        </div>
      </div>
    </div>
  );
}
