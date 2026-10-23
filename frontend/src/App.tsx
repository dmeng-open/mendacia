import { useState } from "react";
import {
  createBrowserRouter,
  Link,
  redirect,
  useParams,
  useRouteError,
  type LoaderFunctionArgs,
} from "react-router";
import { api, GameProblem, type GameId, type SuspectId } from "@/api";
import { CASE_IDS, isCaseId } from "@/game/cases";
import { gameQuery, queryClient, useGame } from "@/game/hooks";
import { cn } from "@/lib/utils";
import { ArchivePanel } from "./components/ArchivePanel";
import { CasePanel } from "./components/CasePanel";
import { ChatPanel } from "./components/ChatPanel";
import { RevealPage } from "./components/RevealPage";
import { buttonVariants } from "./components/ui/button";
import { Tabs, TabsList, TabsTab } from "./components/ui/tabs";

const PANELS = ["Case", "Chat", "Archive"] as const;
type Panel = (typeof PANELS)[number];

/** A loader, not an effect, creates the game, so StrictMode cannot create two. */
async function startGame({ request }: LoaderFunctionArgs) {
  const requested = new URL(request.url).searchParams.get("case");
  if (!isCaseId(requested)) return null;
  const view = await api.createGame(requested);
  queryClient.setQueryData(gameQuery(view.gameId).queryKey, view);
  return redirect(`/play/${view.gameId}`);
}

async function loadGame({ params }: LoaderFunctionArgs) {
  await queryClient.query({ ...gameQuery(params.gameId as GameId), staleTime: "static" });
  return null;
}

async function loadReveal({ params }: LoaderFunctionArgs) {
  try {
    return await api.reveal(params.gameId as GameId);
  } catch (e) {
    if (e instanceof GameProblem && e.problem.code === "not_accused") {
      return redirect(`/play/${params.gameId ?? ""}`);
    }
    throw e;
  }
}

export const router = createBrowserRouter([
  {
    errorElement: <ErrorView />,
    children: [
      { path: "/", loader: startGame, element: <StartPage /> },
      { path: "/play/:gameId", loader: loadGame, element: <PlayPage /> },
      { path: "/play/:gameId/reveal", loader: loadReveal, element: <RevealPage /> },
    ],
  },
]);

function StartPage() {
  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 p-6">
      <h1 className="text-3xl font-semibold">Mendacia</h1>
      <p className="text-stone-700">
        Every suspect lies to protect a secret. Question them, search the archive, and name the
        culprit.
      </p>
      <nav aria-label="Cases" className="flex flex-col gap-2">
        {CASE_IDS.map((id) => (
          <Link key={id} to={`/?case=${id}`} className={buttonVariants({ size: "lg" })}>
            Play {id[0]?.toUpperCase()}
            {id.slice(1)}
          </Link>
        ))}
      </nav>
    </main>
  );
}

function PlayPage() {
  const gameId = useParams().gameId as GameId;
  const { view } = useGame(gameId);
  const [suspect, setSuspect] = useState<SuspectId | null>(view.suspects[0]?.id ?? null);
  const [panel, setPanel] = useState<Panel>("Case");
  const shown = (p: Panel) => cn(panel !== p && "hidden", "md:block");

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-3 p-3 md:p-4">
      <header className="flex items-center justify-between">
        <Link to="/" className="text-sm font-semibold tracking-wide text-stone-500 uppercase">
          Mendacia
        </Link>
      </header>
      <Tabs
        value={panel}
        onValueChange={(v) => {
          setPanel(v as Panel);
        }}
        className="md:hidden"
      >
        <TabsList aria-label="Panels">
          {PANELS.map((p) => (
            <TabsTab key={p} value={p}>
              {p}
            </TabsTab>
          ))}
        </TabsList>
      </Tabs>
      <main className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className={shown("Case")}>
          <CasePanel
            gameId={gameId}
            suspect={suspect}
            onSelect={(s) => {
              setSuspect(s);
              setPanel("Chat");
            }}
          />
        </div>
        <div className={shown("Chat")}>
          <ChatPanel gameId={gameId} suspect={suspect} />
        </div>
        <div className={shown("Archive")}>
          <ArchivePanel gameId={gameId} />
        </div>
      </main>
    </div>
  );
}

function ErrorView() {
  const error = useRouteError();
  const problem = error instanceof GameProblem ? error.problem : null;
  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold">
        {problem?.code === "denied"
          ? "This game belongs to another browser session."
          : "Something went wrong."}
      </h1>
      {problem && problem.code !== "denied" && <p className="text-stone-700">{problem.message}</p>}
      <Link to="/" className={buttonVariants({ className: "self-start" })}>
        Start a new game
      </Link>
    </main>
  );
}
