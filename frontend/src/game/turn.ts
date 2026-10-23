import {
  PLAYER_MESSAGES,
  type AskRequest,
  type Clue,
  type ClueId,
  type DocumentId,
  type DoneFrame,
  type ProblemCode,
  type SuspectId,
  type TurnFrame,
} from "@/api";

/** The live ask. `idle` is the only phase in which the composer is enabled. */
export type Turn =
  | { readonly phase: "idle" }
  | { readonly phase: "sending"; readonly request: AskRequest }
  | { readonly phase: "thinking"; readonly request: AskRequest }
  | { readonly phase: "checking"; readonly request: AskRequest }
  | { readonly phase: "streaming"; readonly request: AskRequest; readonly text: string };

export type LiveTurn = Exclude<Turn, { phase: "idle" }>;

export type TurnInput = { readonly type: "sent"; readonly request: AskRequest } | TurnFrame;

export const IDLE: Turn = { phase: "idle" };

/** A frame that cannot occur in a phase is ignored, never thrown on. */
export function step(turn: Turn, input: TurnInput): Turn {
  if (input.type === "done") return IDLE;
  if (turn.phase === "idle") {
    return input.type === "sent" ? { phase: "sending", request: input.request } : turn;
  }
  const { request } = turn;
  switch (input.type) {
    case "sent":
      return turn;
    case "thinking":
      return turn.phase === "sending" ? { phase: "thinking", request } : turn;
    case "validating":
      return turn.phase === "streaming" ? turn : { phase: "checking", request };
    case "chunk":
      return {
        phase: "streaming",
        request,
        text: (turn.phase === "streaming" ? turn.text : "") + input.text,
      };
  }
}

export type Reply =
  | { readonly kind: "answer"; readonly text: string; readonly newClues: readonly Clue[] }
  /** No question was spent. `text` is the in-character line when the server sent one. */
  | { readonly kind: "refused"; readonly code: ProblemCode; readonly text: string };

export interface Exchange {
  readonly suspect: SuspectId;
  readonly question: string;
  readonly presented: readonly ClueId[];
  readonly documents: readonly DocumentId[];
  readonly reply: Reply;
}

export function settle(turn: LiveTurn, done: DoneFrame): Exchange {
  const streamed = turn.phase === "streaming" ? turn.text : "";
  const reply: Reply =
    done.code === null
      ? { kind: "answer", text: streamed, newClues: done.newClues }
      : { kind: "refused", code: done.code, text: streamed || PLAYER_MESSAGES[done.code] };
  return {
    suspect: turn.request.suspect,
    question: turn.request.question,
    presented: turn.request.present,
    documents: turn.request.documents,
    reply,
  };
}
