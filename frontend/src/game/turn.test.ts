import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  PLAYER_MESSAGES,
  parseFrame,
  type AskRequest,
  type DoneFrame,
  type SuspectId,
  type TurnFrame,
} from "@/api";
import { IDLE, settle, step, type Exchange, type Turn } from "./turn";

const request: AskRequest = {
  suspect: "h_0000000000" as SuspectId,
  question: "Where were you at 10pm?",
  present: [],
  documents: [],
};

function done(fields: Partial<DoneFrame>): DoneFrame {
  return {
    type: "done",
    questionsLeft: 20,
    stateVersion: 0,
    newClues: [],
    code: null,
    replayed: false,
    retryAfterS: null,
    ...fields,
  };
}

/** Drives the reducer the way useAsk does and returns every phase plus the settled exchange. */
function play(frames: readonly TurnFrame[]): { phases: Turn["phase"][]; exchange: Exchange } {
  let turn = step(IDLE, { type: "sent", request });
  const phases: Turn["phase"][] = [turn.phase];
  let exchange: Exchange | null = null;
  for (const frame of frames) {
    if (frame.type === "done" && turn.phase !== "idle") exchange = settle(turn, frame);
    turn = step(turn, frame);
    phases.push(turn.phase);
  }
  if (!exchange) throw new Error("the turn never settled");
  return { phases, exchange };
}

const recorded = (
  JSON.parse(
    readFileSync(new URL("./__fixtures__/manor-first-ask.frames.json", import.meta.url), "utf8"),
  ) as string[]
).map(parseFrame);

describe("ask turn", () => {
  it("parses the recorded manor ask and settles it into an answer with its new clue", () => {
    const { phases, exchange } = play(recorded);
    expect(phases.slice(0, 4)).toEqual(["sending", "thinking", "checking", "streaming"]);
    expect(phases.at(-1)).toBe("idle");
    expect(exchange.reply).toEqual({
      kind: "answer",
      text: "I was in the kitchen at ten o'clock, detective, with the kettle on and the bread rising. Ask me anything you like about my own movements and I'll answer plainly.",
      newClues: [
        {
          id: "h_6d20713f2f",
          description: "Mrs. Pike was in the kitchen at 10pm, plating the late supper.",
        },
      ],
    });
    const last = recorded.at(-1);
    expect(last?.type === "done" && last.questionsLeft).toBe(19);
  });

  it.each([
    {
      name: "screened input keeps the in-character line",
      frames: [
        { type: "thinking" },
        { type: "chunk", text: "I don't follow you, Detective." },
        done({ code: "screened" }),
      ],
      text: "I don't follow you, Detective.",
      code: "screened",
    },
    {
      name: "cooldown has no chunks, so it gets the player-safe message",
      frames: [{ type: "thinking" }, done({ code: "cooldown", retryAfterS: 42 })],
      text: PLAYER_MESSAGES.cooldown,
      code: "cooldown",
    },
    {
      name: "unavailable after checking",
      frames: [{ type: "thinking" }, { type: "validating" }, done({ code: "unavailable" })],
      text: PLAYER_MESSAGES.unavailable,
      code: "unavailable",
    },
    {
      name: "a lost socket ends the turn with a network refusal",
      frames: [done({ code: "network", questionsLeft: null, stateVersion: null })],
      text: PLAYER_MESSAGES.network,
      code: "network",
    },
  ] satisfies { name: string; frames: TurnFrame[]; text: string; code: string }[])(
    "refusal spends nothing: $name",
    ({ frames, text, code }) => {
      const { phases, exchange } = play(frames);
      expect(exchange.reply).toEqual({ kind: "refused", code, text });
      expect(phases.at(-1)).toBe("idle");
    },
  );

  it("ignores the second thinking frame a stale retry produces", () => {
    const { phases, exchange } = play([
      { type: "thinking" },
      { type: "thinking" },
      { type: "validating" },
      { type: "chunk", text: "Yes." },
      done({ questionsLeft: 19 }),
    ]);
    expect(phases).toEqual(["sending", "thinking", "thinking", "checking", "streaming", "idle"]);
    expect(exchange.reply).toMatchObject({ kind: "answer", text: "Yes." });
  });

  it("only an idle turn accepts a new question", () => {
    const busy = step(IDLE, { type: "sent", request });
    expect(step(busy, { type: "sent", request: { ...request, question: "again" } })).toBe(busy);
    expect(step(IDLE, { type: "chunk", text: "stray" })).toBe(IDLE);
  });
});
