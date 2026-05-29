import type { CacheStats, HealthResponse, QueryResponse, SourceInfo } from "./types";

export type { CacheStats, HealthResponse, QueryResponse, SourceInfo };

export interface StreamCallbacks {
  onStatus: (status: string) => void;
  onSource: (source: SourceInfo) => void;
  onToken: (token: string) => void;
  onDone: (meta: {
    confidence?: number;
    trace_id?: string;
    latency_ms?: number;
    cache_hit?: boolean;
    sources?: SourceInfo[];
  }) => void;
  onError: (message: string) => void;
}

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Backend status events carry a machine-readable `step` (e.g. "retrieving").
// Map the known steps to user-facing labels; fall back to the raw value.
const STATUS_LABELS: Record<string, string> = {
  classifying: "Classifying query...",
  querying_sql: "Querying database...",
  retrieving: "Retrieving sources...",
  synthesizing: "Synthesizing answer...",
};

function humanizeStatus(step: string): string {
  return STATUS_LABELS[step] ?? step;
}

// The backend SourceInfo uses `score`; the UI's SourceInfo uses
// `relevance_score`. Normalize both `source` events and `done.sources`.
function mapSource(raw: Record<string, unknown>): SourceInfo {
  return {
    doc_title: (raw.doc_title as string) ?? (raw.doc_id as string) ?? "Untitled",
    element_type: (raw.element_type as string) ?? "text",
    relevance_score:
      (raw.relevance_score as number) ?? (raw.score as number) ?? 0,
    snippet: (raw.snippet as string) ?? "",
    source_file: raw.source_file as string | undefined,
  };
}

export function streamQuery(
  query: string,
  callbacks: StreamCallbacks
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`${apiUrl}/api/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      });

      if (!response.ok) {
        callbacks.onError(
          `Server error: ${response.status} ${response.statusText}`
        );
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        callbacks.onError("No response body from server");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";
      // sse-starlette carries the event kind on a dedicated `event:` line,
      // NOT inside the JSON `data:` payload. Track it across the lines of
      // each event block and reset it on the blank separator line.
      let eventType = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        // Split on LF; the server uses CRLF line endings, so strip a
        // trailing CR from each line before inspecting it.
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const rawLine of lines) {
          const line = rawLine.replace(/\r$/, "");
          if (line === "") {
            // Blank line terminates the current event block.
            eventType = "";
            continue;
          }
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
            continue;
          }
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trim();
          if (!data || data === "[DONE]") continue;
          try {
            const event = JSON.parse(data) as Record<string, unknown>;
            switch (eventType) {
              case "status":
                callbacks.onStatus(
                  humanizeStatus(
                    (event.step as string) ??
                      (event.message as string) ??
                      (event.status as string) ??
                      ""
                  )
                );
                break;
              case "source":
                callbacks.onSource(mapSource(event));
                break;
              case "token":
                callbacks.onToken(
                  (event.text as string) ?? (event.token as string) ?? ""
                );
                break;
              case "done":
                callbacks.onDone({
                  confidence: event.confidence as number | undefined,
                  trace_id: event.trace_id as string | undefined,
                  latency_ms: event.latency_ms as number | undefined,
                  cache_hit: event.cache_hit as boolean | undefined,
                  sources: Array.isArray(event.sources)
                    ? (event.sources as Record<string, unknown>[]).map(
                        mapSource
                      )
                    : undefined,
                });
                break;
              case "error":
                callbacks.onError(
                  (event.message as string) ?? "Unknown error from server"
                );
                break;
            }
          } catch {
            // non-JSON lines are silently ignored
          }
        }
      }
    } catch (err) {
      const e = err as Error;
      if (e.name === "AbortError") return;
      // Network-level failures (server down, DNS, CORS preflight failure)
      // surface as generic `TypeError: Failed to fetch` — translate to
      // something a user can act on instead of leaking the raw browser error.
      const friendly =
        e.name === "TypeError"
          ? "Unable to connect to the server. Please try again."
          : (e.message ?? "Connection failed");
      callbacks.onError(friendly);
    }
  })();

  return controller;
}

export async function query(text: string): Promise<QueryResponse> {
  const res = await fetch(`${apiUrl}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: text }),
  });
  if (!res.ok) throw new Error(`Query failed: ${res.status}`);
  return res.json() as Promise<QueryResponse>;
}

export async function healthCheck(): Promise<HealthResponse> {
  const res = await fetch(`${apiUrl}/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json() as Promise<HealthResponse>;
}

export async function getCacheStats(): Promise<CacheStats> {
  const res = await fetch(`${apiUrl}/api/cache/stats`);
  if (!res.ok) throw new Error("Cache stats failed");
  return res.json() as Promise<CacheStats>;
}

export async function clearCache(): Promise<void> {
  const res = await fetch(`${apiUrl}/api/cache`, { method: "DELETE" });
  if (!res.ok) throw new Error("Clear cache failed");
}
