import { LightbulbIcon } from "lucide-react";
import type { GameId, SuspectId } from "@/api";
import { useGame } from "@/game/hooks";
import { useJournal } from "@/game/journal";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardTitle } from "./ui/card";

export function CasePanel({
  gameId,
  suspect,
  onSelect,
}: {
  gameId: GameId;
  suspect: SuspectId | null;
  onSelect: (suspect: SuspectId) => void;
}) {
  const { view, perform, busy } = useGame(gameId);
  const { hints } = useJournal(gameId);

  return (
    <div className="flex flex-col gap-4">
      <Card aria-label="Case">
        <h1 className="text-xl font-semibold text-stone-900">{view.title}</h1>
        <p className="text-sm leading-relaxed text-stone-700">{view.summary}</p>
        <div className="flex flex-wrap gap-2" aria-label="Budget">
          <Badge variant="muted">{view.questionsLeft} questions left</Badge>
          <Badge variant="muted">{view.hintsLeft} hints left</Badge>
        </div>
      </Card>

      <Card aria-label="Suspects">
        <CardTitle>Suspects</CardTitle>
        <ul className="flex flex-col gap-1">
          {view.suspects.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                aria-pressed={s.id === suspect}
                onClick={() => {
                  onSelect(s.id);
                }}
                className={cn(
                  "w-full rounded-md px-3 py-2 text-left hover:bg-stone-100",
                  s.id === suspect && "bg-stone-900 text-stone-50 hover:bg-stone-800",
                )}
              >
                <span className="block text-sm font-medium">{s.name}</span>
                <span
                  className={cn(
                    "block text-xs",
                    s.id === suspect ? "text-stone-300" : "text-stone-500",
                  )}
                >
                  {s.description}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Card>

      <Card aria-label="Clues">
        <CardTitle>Clues</CardTitle>
        {view.clues.length === 0 ? (
          <p className="text-sm text-stone-500">Nothing yet. Ask, search, and read.</p>
        ) : (
          <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
            {view.clues.map((c) => (
              <li key={c.id}>{c.description}</li>
            ))}
          </ul>
        )}
      </Card>

      <Card aria-label="Hints">
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Hints</CardTitle>
          <Button
            variant="outline"
            size="sm"
            disabled={busy || view.hintsLeft === 0 || view.accused}
            onClick={() => void perform({ kind: "hint" })}
          >
            <LightbulbIcon />
            Take a hint
          </Button>
        </div>
        {hints.length > 0 && (
          <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm">
            {hints.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
