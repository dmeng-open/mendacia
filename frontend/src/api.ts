import createClient from "openapi-fetch";
import type { components, paths } from "./api-types";

type Wire = components["schemas"];

declare const brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [brand]: B };

export type GameId = Brand<string, "GameId">;
export type SuspectId = Brand<string, "SuspectId">;
export type ClueId = Brand<string, "ClueId">;
export type DocumentId = Brand<string, "DocumentId">;
export type CaseId = Brand<string, "CaseId">;
export type IdempotencyKey = Brand<string, "IdempotencyKey">;

export type ReasonCode = Wire["Problem"]["code"];
export type ProblemCode = ReasonCode | "network";

export interface Problem {
  readonly code: ProblemCode;
  readonly message: string;
  readonly retryAfterS: number | null;
}

export const PLAYER_MESSAGES: Readonly<Record<ProblemCode, string>> = {
  bad_request: "That request is malformed.",
  denied: "That is not your game.",
  not_visible: "You cannot see that yet.",
  no_questions_left: "You have no questions left.",
  no_hints_left: "You have no hints left.",
  already_accused: "You have already made your accusation.",
  not_accused: "The solution is revealed only after your accusation.",
  stale_state: "The game moved on. Reload and try again.",
  screened: "I don't follow you, Detective.",
  cooldown: "Take a moment before you ask again.",
  budget_exhausted: "That is enough of that for this game.",
  unavailable: "The house is quiet for a moment. Nothing was spent; try again.",
  network: "The connection dropped. Try again; nothing is spent twice.",
};

export interface Suspect {
  readonly id: SuspectId;
  readonly name: string;
  readonly description: string;
}
export interface Clue {
  readonly id: ClueId;
  readonly description: string;
}
export interface DocumentRef {
  readonly id: DocumentId;
  readonly title: string;
  readonly source: string;
  readonly opened: boolean;
}
export interface DocumentBody {
  readonly id: DocumentId;
  readonly title: string;
  readonly source: string;
  readonly body: string;
}

export interface GameView {
  readonly gameId: GameId;
  readonly title: string;
  readonly summary: string;
  readonly timeSlots: readonly string[];
  readonly suspects: readonly Suspect[];
  readonly documents: readonly DocumentRef[];
  readonly clues: readonly Clue[];
  readonly questionsLeft: number;
  readonly hintsLeft: number;
  readonly stateVersion: number;
  readonly accused: boolean;
}

export interface HighlightSpan {
  readonly text: string;
  readonly marked: boolean;
}

export interface SearchHit {
  readonly document: DocumentId;
  readonly title: string;
  readonly source: string;
  readonly highlight: readonly HighlightSpan[];
}

export interface CaseSummary {
  readonly id: CaseId;
  readonly title: string;
  readonly summary: string;
}

export interface Reveal {
  readonly ruling: string;
  readonly correct: boolean;
  readonly chain: readonly string[];
  readonly citedChain: readonly string[];
  readonly timeline: readonly string[];
}

export type Action =
  | { readonly kind: "open"; readonly document: DocumentId }
  | { readonly kind: "hint" }
  | { readonly kind: "accuse"; readonly suspect: SuspectId; readonly cited: readonly ClueId[] };

export interface ActionValue {
  open: { readonly document: DocumentBody; readonly newClues: readonly Clue[] };
  hint: { readonly hint: string };
  accuse: { readonly correct: boolean; readonly ruling: string };
}
export type ValueOf<A extends Action> = ActionValue[A["kind"]];

export type Outcome<T> =
  | { readonly ok: true; readonly view: GameView; readonly value: T; readonly replayed: boolean }
  | { readonly ok: false; readonly problem: Problem };

export interface AskRequest {
  readonly suspect: SuspectId;
  readonly question: string;
  readonly present: readonly ClueId[];
  readonly documents: readonly DocumentId[];
}

export type DoneFrame = {
  readonly type: "done";
  readonly questionsLeft: number | null;
  readonly stateVersion: number | null;
  readonly newClues: readonly Clue[];
  readonly code: ProblemCode | null;
  readonly replayed: boolean;
  readonly retryAfterS: number | null;
};

export type TurnFrame =
  | { readonly type: "thinking" }
  | { readonly type: "validating" }
  | { readonly type: "chunk"; readonly text: string }
  | DoneFrame;

