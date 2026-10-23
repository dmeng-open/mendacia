import { describe, expect, it } from "vitest";
import {
  createApi,
  parseHighlight,
  parseProblem,
  type DocumentId,
  type GameId,
  type SuspectId,
  type TurnFrame,
} from "./api";

const GAME = "g1" as GameId;

function wireView(version: number) {
  return {
    game_id: GAME,
    title: "Death at Ashcombe Manor",
    summary: "",
    time_slots: [],
    suspects: [],
    documents: [],
    clues: [],
    questions_left: 20,
    hints_left: 3,
    state_version: version,
    accused: false,
  };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Sent {
  method: string;
  path: string;
  key: string | null;
  body: unknown;
}

/** A fake server: each request is answered by the next handler in order. */
function server(...handlers: ((sent: Sent) => Response | Error)[]) {
  const sent: Sent[] = [];
  const fetch = async (input: RequestInfo | URL): Promise<Response> => {
    const req = input as Request;
    const text = await req.text();
    const s: Sent = {
      method: req.method,
      path: new URL(req.url).pathname,
      key: req.headers.get("Idempotency-Key"),
      body: text ? JSON.parse(text) : null,
    };
    sent.push(s);
    const handler = handlers.shift();
    if (!handler) throw new Error(`unexpected ${s.method} ${s.path}`);
    const out = handler(s);
    if (out instanceof Error) throw out;
    return out;
  };
  return { sent, api: createApi({ baseUrl: "http://test", fetch }) };
}

const hint = (version: number) => ({
  view: wireView(version),
  text: "Look at the pavilion.",
  new_clues: [],
  replayed: false,
});

describe("perform", () => {
  it("resends a stale action once with the same key at the fresh version", async () => {
    const { sent, api } = server(
      () => json(409, { code: "stale_state", message: "The game moved on." }),
      () => json(200, wireView(5)),
      () => json(200, hint(6)),
    );
    const outcome = await api.perform(GAME, { kind: "hint" }, 3);
    expect(outcome).toMatchObject({ ok: true, value: { hint: "Look at the pavilion." } });
    expect(outcome.ok && outcome.view.stateVersion).toBe(6);
    const posts = sent.filter((s) => s.method === "POST");
    expect(posts.map((p) => p.body)).toEqual([{ state_version: 3 }, { state_version: 5 }]);
    expect(posts[0]?.key).toMatch(/^[0-9a-f]{32}$/);
    expect(posts[1]?.key).toBe(posts[0]?.key);
  });

  it("gives up after one stale retry", async () => {
    const stale = () => json(409, { code: "stale_state", message: "moved" });
    const { sent, api } = server(stale, () => json(200, wireView(5)), stale);
    const outcome = await api.perform(GAME, { kind: "hint" }, 3);
    expect(outcome).toMatchObject({ ok: false, problem: { code: "stale_state" } });
    expect(sent).toHaveLength(3);
  });

  it("retries a dropped request with the same key, then reports network", async () => {
    const { sent, api } = server(
      () => new TypeError("fetch failed"),
      () => new TypeError("fetch failed"),
    );
    const outcome = await api.perform(
      GAME,
      { kind: "open", document: "pavilion_visitors_book" as DocumentId },
      0,
    );
    expect(outcome).toMatchObject({ ok: false, problem: { code: "network" } });
    expect(sent.map((s) => s.path)).toEqual([
      "/games/g1/documents/pavilion_visitors_book/open",
      "/games/g1/documents/pavilion_visitors_book/open",
    ]);
    expect(sent[1]?.key).toBe(sent[0]?.key);
  });

  it("each intent mints its own key", async () => {
    const { sent, api } = server(
      () => json(200, hint(1)),
      () => json(200, hint(2)),
    );
    await api.perform(GAME, { kind: "hint" }, 0);
    await api.perform(GAME, { kind: "hint" }, 1);
    expect(sent[0]?.key).not.toBe(sent[1]?.key);
  });
});

describe("parseProblem", () => {
  it("keeps the server's player-safe message", () => {
    expect(parseProblem({ code: "cooldown", message: "Wait.", retry_after_s: 9 })).toEqual({
      code: "cooldown",
      message: "Wait.",
      retryAfterS: 9,
    });
  });
  it("turns an unknown body into unavailable", () => {
    expect(parseProblem({ detail: "Not Found" }).code).toBe("unavailable");
    expect(parseProblem("<html>").code).toBe("unavailable");
  });
});

describe("parseHighlight", () => {
  it.each([
    ["plain text", [{ text: "plain text", marked: false }]],
    [
      "an [[empty]] velvet [[case]]",
      [
        { text: "an ", marked: false },
        { text: "empty", marked: true },
        { text: " velvet ", marked: false },
        { text: "case", marked: true },
      ],
    ],
    [
      "[[<b>]] stays text",
      [
        { text: "<b>", marked: true },
        { text: " stays text", marked: false },
      ],
    ],
    ["broken [[marker", [{ text: "broken [[marker", marked: false }]],
  ])("%s", (raw, spans) => {
    expect(parseHighlight(raw)).toEqual(spans);
  });
});

type Script = (socket: FakeSocket, frame: Record<string, unknown>) => void;

class FakeSocket {
  static readonly OPEN = 1;
  static script: Script[] = [];
  static instances: FakeSocket[] = [];
  readyState = 0;
  readonly sent: Record<string, unknown>[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = FakeSocket.OPEN;
      this.onopen?.();
    });
  }
  send(data: string) {
    const frame = JSON.parse(data) as Record<string, unknown>;
    this.sent.push(frame);
    const next = FakeSocket.script.shift();
    if (!next) throw new Error("unexpected frame");
    queueMicrotask(() => {
      next(this, frame);
    });
  }
  emit(...frames: object[]) {
    for (const f of frames) this.onmessage?.({ data: JSON.stringify(f) });
  }
  drop(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
  close() {
    this.readyState = 3;
  }
}

