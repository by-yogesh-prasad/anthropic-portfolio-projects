import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../types";
import SourceCitation from "./SourceCitation";

interface MessageBubbleProps {
  message: Message;
}

function TypingIndicator() {
  return (
    <span className="inline-flex gap-1 items-center">
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.3s]" />
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.15s]" />
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" />
    </span>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-anthropic-orange flex items-center justify-center text-white text-xs font-bold shrink-0 mr-2 mt-1">
          A
        </div>
      )}

      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 shadow-sm ${
          isUser
            ? "bg-anthropic-orange text-white rounded-br-sm"
            : "bg-white text-gray-800 rounded-bl-sm border border-gray-100"
        }`}
      >
        {message.error ? (
          <p className="text-red-500 text-sm">{message.error}</p>
        ) : isUser ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            {message.content ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                className="prose prose-sm max-w-none
                  prose-headings:font-semibold prose-headings:text-gray-900 prose-headings:mt-3 prose-headings:mb-1
                  prose-p:my-1 prose-p:leading-relaxed
                  prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5
                  prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono prose-code:text-gray-700 prose-code:before:content-none prose-code:after:content-none
                  prose-pre:bg-gray-100 prose-pre:rounded-lg prose-pre:p-3 prose-pre:text-xs prose-pre:overflow-x-auto
                  prose-a:text-anthropic-orange prose-a:no-underline hover:prose-a:underline
                  prose-strong:font-semibold prose-strong:text-gray-900
                  prose-blockquote:border-l-anthropic-orange prose-blockquote:text-gray-600"
              >
                {message.content}
              </ReactMarkdown>
            ) : (
              message.isStreaming && <TypingIndicator />
            )}
            {!message.isStreaming && (
              <SourceCitation citations={message.citations} />
            )}
          </>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-gray-600 text-xs font-bold shrink-0 ml-2 mt-1">
          U
        </div>
      )}
    </div>
  );
}
