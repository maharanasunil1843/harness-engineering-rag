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

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (!data || data === "[DONE]") continue;
          try {
            const event = JSON.parse(data) as Record<string, unknown>;
            switch (event.type) {
              case "status":
                callbacks.onStatus(
                  (event.message as string) ?? (event.status as string) ?? ""
                );
                break;
              case "source":
                callbacks.onSource((event.source as SourceInfo) ?? (event as unknown as SourceInfo));
                break;
              case "token":
                callbacks.onToken(
                  (event.token as string) ?? (event.text as string) ?? ""
                );
                break;
              case "done":
                callbacks.onDone({
                  confidence: event.confidence as number | undefined,
                  trace_id: event.trace_id as string | undefined,
                  latency_ms: event.latency_ms as number | undefined,
                  cache_hit: event.cache_hit as boolean | undefined,
                  sources: event.sources as SourceInfo[] | undefined,
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
