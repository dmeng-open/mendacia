import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { expect, type Page } from "@playwright/test";
import type { Step } from "./walkthroughs";

type Panel = "Case" | "Chat" | "Archive";

export interface AskResult {
  readonly reply: string;
  /** Every turn phase the chat painted, in order. */
  readonly phases: readonly string[];
  /** Ask to first painted chunk, from the `ask:first-chunk` measure ChatPanel records. */
  readonly firstChunkMs: number | null;
}

declare global {
  interface Window {
    __turnPhases: string[];
  }
}

/** Records each `data-turn-phase` the page paints, so a phase that lasts one frame is still seen. */
function watchPhases() {
  window.__turnPhases = [];
  const seen = () => {
    const el = document.querySelector("[data-turn-phase]");
    const phase = el?.getAttribute("data-turn-phase");
    if (phase && window.__turnPhases.at(-1) !== phase) window.__turnPhases.push(phase);
  };
  new MutationObserver(seen).observe(document, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ["data-turn-phase"],
  });
}

/** Player verbs by role and accessible name. Works at desktop and phone widths. */
export function detective(page: Page) {
  void page.addInitScript(watchPhases);

  async function show(panel: Panel) {
    const tabs = page.getByRole("tablist", { name: "Panels" });
    if (await tabs.isVisible()) await tabs.getByRole("tab", { name: panel }).click();
  }

  const transcript = () => page.getByRole("list", { name: "Transcript" }).locator(":scope > li");

  return {
    page,
    show,

    /** Opens `/?case=<id>` and waits for the case. Returns the game id. */
    async start(caseId: string): Promise<string> {
      await page.goto(`/?case=${caseId}`);
      await page.waitForURL(/\/play\/[^/]+$/);
      await expect(page.getByRole("region", { name: "Case" }).getByRole("heading")).toBeVisible();
      return page.url().split("/").at(-1) ?? "";
    },

    async ask(suspect: string, question: string): Promise<AskResult> {
      await show("Case");
      await page
        .getByRole("region", { name: "Suspects" })
        .getByRole("button", { name: suspect })
        .click();
      await show("Chat");
      const before = await transcript().count();
      await page.evaluate(() => {
        window.__turnPhases = [];
      });
      await page.getByLabel("Your question").fill(question);
      await page.getByRole("button", { name: "Ask", exact: true }).click();
      await expect(page.locator("[data-turn-phase]")).toHaveCount(0, { timeout: 45_000 });
      await expect(transcript()).toHaveCount(before + 1);
      const reply = await transcript().last().locator(":scope > div").nth(1).innerText();
      const { phases, firstChunkMs } = await page.evaluate(() => ({
        phases: window.__turnPhases,
        firstChunkMs:
          performance.getEntriesByName("ask:first-chunk", "measure").at(-1)?.duration ?? null,
      }));
      return { reply, phases, firstChunkMs };
    },

    /** Returns the hit titles and how many passages carry a highlight. */
    async search(query: string): Promise<{ titles: string[]; marks: number }> {
      await show("Archive");
      await page.getByRole("searchbox", { name: "Search the archive" }).fill(query);
      await page.getByRole("button", { name: "Search", exact: true }).click();
      const results = page.getByRole("list", { name: "Search results" });
      await expect(results).toBeVisible();
      const titles = await results.locator(":scope > li p.font-medium").allInnerTexts();
      return { titles, marks: await results.locator("mark").count() };
    },

    /** Opens or rereads a visible document and returns its body. */
    async open(title: string): Promise<string> {
      await show("Archive");
      const docs = page.getByRole("region", { name: "Documents" });
      await docs
        .getByRole("button", { name: new RegExp(`^(Open|Read) ${escape(title)}$`) })
        .click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("heading", { name: title })).toBeVisible();
      const body = await dialog.locator("p").last().innerText();
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      return body;
    },

    async hint(): Promise<string> {
      await show("Case");
      const hints = page.getByRole("region", { name: "Hints" }).getByRole("listitem");
      const before = await hints.count();
      await page.getByRole("button", { name: "Take a hint" }).click();
      await expect(hints).toHaveCount(before + 1);
      return hints.last().innerText();
    },

    async clues(): Promise<string[]> {
      await show("Case");
      return page.getByRole("region", { name: "Clues" }).getByRole("listitem").allInnerTexts();
    },

    async visibleDocuments(): Promise<string[]> {
      await show("Archive");
      return page
        .getByRole("region", { name: "Documents" })
        .locator("p.font-medium")
        .allInnerTexts();
    },

    /** Accuses, waits for the reveal page, and returns the ruling. */
    async accuse(suspect: string, clues: readonly string[] | "all"): Promise<string> {
      await show("Archive");
      await page.getByRole("button", { name: "Accuse" }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("radio", { name: suspect }).check();
      const boxes = dialog.getByRole("checkbox");
      for (const box of await boxes.all()) {
        const label = (await box.locator("xpath=..").innerText()).trim();
        if (clues === "all" || clues.includes(label)) await box.check();
      }
      await dialog.getByRole("button", { name: "Accuse" }).click();
      await page.waitForURL(/\/reveal$/);
      const ruling = page.getByRole("region", { name: "Ruling" }).locator("p").first();
      await expect(ruling).toBeVisible();
      return (await ruling.innerText()).trim();
    },
  };
}

