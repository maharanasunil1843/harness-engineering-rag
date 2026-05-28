export interface SourceInfo {
  doc_title: string;
  element_type: string;
  relevance_score: number;
  snippet: string;
  source_file?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceInfo[];
  confidence?: number;
  traceId?: string;
  latencyMs?: number;
  cacheHit?: boolean;
  timestamp: number;
}

export interface Session {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

export interface QueryResponse {
  answer: string;
  sources: SourceInfo[];
  confidence: number;
  trace_id: string;
  latency_ms: number;
  cache_hit: boolean;
}

export interface HealthResponse {
  status: string;
  version?: string;
}

export interface CacheStats {
  hits: number;
  misses: number;
  size: number;
}
