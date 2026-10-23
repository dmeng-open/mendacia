import { CheckCircle2Icon, XCircleIcon } from "lucide-react";
import { Link, useLoaderData, useParams } from "react-router";
import type { GameId, Reveal } from "@/api";
import { useJournal } from "@/game/journal";
import { buttonVariants } from "./ui/button";
import { Card, CardTitle } from "./ui/card";

export function RevealPage() {
  const reveal = useLoaderData<Reveal>();
  const gameId = useParams().gameId as GameId;
  const { accusation } = useJournal(gameId);

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
      <Card aria-label="Ruling">
        <p className="flex items-center gap-2 text-2xl font-semibold">
          {reveal.correct ? (
            <CheckCircle2Icon className="size-7 text-emerald-700" aria-hidden />
          ) : (
            <XCircleIcon className="size-7 text-red-700" aria-hidden />
          )}
          {reveal.ruling}
        </p>
        {accusation && <p className="text-sm">You accused {accusation.suspect.name}.</p>}
        <p className="text-sm text-stone-600">
          You cited {reveal.citedChain.length} of the {reveal.chain.length} clues in the solution
          chain.
        </p>
        {accusation && accusation.cited.length > 0 && (
          <>
            <CardTitle>Your cited clues</CardTitle>
            <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
              {accusation.cited.map((c) => (
                <li key={c.id}>{c.description}</li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card aria-label="Timeline">
        <CardTitle>Timeline</CardTitle>
        <ol className="flex flex-col gap-2 border-l-2 border-stone-300 pl-4 text-sm">
          {reveal.timeline.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ol>
      </Card>

      <Link to="/" className={buttonVariants({ variant: "outline", className: "self-start" })}>
        Play another case
      </Link>
    </main>
  );
}
