export interface RepoInfo {
  name: string;
  repo_path: string;
  total_commits: number;
  chunk_count: number;
  indexed_at: string;
}

export interface Source {
  sha: string;
  full_sha: string;
  chunk_type: string;
  distance: number;
  text: string;
}

export interface Usage {
  input: number;
  output: number;
}

export interface Message {
  id: string;
  question: string;
  answer: string;
  sources: Source[];
  usage?: Usage;
  status: "streaming" | "done" | "error";
}

export type SSEEvent =
  | { type: "chunk"; text: string }
  | { type: "done"; sources: Source[]; usage: Usage }
  | { type: "error"; message: string };
