import { useState, type KeyboardEvent } from "react";

interface InputBarProps {
  onSubmit: (question: string) => void;
  isLoading: boolean;
}

export default function InputBar({ onSubmit, isLoading }: InputBarProps) {
  const [value, setValue] = useState("");

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSubmit(trimmed);
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="flex items-end gap-2 max-w-3xl mx-auto">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about Anthropic's documentation…"
          disabled={isLoading}
          rows={1}
          className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-anthropic-orange focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400 max-h-40 overflow-y-auto"
          style={{ height: "auto" }}
          onInput={(e) => {
            const t = e.currentTarget;
            t.style.height = "auto";
            t.style.height = `${t.scrollHeight}px`;
          }}
        />
        <button
          onClick={handleSubmit}
          disabled={!value.trim() || isLoading}
          className="shrink-0 rounded-xl bg-anthropic-orange px-4 py-2.5 text-sm font-medium text-white hover:bg-orange-600 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? (
            <span className="flex items-center gap-1.5">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span>Thinking</span>
            </span>
          ) : (
            "Send"
          )}
        </button>
      </div>
      <p className="text-center text-xs text-gray-400 mt-2">
        Press Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
}
