import { readFileSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { detective, leaked, recordTraffic } from "./detective";

interface CaseFile {
  readonly id: string;
  readonly culprit: string;
  readonly suspects: readonly { readonly id: string; readonly name: string }[];
  readonly time_slots: readonly string[];
  readonly facts: readonly {
    readonly id: string;
    readonly subject: string;
    readonly predicate: string;
    readonly time_slot: number | null;
  }[];
  readonly clues: readonly {
    readonly id: string;
    readonly description: string;
    readonly reveals: readonly string[];
    readonly doc_id: string | null;
  }[];
  readonly documents: readonly {
    readonly id: string;
    readonly title: string;
    readonly visibility: "open" | { readonly unlocked_by: readonly string[] };
  }[];
  readonly solution_chain: readonly string[];
}

const ROOT = resolve(import.meta.dirname, "../..");
const PATHS = process.env.CASE
  ? [isAbsolute(process.env.CASE) ? process.env.CASE : resolve(ROOT, process.env.CASE)]
  : ["gallery", "lighthouse", "manor"].map((n) => resolve(ROOT, "cases", `${n}.json`));

/** Documents to open, unlockers first, so every chain document becomes visible. */
function documentsToOpen(c: CaseFile): string[] {
  const docs = new Map(c.documents.map((d) => [d.id, d]));
  const order: string[] = [];
  const visit = (id: string) => {
    const doc = docs.get(id);
    if (!doc || order.includes(doc.title)) return;
    if (doc.visibility !== "open") {
      const unlocker = doc.visibility.unlocked_by.find((u) => docs.has(u));
      if (unlocker) visit(unlocker);
    }
    order.push(doc.title);
  };
  for (const clue of c.clues.filter((cl) => c.solution_chain.includes(cl.id))) {
    if (clue.doc_id) visit(clue.doc_id);
  }
  return order;
}

const ASKS: Record<string, string> = {
  at: "Where were you at",
  saw: "Whom did you see at",
  heard: "Did you hear anything at",
};

/** The question that asks a testimony clue's witness for its fact, by predicate. */
function questions(
  c: CaseFile,
  clues: CaseFile["clues"],
  predicates: readonly string[],
): { suspect: string; question: string }[] {
  const names = new Map(c.suspects.map((s) => [s.id, s.name]));
  return clues
    .filter((cl) => !cl.doc_id)
    .flatMap((cl) => c.facts.filter((f) => cl.reveals.includes(f.id)))
    .filter((f) => predicates.includes(f.predicate) && names.has(f.subject) && f.time_slot)
    .map((f) => ({
      suspect: names.get(f.subject) ?? "",
      question: `${ASKS[f.predicate] ?? ""} ${c.time_slots[(f.time_slot ?? 1) - 1] ?? ""}?`,
    }));
}

for (const path of PATHS) {
  const c = JSON.parse(readFileSync(path, "utf8")) as CaseFile;
  const chain = c.clues.filter((cl) => c.solution_chain.includes(cl.id));
  const culprit = c.suspects.find((s) => s.id === c.culprit)?.name ?? "";

  test(`${c.id}: play to the reveal by citing the solution chain`, async ({ page }) => {
    test.setTimeout(240_000);
    const traffic = recordTraffic(page);
    const d = detective(page);
    await d.start(c.id);
    const missing = async () => {
      const held = await d.clues();
      return chain.filter((cl) => !held.includes(cl.description));
    };
    for (const { suspect, question } of questions(c, chain, ["at"])) await d.ask(suspect, question);
    for (const title of documentsToOpen(c)) await d.open(title);
    for (let i = 0; i < chain.length && (await missing()).length > 0; i++) await d.hint();
    for (const { suspect, question } of questions(c, await missing(), ["saw", "heard", "at"])) {
      await d.ask(suspect, question);
    }
    expect(await d.clues()).toEqual(expect.arrayContaining(chain.map((cl) => cl.description)));

    const screens: string[] = [];
    const ruling = await d.accuse(culprit, "all", async () => {
      screens.push(await page.evaluate(() => document.body.innerText));
    });
    expect(ruling).toBe("Correct.");
    const bodies = await traffic.bodies();
    expect(leaked(relative(ROOT, path), [...bodies, ...screens])).toEqual([]);
  });
}
