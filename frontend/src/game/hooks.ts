import { QueryClient, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { toast } from "sonner";
import {
  api,
  GameProblem,
  type Action,
  type ActionValue,
  type AskRequest,
  type GameId,
  type GameView,
  type Outcome,
  type Problem,
  type SearchHit,
  type ValueOf,
} from "@/api";
import { record } from "./journal";
import { IDLE, settle, step, type Turn } from "./turn";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: Infinity } },
});

const gameKey = (gameId: GameId) => ["game", gameId] as const;

export const gameQuery = (gameId: GameId) => ({
  queryKey: gameKey(gameId),
  queryFn: () => api.view(gameId),
});

function announce(problem: Problem): void {
  const wait = problem.retryAfterS ? ` (${problem.retryAfterS}s)` : "";
  toast.error(problem.message + wait);
}

export interface GameHandle {
  readonly view: GameView;
  /** Runs one action at the cached state_version, replaces the cached view, toasts problems. */
  readonly perform: <A extends Action>(action: A) => Promise<Outcome<ValueOf<A>>>;
  readonly busy: boolean;
}

export function useGame(gameId: GameId): GameHandle {
  const client = useQueryClient();
  const { data: view } = useSuspenseQuery(gameQuery(gameId));
  const [inFlight, setInFlight] = useState(0);

  const perform = useCallback(
    async <A extends Action>(action: A): Promise<Outcome<ValueOf<A>>> => {
      const before = client.getQueryData<GameView>(gameKey(gameId)) ?? view;
      setInFlight((n) => n + 1);
      try {
        const outcome = await api.perform(gameId, action, before.stateVersion);
        if (!outcome.ok) {
          announce(outcome.problem);
          await client.invalidateQueries({ queryKey: gameKey(gameId) });
          return outcome;
        }
        client.setQueryData(gameKey(gameId), outcome.view);
        if (action.kind === "hint" && !outcome.replayed) {
          record(gameId, { type: "hint", hint: (outcome.value as ActionValue["hint"]).hint });
        }
        if (action.kind === "accuse") {
          const suspect = before.suspects.find((s) => s.id === action.suspect);
          const cited = before.clues.filter((c) => action.cited.includes(c.id));
          if (suspect) record(gameId, { type: "accused", suspect, cited });
        }
        return outcome;
      } finally {
        setInFlight((n) => n - 1);
      }
    },
    [client, gameId, view],
  );

  return { view, perform, busy: inFlight > 0 };
}

export interface AskHandle {
  readonly turn: Turn;
  /** Ignored unless the turn is idle. */
  readonly ask: (request: AskRequest) => void;
}

export function useAsk(gameId: GameId): AskHandle {
  const client = useQueryClient();
  const [turn, setTurn] = useState<Turn>(IDLE);
  const live = useRef<Turn>(IDLE);
  const channel = useRef(api.ask(gameId));

  useEffect(() => {
    const c = channel.current;
    return () => {
      c.close();
    };
  }, []);

  const ask = useCallback(
    (request: AskRequest) => {
      if (live.current.phase !== "idle") return;
      const advance = (next: Turn) => {
        live.current = next;
        // Commit every frame, so "checking" paints before the first chunk replaces it.
        flushSync(() => {
          setTurn(next);
        });
      };
      advance(step(IDLE, { type: "sent", request }));
      const version = client.getQueryData<GameView>(gameKey(gameId))?.stateVersion ?? 0;
      void (async () => {
        for await (const frame of channel.current.turn(request, version)) {
          const before = live.current;
          if (frame.type === "done" && before.phase !== "idle") {
            record(gameId, { type: "exchange", exchange: settle(before, frame) });
            void client.invalidateQueries({ queryKey: gameKey(gameId) });
          }
          advance(step(before, frame));
        }
      })();
    },
    [client, gameId],
  );

  return { turn, ask };
}

export interface SearchHandle {
  readonly hits: readonly SearchHit[] | null;
  readonly pending: boolean;
  readonly search: (query: string) => void;
}

export function useSearch(gameId: GameId): SearchHandle {
  const [hits, setHits] = useState<readonly SearchHit[] | null>(null);
  const [pending, setPending] = useState(false);
  const search = useCallback(
    (query: string) => {
      setPending(true);
      api
        .search(gameId, query)
        .then(setHits, (e: unknown) => {
          if (e instanceof GameProblem) announce(e.problem);
          else throw e;
        })
        .finally(() => {
          setPending(false);
        });
    },
    [gameId],
  );
  return { hits, pending, search };
}
