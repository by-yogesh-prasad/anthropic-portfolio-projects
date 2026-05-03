export interface Citation {
  url: string;
  title: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  isStreaming: boolean;
  error?: string;
}

export type SSEEvent =
  | { type: "token"; content: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "error"; message: string };

export interface IngestJobQueued {
  job_id: string;
  status: "queued";
  message: string;
}

export interface IngestJobStatus {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  queued_at: string;
  started_at?: string;
  finished_at?: string;
  pages_processed?: number;
  pages_failed?: number;
  total_chunks_added?: number;
  error?: string;
}