export type Detective = ReturnType<typeof detective>;

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export interface Walked {
  readonly asks: AskResult[];
  readonly searches: { titles: string[]; marks: number }[];
  readonly ruling: string | null;
}

/** Plays a walkthrough. `beforeAccuse` runs at the last moment before the accusation. */
export async function walk(
  d: Detective,
  steps: readonly Step[],
  beforeAccuse?: () => Promise<void>,
): Promise<Walked> {
  const out: Walked = { asks: [], searches: [], ruling: null };
  let ruling: string | null = null;
  for (const step of steps) {
    if ("ask" in step) out.asks.push(await d.ask(step.ask.suspect, step.ask.question));
    else if ("search" in step) out.searches.push(await d.search(step.search));
    else if ("hint" in step) await d.hint();
    else if ("open" in step) await d.open(step.open);
    else {
      await beforeAccuse?.();
      ruling = await d.accuse(step.accuse.suspect, step.accuse.clues);
    }
  }
  return { ...out, ruling };
}

export interface Traffic {
  /** Every `/games/` response body and every WebSocket frame sent before the first /reveal request. */
  bodies(): Promise<string[]>;
}

export function recordTraffic(page: Page): Traffic {
  let open = true;
  const pending: Promise<string | null>[] = [];
  const frames: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/reveal")) open = false;
  });
  page.on("response", (r) => {
    if (!open || !new URL(r.url()).pathname.startsWith("/games")) return;
    pending.push(r.text().catch(() => null));
  });
  page.on("websocket", (ws) => {
    const keep = (f: { payload: string | Buffer }) => {
      if (open) frames.push(f.payload.toString());
    };
    ws.on("framesent", keep);
    ws.on("framereceived", keep);
  });
  return {
    async bodies() {
      const texts = (await Promise.all(pending)).filter((t): t is string => t !== null);
      return [...texts, ...frames];
    },
  };
}

const BACKEND = resolve(import.meta.dirname, "../../backend");
const LEAKED = `
import json, sys
from engine.schema import Case
from tests.api.conftest import ROOT, leaked
case = Case.model_validate_json((ROOT / "cases" / f"{sys.argv[1]}.json").read_text())
print(json.dumps(leaked(case, json.load(open(sys.argv[2])))))
`;

/** The backend's own leak matcher (tests/api/conftest.py), so there is one forbidden-token list. */
export function leaked(caseId: string, bodies: readonly string[]): [string, string][] {
  const file = join(mkdtempSync(join(tmpdir(), "mendacia-leak-")), "bodies.json");
  writeFileSync(file, JSON.stringify(bodies));
  const out = execFileSync("uv", ["run", "--quiet", "python", "-c", LEAKED, caseId, file], {
    cwd: BACKEND,
    env: { ...process.env, LLM_MODE: "replay", SESSION_SECRET: "leak-check" },
    encoding: "utf8",
  });
  return JSON.parse(out) as [string, string][];
}
