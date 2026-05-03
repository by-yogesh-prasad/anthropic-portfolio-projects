import type { Citation } from "../types";

interface SourceCitationProps {
  citations: Citation[];
}

export default function SourceCitation({ citations }: SourceCitationProps) {
  if (citations.length === 0) return null;

  return (
    <div className="mt-3 pt-3 border-t border-gray-200">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
        Sources
      </p>
      <ul className="space-y-1">
        {citations.map((c, i) => (
          <li key={c.url} className="flex items-start gap-1.5">
            <span className="text-xs text-gray-400 mt-0.5 shrink-0">{i + 1}.</span>
            <a
              href={c.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-anthropic-orange hover:underline break-all"
            >
              {c.title || c.url}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
