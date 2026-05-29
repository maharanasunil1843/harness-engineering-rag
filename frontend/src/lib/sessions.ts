import type { Message, Session } from "./types";

export type { Message, Session };

const STORAGE_KEY = "harness-rag-sessions";

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

// In-memory fallback used when localStorage throws (quota exceeded, private
// browsing mode with storage disabled). Sessions still work for the lifetime
// of the tab — they just don't persist across reloads.
let _memoryFallback: Session[] | null = null;

function _readRaw(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function _writeRaw(sessions: Session[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    _memoryFallback = null;
  } catch {
    // QuotaExceededError, SecurityError, etc. — degrade silently.
    _memoryFallback = sessions;
  }
}

export function getSessions(): Session[] {
  if (typeof window === "undefined") return [];
  if (_memoryFallback) return _memoryFallback;
  try {
    const raw = _readRaw();
    if (!raw) return [];
    return JSON.parse(raw) as Session[];
  } catch {
    return [];
  }
}

export function getSession(id: string): Session | null {
  return getSessions().find((s) => s.id === id) ?? null;
}

export function createSession(): Session {
  const session: Session = {
    id: generateId(),
    title: "New Chat",
    messages: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  const sessions = getSessions();
  sessions.unshift(session);
  _writeRaw(sessions);
  return session;
}

export function updateSession(id: string, messages: Message[]): void {
  const sessions = getSessions();
  const idx = sessions.findIndex((s) => s.id === id);
  if (idx === -1) return;
  const firstUserMsg = messages.find((m) => m.role === "user");
  const title = firstUserMsg
    ? firstUserMsg.content.slice(0, 60)
    : sessions[idx].title;
  sessions[idx] = { ...sessions[idx], title, messages, updatedAt: Date.now() };
  _writeRaw(sessions);
}

export function deleteSession(id: string): void {
  const updated = getSessions().filter((s) => s.id !== id);
  _writeRaw(updated);
}

export function clearSessions(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignored — degraded mode
  }
  _memoryFallback = null;
}