export interface AskChannel {
  turn(request: AskRequest, stateVersion: number): AsyncIterable<TurnFrame>;
  close(): void;
}

export class GameProblem extends Error {
  constructor(readonly problem: Problem) {
    super(problem.message);
  }
}

export const MAX_QUESTION = 500;
const DENIED_CLOSE = 4403;
const REASON_CODES = new Set<string>(Object.keys(PLAYER_MESSAGES));

export function problemOf(code: ProblemCode, retryAfterS: number | null = null): Problem {
  return { code, message: PLAYER_MESSAGES[code], retryAfterS };
}

export function parseProblem(body: unknown): Problem {
  if (typeof body !== "object" || body === null) return problemOf("unavailable");
  const { code, message, retry_after_s } = body as Record<string, unknown>;
  if (typeof code !== "string" || !REASON_CODES.has(code)) return problemOf("unavailable");
  const known = code as ProblemCode;
  return {
    code: known,
    message: typeof message === "string" && message ? message : PLAYER_MESSAGES[known],
    retryAfterS: typeof retry_after_s === "number" ? retry_after_s : null,
  };
}

export function parseHighlight(raw: string): HighlightSpan[] {
  const spans: HighlightSpan[] = [];
  let rest = raw;
  while (rest) {
    const open = rest.indexOf("[[");
    const close = open < 0 ? -1 : rest.indexOf("]]", open + 2);
    if (open < 0 || close < 0) {
      spans.push({ text: rest, marked: false });
      break;
    }
    if (open > 0) spans.push({ text: rest.slice(0, open), marked: false });
    if (close > open + 2) spans.push({ text: rest.slice(open + 2, close), marked: true });
    rest = rest.slice(close + 2);
  }
  return spans;
}

function parseClue(wire: Wire["PublicClue"]): Clue {
  return { id: wire.id as ClueId, description: wire.description };
}

export function parseView(wire: Wire["GameView"]): GameView {
  return {
    gameId: wire.game_id as GameId,
    title: wire.title,
    summary: wire.summary,
    timeSlots: wire.time_slots,
    suspects: wire.suspects.map((s) => ({
      id: s.id as SuspectId,
      name: s.name,
      description: s.description,
    })),
    documents: wire.documents.map((d) => ({
      id: d.id as DocumentId,
      title: d.title,
      source: d.source,
      opened: d.opened,
    })),
    clues: wire.clues.map(parseClue),
    questionsLeft: wire.questions_left,
    hintsLeft: wire.hints_left,
    stateVersion: wire.state_version,
    accused: wire.accused,
  };
}

function parseValue<A extends Action>(action: A, wire: Wire["ActionResult"]): ValueOf<A> | null {
  const newClues = wire.new_clues.map(parseClue);
  const value = (): ActionValue[Action["kind"]] | null => {
    switch (action.kind) {
      case "open":
        return wire.document
          ? { document: { ...wire.document, id: wire.document.id as DocumentId }, newClues }
          : null;
      case "hint":
        return wire.text ? { hint: wire.text } : null;
      case "accuse":
        return typeof wire.correct === "boolean" && wire.text
          ? { correct: wire.correct, ruling: wire.text }
          : null;
    }
  };
  return value() as ValueOf<A> | null;
}

/** WebSocket frames are not in OpenAPI, so this is the one hand-written wire parser. */
export function parseFrame(raw: string): TurnFrame {
  const f = JSON.parse(raw) as Record<string, unknown>;
  const nullableNumber = (v: unknown): number | null => (typeof v === "number" ? v : null);
  switch (f.type) {
    case "thinking":
    case "validating":
      return { type: f.type };
    case "chunk":
      if (typeof f.text !== "string") break;
      return { type: "chunk", text: f.text };
    case "done": {
      const code = f.code === null || f.code === undefined ? null : f.code;
      if (code !== null && (typeof code !== "string" || !REASON_CODES.has(code))) break;
      const clues = Array.isArray(f.new_clues) ? (f.new_clues as Wire["PublicClue"][]) : [];
      return {
        type: "done",
        questionsLeft: nullableNumber(f.questions_left),
        stateVersion: nullableNumber(f.state_version),
        newClues: clues.map(parseClue),
        code: code as ProblemCode | null,
        replayed: f.replayed === true,
        retryAfterS: nullableNumber(f.retry_after_s),
      };
    }
  }
  throw new Error(`unexpected ask frame: ${raw.slice(0, 200)}`);
}