const doneWire = (fields: object = {}) => ({
  type: "done",
  questions_left: 19,
  state_version: 1,
  new_clues: [],
  code: null,
  replayed: false,
  retry_after_s: null,
  ...fields,
});

async function runTurn(api: ReturnType<typeof createApi>, version = 0): Promise<TurnFrame[]> {
  const frames: TurnFrame[] = [];
  const request = {
    suspect: "h_1" as SuspectId,
    question: "Where were you at 10pm?",
    present: [],
    documents: [],
  };
  for await (const f of api.ask(GAME).turn(request, version)) frames.push(f);
  return frames;
}

function socketApi(script: Script[], fetchHandlers: (() => Response)[] = []) {
  FakeSocket.script = script;
  FakeSocket.instances = [];
  return createApi({
    baseUrl: "http://test",
    fetch: () => {
      const h = fetchHandlers.shift();
      if (!h) throw new Error("unexpected fetch");
      return Promise.resolve(h());
    },
    WebSocket: FakeSocket as unknown as typeof WebSocket,
    askUrl: (id) => `ws://test/games/${id}/ask`,
  });
}

describe("ask channel", () => {
  it("reopens a dropped socket and resends the turn with the same key", async () => {
    const api = socketApi([
      (s) => {
        s.emit({ type: "thinking" });
        s.drop();
      },
      (s) => {
        s.emit({ type: "thinking" }, { type: "chunk", text: "In the kitchen." }, doneWire());
      },
    ]);
    const frames = await runTurn(api);
    expect(frames.map((f) => f.type)).toEqual(["thinking", "thinking", "chunk", "done"]);
    const [first, second] = FakeSocket.instances;
    expect(second?.sent[0]?.idempotency_key).toBe(first?.sent[0]?.idempotency_key);
  });

  it("ends the turn with exactly one done when the socket drops twice", async () => {
    const api = socketApi([
      (s) => {
        s.drop();
      },
      (s) => {
        s.drop();
      },
    ]);
    const frames = await runTurn(api);
    expect(frames).toHaveLength(1);
    expect(frames[0]).toMatchObject({ type: "done", code: "network" });
  });

  it("maps a 4403 close to denied", async () => {
    const api = socketApi([
      (s) => {
        s.drop(4403);
      },
    ]);
    expect(await runTurn(api)).toMatchObject([{ type: "done", code: "denied" }]);
  });

  it("resends a stale turn with the same key at the fresh version", async () => {
    const api = socketApi(
      [
        (s) => {
          s.emit({ type: "thinking" }, doneWire({ code: "stale_state", questions_left: null }));
        },
        (s) => {
          s.emit({ type: "thinking" }, doneWire());
        },
      ],
      [() => json(200, wireView(4))],
    );
    const frames = await runTurn(api, 2);
    expect(frames.filter((f) => f.type === "done")).toHaveLength(1);
    const sent = FakeSocket.instances[0]?.sent ?? [];
    expect(sent.map((f) => f.state_version)).toEqual([2, 4]);
    expect(sent[1]?.idempotency_key).toBe(sent[0]?.idempotency_key);
  });
});
