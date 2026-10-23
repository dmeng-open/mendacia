import { SendIcon, ShieldCheckIcon } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { MAX_QUESTION, type ClueId, type DocumentId, type GameId, type SuspectId } from "@/api";
import { useAsk, useGame } from "@/game/hooks";
import { useJournal } from "@/game/journal";
import type { Exchange, Turn } from "@/game/turn";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardTitle } from "./ui/card";
import { Textarea } from "./ui/input";

export function ChatPanel({ gameId, suspect }: { gameId: GameId; suspect: SuspectId | null }) {
  const { view } = useGame(gameId);
  const { exchanges } = useJournal(gameId);
  const { turn, ask } = useAsk(gameId);
  const [question, setQuestion] = useState("");
  const [present, setPresent] = useState<readonly ClueId[]>([]);
  const [documents, setDocuments] = useState<readonly DocumentId[]>([]);
  useFirstChunkMark(turn);

  const who = view.suspects.find((s) => s.id === suspect);
  const history = exchanges.filter((e) => e.suspect === suspect);
  const live = turn.phase !== "idle" && turn.request.suspect === suspect ? turn : null;
  const opened = view.documents.filter((d) => d.opened);
  const canAsk =
    !!who && turn.phase === "idle" && view.questionsLeft > 0 && !view.accused && !!question.trim();

  function submit(e: { preventDefault: () => void }) {
    e.preventDefault();
    if (!who || !canAsk) return;
    performance.mark("ask:sent");
    ask({ suspect: who.id, question: question.trim(), present, documents });
    setQuestion("");
    setPresent([]);
    setDocuments([]);
  }

  return (
    <Card aria-label="Conversation" className="min-h-[60dvh]">
      <CardTitle>{who ? who.name : "Choose a suspect"}</CardTitle>
      {who && <p className="-mt-2 text-xs text-stone-500">{who.description}</p>}

      <ol className="flex flex-1 flex-col gap-3 overflow-y-auto" aria-label="Transcript">
        {history.map((e, i) => (
          <ExchangeView key={i} exchange={e} name={who?.name ?? ""} />
        ))}
        {live && (
          <li className="flex flex-col gap-2">
            <Bubble from="you">{live.request.question}</Bubble>
            <LiveReply turn={live} name={who?.name ?? ""} />
          </li>
        )}
      </ol>

      {who && (
        <form onSubmit={submit} className="flex flex-col gap-2 border-t border-stone-200 pt-3">
          {(view.clues.length > 0 || opened.length > 0) && (
            <fieldset className="flex flex-wrap gap-1">
              <legend className="mb-1 text-xs text-stone-500">Present evidence (optional)</legend>
              {view.clues.map((c) => (
                <Toggle
                  key={c.id}
                  on={present.includes(c.id)}
                  onClick={() => {
                    setPresent(flip(present, c.id));
                  }}
                >
                  {c.description}
                </Toggle>
              ))}
              {opened.map((d) => (
                <Toggle
                  key={d.id}
                  on={documents.includes(d.id)}
                  onClick={() => {
                    setDocuments(flip(documents, d.id));
                  }}
                >
                  {d.title}
                </Toggle>
              ))}
            </fieldset>
          )}
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <div className="flex items-end gap-2">
            <Textarea
              id="question"
              placeholder={`Ask ${who.name} something`}
              value={question}
              maxLength={MAX_QUESTION}
              onChange={(e) => {
                setQuestion(e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) submit(e);
              }}
            />
            <Button type="submit" disabled={!canAsk}>
              <SendIcon />
              Ask
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function ExchangeView({ exchange, name }: { exchange: Exchange; name: string }) {
  const { reply } = exchange;
  return (
    <li className="flex flex-col gap-2">
      <Bubble from="you">{exchange.question}</Bubble>
      {reply.kind === "answer" ? (
        <Bubble from={name}>
          {reply.text}
          {reply.newClues.map((c) => (
            <Badge key={c.id} className="mt-2 block w-fit">
              New clue: {c.description}
            </Badge>
          ))}
        </Bubble>
      ) : (
        <Bubble from={name} muted>
          {reply.text}
          <span className="mt-1 block text-xs text-stone-500">No question was spent.</span>
        </Bubble>
      )}
    </li>
  );
}

function LiveReply({ turn, name }: { turn: Exclude<Turn, { phase: "idle" }>; name: string }) {
  return (
    <div data-turn-phase={turn.phase} aria-live="polite">
      {turn.phase === "streaming" ? (
        <Bubble from={name}>{turn.text}</Bubble>
      ) : turn.phase === "checking" ? (
        <p className="flex items-center gap-2 text-sm text-stone-500">
          <ShieldCheckIcon className="size-4 animate-pulse" />
          Checking the reply against the facts…
        </p>
      ) : (
        <p className="text-sm text-stone-500">{name} is thinking…</p>
      )}
    </div>
  );
}

function Bubble({ from, muted, children }: { from: string; muted?: boolean; children: ReactNode }) {
  const you = from === "you";
  return (
    <div
      className={cn(
        "max-w-[85%] rounded-lg px-3 py-2 text-sm",
        you ? "self-end bg-stone-900 text-stone-50" : "self-start bg-stone-100 text-stone-900",
        muted && "italic",
      )}
    >
      <span className="sr-only">{you ? "You: " : `${from}: `}</span>
      {children}
    </div>
  );
}

function Toggle({
  on,
  onClick,
  children,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "max-w-full truncate rounded-full border px-2 py-0.5 text-xs",
        on ? "border-stone-900 bg-stone-900 text-stone-50" : "border-stone-300 text-stone-700",
      )}
    >
      {children}
    </button>
  );
}

function flip<T>(list: readonly T[], item: T): readonly T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

/** e2e reads the `ask:first-chunk` measure: time from Ask to the first painted chunk. */
function useFirstChunkMark(turn: Turn) {
  const marked = useRef(false);
  useEffect(() => {
    if (turn.phase === "streaming" && !marked.current) {
      marked.current = true;
      performance.mark("ask:first-chunk");
      performance.measure("ask:first-chunk", "ask:sent", "ask:first-chunk");
    } else if (turn.phase === "idle") {
      marked.current = false;
    }
  }, [turn.phase]);
}