function mintKey(): IdempotencyKey {
  return crypto.randomUUID().replaceAll("-", "") as IdempotencyKey;
}

function doneWith(code: ProblemCode): DoneFrame {
  return {
    type: "done",
    questionsLeft: null,
    stateVersion: null,
    newClues: [],
    code,
    replayed: false,
    retryAfterS: null,
  };
}

type SocketEvent =
  | { readonly kind: "open" }
  | { readonly kind: "message"; readonly data: string }
  | { readonly kind: "close"; readonly code: number };

class Socket {
  private readonly events: SocketEvent[] = [];
  private waiting: ((e: SocketEvent) => void) | null = null;
  readonly ws: WebSocket;

  constructor(WS: typeof WebSocket, url: string) {
    this.ws = new WS(url);
    this.ws.onopen = () => {
      this.push({ kind: "open" });
    };
    this.ws.onmessage = (e: MessageEvent) => {
      this.push({ kind: "message", data: String(e.data) });
    };
    this.ws.onclose = (e: CloseEvent) => {
      this.push({ kind: "close", code: e.code });
    };
  }

  private push(e: SocketEvent): void {
    const w = this.waiting;
    if (w) {
      this.waiting = null;
      w(e);
    } else this.events.push(e);
  }

  next(): Promise<SocketEvent> {
    const e = this.events.shift();
    if (e) return Promise.resolve(e);
    return new Promise((resolve) => (this.waiting = resolve));
  }
}

export interface ApiOptions {
  readonly baseUrl?: string;
  readonly fetch?: typeof fetch;
  readonly WebSocket?: typeof WebSocket;
  readonly askUrl?: (gameId: GameId) => string;
}

