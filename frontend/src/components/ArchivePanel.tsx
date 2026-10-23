import { BookOpenIcon, LockIcon, SearchIcon } from "lucide-react";
import { useState } from "react";
import type { DocumentBody, DocumentId, GameId, SearchHit } from "@/api";
import { useGame, useSearch } from "@/game/hooks";
import { AccuseDialog } from "./AccuseDialog";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardTitle } from "./ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./ui/dialog";
import { Input } from "./ui/input";

export function ArchivePanel({ gameId }: { gameId: GameId }) {
  const { view, perform, busy } = useGame(gameId);
  const { hits, pending, search } = useSearch(gameId);
  const [query, setQuery] = useState("");
  const [reading, setReading] = useState<DocumentBody | null>(null);

  async function open(document: DocumentId) {
    const opened = await perform({ kind: "open", document });
    if (opened.ok) setReading(opened.value.document);
  }

  return (
    <div className="flex flex-col gap-4">
      <Card aria-label="Archive search">
        <CardTitle>Archive</CardTitle>
        <form
          role="search"
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (query.trim()) search(query.trim());
          }}
        >
          <Input
            aria-label="Search the archive"
            placeholder="Search the archive"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
            }}
          />
          <Button type="submit" variant="outline" disabled={pending}>
            <SearchIcon />
            Search
          </Button>
        </form>
        {hits && <Hits hits={hits} busy={busy} onOpen={(id) => void open(id)} />}
      </Card>

      <Card aria-label="Documents">
        <CardTitle>Documents</CardTitle>
        <ul className="flex flex-col divide-y divide-stone-100">
          {view.documents.map((d) => (
            <li key={d.id} className="flex items-center gap-3 py-2">
              {d.opened ? (
                <BookOpenIcon className="size-4 shrink-0 text-stone-500" aria-hidden />
              ) : (
                <LockIcon className="size-4 shrink-0 text-stone-500" aria-label="Sealed" />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{d.title}</p>
                <p className="truncate text-xs text-stone-500">{d.source}</p>
              </div>
              <Button
                size="sm"
                variant={d.opened ? "ghost" : "outline"}
                disabled={busy}
                aria-label={`${d.opened ? "Read" : "Open"} ${d.title}`}
                onClick={() => void open(d.id)}
              >
                {d.opened ? "Read" : "Open"}
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <AccuseDialog gameId={gameId} />

      <Dialog
        open={reading !== null}
        onOpenChange={(open) => {
          if (!open) setReading(null);
        }}
      >
        <DialogContent>
          {reading && (
            <>
              <DialogTitle>{reading.title}</DialogTitle>
              <DialogDescription>{reading.source}</DialogDescription>
              <p className="text-sm leading-relaxed whitespace-pre-line text-stone-800">
                {reading.body}
              </p>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Hits({
  hits,
  busy,
  onOpen,
}: {
  hits: readonly SearchHit[];
  busy: boolean;
  onOpen: (id: DocumentId) => void;
}) {
  if (hits.length === 0) return <p className="text-sm text-stone-500">No matching documents.</p>;
  return (
    <ul aria-label="Search results" className="flex flex-col gap-2">
      {hits.map((h) => (
        <li key={h.document} className="rounded-md border border-stone-200 p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-medium">{h.title}</p>
              <Badge variant="outline" className="mt-1">
                {h.source}
              </Badge>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              aria-label={`Open ${h.title}`}
              onClick={() => {
                onOpen(h.document);
              }}
            >
              Open
            </Button>
          </div>
          <p className="mt-2 text-sm text-stone-700">
            {h.highlight.map((span, i) =>
              span.marked ? (
                <mark key={i} className="rounded bg-amber-200 px-0.5">
                  {span.text}
                </mark>
              ) : (
                <span key={i}>{span.text}</span>
              ),
            )}
          </p>
        </li>
      ))}
    </ul>
  );
}
