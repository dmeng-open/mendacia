import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { expect, type Page } from "@playwright/test";
import { FIRST_CHUNK } from "../src/game/marks";
import type { Step } from "./walkthroughs";

type Panel = "Case" | "Chat" | "Archive";

export interface AskResult {
  readonly reply: string;
  readonly phases: readonly string[];
  readonly firstChunkMs: number | null;
}

declare global {
  interface Window {
    __turnPhases: string[];
  }
}

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

    async start(caseId: string): Promise<string> {
      await page.goto(`/?case=${caseId}`);
      await page.waitForURL(/\/play\/[^/]+$/);
      await expect(page.getByRole("region", { name: "Case" }).getByRole("heading")).toBeVisible();
      return page.url().split("/").at(-1) ?? "";
    },

    async ask(
      suspect: string,
      question: string,
      whileStreaming?: () => Promise<void>,
    ): Promise<AskResult> {
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
      if (whileStreaming) {
        const settled = await page.waitForFunction(
          () => {
            const p = document.querySelector("[data-turn-phase]")?.getAttribute("data-turn-phase");
            return p === "streaming" ? p : p ? false : "done";
          },
          undefined,
          { timeout: 45_000, polling: "raf" },
        );
        if ((await settled.jsonValue()) === "streaming") await whileStreaming();
      }
      await expect(page.locator("[data-turn-phase]")).toHaveCount(0, { timeout: 45_000 });
      await expect(transcript()).toHaveCount(before + 1);
      const reply = await transcript().last().locator(":scope > div").nth(1).innerText();
      const { phases, firstChunkMs } = await page.evaluate(
        (mark) => ({
          phases: window.__turnPhases,
          firstChunkMs: performance.getEntriesByName(mark, "measure").at(-1)?.duration ?? null,
        }),
        FIRST_CHUNK,
      );
      return { reply, phases, firstChunkMs };
    },

    async search(query: string): Promise<{ titles: string[]; marks: number }> {
      await show("Archive");
      await page.getByRole("searchbox", { name: "Search the archive" }).fill(query);
      await page.getByRole("button", { name: "Search", exact: true }).click();
      const results = page.getByRole("list", { name: "Search results" });
      await expect(results).toBeVisible();
      const titles = await results.locator(":scope > li p.font-medium").allInnerTexts();
      return { titles, marks: await results.locator("mark").count() };
    },

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

    async accuse(
      suspect: string,
      clues: readonly string[] | "all",
      beforeConfirm?: () => Promise<void>,
    ): Promise<string> {
      await show("Archive");
      await page.getByRole("button", { name: "Accuse" }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("radio", { name: suspect }).check();
      const boxes = dialog.getByRole("checkbox");
      for (const box of await boxes.all()) {
        const label = (await box.locator("xpath=..").innerText()).trim();
        if (clues === "all" || clues.includes(label)) await box.check();
      }
      await beforeConfirm?.();
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

export interface WalkHooks {
  readonly whileStreaming?: (step: Step) => Promise<void>;
  readonly beforeConfirm?: () => Promise<void>;
  readonly afterStep?: (step: Step) => Promise<void>;
}

export async function walk(
  d: Detective,
  steps: readonly Step[],
  hooks: WalkHooks = {},
): Promise<Walked> {
  const asks: AskResult[] = [];
  const searches: { titles: string[]; marks: number }[] = [];
  let ruling: string | null = null;
  for (const step of steps) {
    if ("ask" in step) {
      const streaming =
        hooks.whileStreaming && (() => hooks.whileStreaming?.(step) ?? Promise.resolve());
      asks.push(await d.ask(step.ask.suspect, step.ask.question, streaming));
    } else if ("search" in step) searches.push(await d.search(step.search));
    else if ("hint" in step) await d.hint();
    else if ("open" in step) await d.open(step.open);
    else ruling = await d.accuse(step.accuse.suspect, step.accuse.clues, hooks.beforeConfirm);
    await hooks.afterStep?.(step);
  }
  return { asks, searches, ruling };
}

export interface Traffic {
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
case = Case.model_validate_json((ROOT / sys.argv[1]).read_text())
print(json.dumps(leaked(case, json.load(open(sys.argv[2])))))
`;

/** `casePath` is a case file relative to the repository root, or a hand-written case id. */
export function leaked(casePath: string, bodies: readonly string[]): [string, string][] {
  const path = casePath.endsWith(".json") ? casePath : `cases/${casePath}.json`;
  const file = join(mkdtempSync(join(tmpdir(), "mendacia-leak-")), "bodies.json");
  writeFileSync(file, JSON.stringify(bodies));
  const out = execFileSync("uv", ["run", "--quiet", "python", "-c", LEAKED, path, file], {
    cwd: BACKEND,
    env: { ...process.env, LLM_MODE: "replay", SESSION_SECRET: "leak-check" },
    encoding: "utf8",
  });
  return JSON.parse(out) as [string, string][];
}