function defaultAskUrl(gameId: GameId): string {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/games/${gameId}/ask`;
}

export function createApi(options: ApiOptions = {}) {
  const client = createClient<paths>({
    baseUrl: options.baseUrl ?? "",
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
  const WS = options.WebSocket ?? globalThis.WebSocket;
  const askUrl = options.askUrl ?? defaultAskUrl;

  async function read<T>(call: Promise<{ data?: T; error?: unknown }>): Promise<T> {
    let res: { data?: T; error?: unknown };
    try {
      res = await call;
    } catch {
      throw new GameProblem(problemOf("network"));
    }
    if (res.data === undefined) throw new GameProblem(parseProblem(res.error));
    return res.data;
  }

  async function view(gameId: GameId): Promise<GameView> {
    const params = { path: { game_id: gameId } };
    return parseView(await read(client.GET("/games/{game_id}", { params })));
  }

  function post(gameId: GameId, action: Action, version: number, key: IdempotencyKey) {
    const header = { "Idempotency-Key": key };
    switch (action.kind) {
      case "open":
        return client.POST("/games/{game_id}/documents/{doc_id}/open", {
          params: { path: { game_id: gameId, doc_id: action.document }, header },
          body: { state_version: version },
        });
      case "hint":
        return client.POST("/games/{game_id}/hint", {
          params: { path: { game_id: gameId }, header },
          body: { state_version: version },
        });
      case "accuse":
        return client.POST("/games/{game_id}/accuse", {
          params: { path: { game_id: gameId }, header },
          body: { state_version: version, suspect: action.suspect, cited: [...action.cited] },
        });
    }
  }

  async function attempt<A extends Action>(
    gameId: GameId,
    action: A,
    version: number,
    key: IdempotencyKey,
  ): Promise<Outcome<ValueOf<A>>> {
    let res;
    try {
      res = await post(gameId, action, version, key);
    } catch {
      try {
        res = await post(gameId, action, version, key);
      } catch {
        return { ok: false, problem: problemOf("network") };
      }
    }
    if (!res.data) return { ok: false, problem: parseProblem(res.error) };
    const value = parseValue(action, res.data);
    if (!value) return { ok: false, problem: problemOf("unavailable") };
    return { ok: true, view: parseView(res.data.view), value, replayed: res.data.replayed };
  }

  async function freshVersion(gameId: GameId): Promise<number | Problem> {
    try {
      return (await view(gameId)).stateVersion;
    } catch (e) {
      return e instanceof GameProblem ? e.problem : problemOf("network");
    }
  }

  function ask(gameId: GameId): AskChannel {
    let socket: Socket | null = null;
    let busy = false;

    async function connect(): Promise<Socket | "denied" | "failed"> {
      if (socket && socket.ws.readyState === WS.OPEN) return socket;
      socket?.ws.close();
      const s = new Socket(WS, askUrl(gameId));
      const first = await s.next();
      if (first.kind === "open") return (socket = s);
      return first.kind === "close" && first.code === DENIED_CLOSE ? "denied" : "failed";
    }

    async function* turn(request: AskRequest, stateVersion: number): AsyncGenerator<TurnFrame> {
      const key = mintKey();
      let version = stateVersion;
      let reconnected = false;
      let staleRetried = false;
      for (;;) {
        const s = await connect();
        if (s === "denied") {
          yield doneWith("denied");
          return;
        }
        if (s === "failed") {
          if (reconnected) {
            yield doneWith("network");
            return;
          }
          reconnected = true;
          continue;
        }
        s.ws.send(
          JSON.stringify({
            idempotency_key: key,
            state_version: version,
            suspect: request.suspect,
            question: request.question,
            present: request.present,
            documents: request.documents,
          }),
        );
        let resend = false;
        while (!resend) {
          const e = await s.next();
          if (e.kind === "open") continue;
          if (e.kind === "close") {
            socket = null;
            if (e.code === DENIED_CLOSE) {
              yield doneWith("denied");
              return;
            }
            if (reconnected) {
              yield doneWith("network");
              return;
            }
            reconnected = true;
            resend = true;
            continue;
          }
          let frame: TurnFrame;
          try {
            frame = parseFrame(e.data);
          } catch {
            s.ws.close();
            socket = null;
            yield doneWith("unavailable");
            return;
          }
          if (frame.type === "done" && frame.code === "stale_state" && !staleRetried) {
            staleRetried = true;
            const fresh = await freshVersion(gameId);
            if (typeof fresh !== "number") {
              yield doneWith(fresh.code);
              return;
            }
            version = fresh;
            resend = true;
            continue;
          }
          yield frame;
          if (frame.type === "done") return;
        }
      }
    }

    return {
      turn(request, stateVersion) {
        if (busy) throw new Error("one ask turn at a time");
        busy = true;
        const frames = turn(request, stateVersion);
        return {
          async *[Symbol.asyncIterator]() {
            try {
              yield* frames;
            } finally {
              busy = false;
            }
          },
        };
      },
      close() {
        socket?.ws.close();
        socket = null;
      },
    };
  }

  return {
    async listCases(): Promise<CaseSummary[]> {
      const cases = await read(client.GET("/cases"));
      return cases.map((c) => ({ id: c.id as CaseId, title: c.title, summary: c.summary }));
    },

    async createGame(caseId: CaseId): Promise<GameView> {
      return parseView(await read(client.POST("/games", { body: { case_id: caseId } })));
    },

    view,

    async search(gameId: GameId, query: string): Promise<SearchHit[]> {
      const params = { path: { game_id: gameId }, query: { q: query } };
      const hits = await read(client.GET("/games/{game_id}/search", { params }));
      return hits.map((h) => ({
        document: h.document_id as DocumentId,
        title: h.title,
        source: h.source,
        highlight: parseHighlight(h.highlight),
      }));
    },

    async perform<A extends Action>(
      gameId: GameId,
      action: A,
      stateVersion: number,
    ): Promise<Outcome<ValueOf<A>>> {
      const key = mintKey();
      const first = await attempt(gameId, action, stateVersion, key);
      if (first.ok || first.problem.code !== "stale_state") return first;
      const fresh = await freshVersion(gameId);
      if (typeof fresh !== "number") return { ok: false, problem: fresh };
      return attempt(gameId, action, fresh, key);
    },

    async reveal(gameId: GameId): Promise<Reveal> {
      const params = { path: { game_id: gameId } };
      const r = await read(client.GET("/games/{game_id}/reveal", { params }));
      return {
        ruling: r.ruling,
        correct: r.correct,
        chain: r.chain,
        citedChain: r.cited_chain,
        timeline: r.timeline,
      };
    },

    ask,
  } as const;
}

export type Api = ReturnType<typeof createApi>;

export const api: Api = createApi();
