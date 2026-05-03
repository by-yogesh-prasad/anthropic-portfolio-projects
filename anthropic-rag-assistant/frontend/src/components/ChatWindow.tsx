import { useEffect, useRef } from "react";
import type { Message } from "../types";
import MessageBubble from "./MessageBubble";

interface ChatWindowProps {
  messages: Message[];
}

export default function ChatWindow({ messages }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-16 h-16 rounded-full bg-anthropic-orange/10 flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-anthropic-orange" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-gray-700 mb-2">
          Anthropic Docs Assistant
        </h2>
        <p className="text-gray-500 text-sm max-w-sm">
          Ask me anything about Claude, the Anthropic API, prompt engineering,
          or tool use. I'll find the answer from the official documentation.
        </p>
        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
          {[
            "What is Claude and what can it do?",
            "How do I get started with the Anthropic API?",
            "What are best practices for prompt engineering?",
            "How does tool use work in Claude?",
          ].map((q) => (
            <button
              key={q}
              className="text-left text-sm text-gray-600 bg-gray-50 hover:bg-gray-100 rounded-xl px-4 py-3 border border-gray-200 transition-colors"
              onClick={() => {
                const event = new CustomEvent("suggested-question", { detail: q });
                window.dispatchEvent(event);
              }}
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-3xl mx-auto">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
