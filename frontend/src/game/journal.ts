import { useCallback, useSyncExternalStore } from "react";
import type { Clue, GameId, Suspect } from "@/api";
import type { Exchange } from "./turn";

export interface Journal {
  readonly schema: 1;
  readonly exchanges: readonly Exchange[];
  readonly hints: readonly string[];
  readonly accusation: { readonly suspect: Suspect; readonly cited: readonly Clue[] } | null;
}

export type JournalEvent =
  | { readonly type: "exchange"; readonly exchange: Exchange }
  | { readonly type: "hint"; readonly hint: string }
  | { readonly type: "accused"; readonly suspect: Suspect; readonly cited: readonly Clue[] };

export const EMPTY_JOURNAL: Journal = { schema: 1, exchanges: [], hints: [], accusation: null };

export function applyJournal(journal: Journal, event: JournalEvent): Journal {
  switch (event.type) {
    case "exchange":
      return { ...journal, exchanges: [...journal.exchanges, event.exchange] };
    case "hint":
      return { ...journal, hints: [...journal.hints, event.hint] };
    case "accused":
      return journal.accusation
        ? journal
        : { ...journal, accusation: { suspect: event.suspect, cited: event.cited } };
  }
}

export function loadJournal(raw: string | null): Journal {
  if (!raw) return EMPTY_JOURNAL;
  try {
    const parsed = JSON.parse(raw) as Partial<Journal> | null;
    if (parsed?.schema !== 1 || !Array.isArray(parsed.exchanges) || !Array.isArray(parsed.hints)) {
      return EMPTY_JOURNAL;
    }
    return { ...EMPTY_JOURNAL, ...parsed };
  } catch {
    return EMPTY_JOURNAL;
  }
}

const storageKey = (gameId: GameId) => `mendacia:journal:${gameId}`;
const journals = new Map<GameId, Journal>();
const listeners = new Set<() => void>();

function current(gameId: GameId): Journal {
  let journal = journals.get(gameId);
  if (!journal) {
    try {
      journal = loadJournal(sessionStorage.getItem(storageKey(gameId)));
    } catch {
      journal = EMPTY_JOURNAL;
    }
    journals.set(gameId, journal);
  }
  return journal;
}

export function record(gameId: GameId, event: JournalEvent): void {
  const next = applyJournal(current(gameId), event);
  journals.set(gameId, next);
  try {
    sessionStorage.setItem(storageKey(gameId), JSON.stringify(next));
  } catch {
    // Storage can be full or disabled; the journal then lives in memory for this tab.
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useJournal(gameId: GameId): Journal {
  const snapshot = useCallback(() => current(gameId), [gameId]);
  return useSyncExternalStore(subscribe, snapshot);
}
