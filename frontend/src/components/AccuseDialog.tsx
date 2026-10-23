import { GavelIcon } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import type { ClueId, GameId, SuspectId } from "@/api";
import { useGame } from "@/game/hooks";
import { Button, buttonVariants } from "./ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "./ui/dialog";

export function AccuseDialog({ gameId }: { gameId: GameId }) {
  const { view, perform, busy } = useGame(gameId);
  const navigate = useNavigate();
  const [suspect, setSuspect] = useState<SuspectId | null>(null);
  const [cited, setCited] = useState<readonly ClueId[]>([]);

  if (view.accused) {
    return (
      <Link to={`/play/${gameId}/reveal`} className={buttonVariants({ size: "lg" })}>
        See the reveal
      </Link>
    );
  }

  async function accuse() {
    if (!suspect) return;
    const result = await perform({ kind: "accuse", suspect, cited });
    if (result.ok) await navigate(`/play/${gameId}/reveal`);
  }

  return (
    <Dialog>
      <DialogTrigger render={<Button variant="destructive" size="lg" />}>
        <GavelIcon />
        Accuse
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>Make your accusation</DialogTitle>
        <DialogDescription>
          You get one accusation. Name the culprit and cite the clues that prove it.
        </DialogDescription>
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-sm font-medium">Who did it?</legend>
          {view.suspects.map((s) => (
            <label key={s.id} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="suspect"
                checked={suspect === s.id}
                onChange={() => {
                  setSuspect(s.id);
                }}
              />
              {s.name}
            </label>
          ))}
        </fieldset>
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-sm font-medium">Cite your clues</legend>
          {view.clues.length === 0 && (
            <p className="text-sm text-stone-500">You have not found any clues yet.</p>
          )}
          {view.clues.map((c) => (
            <label key={c.id} className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={cited.includes(c.id)}
                onChange={(e) => {
                  setCited(e.target.checked ? [...cited, c.id] : cited.filter((x) => x !== c.id));
                }}
              />
              {c.description}
            </label>
          ))}
        </fieldset>
        <Button variant="destructive" disabled={!suspect || busy} onClick={() => void accuse()}>
          Accuse
        </Button>
      </DialogContent>
    </Dialog>
  );
}
