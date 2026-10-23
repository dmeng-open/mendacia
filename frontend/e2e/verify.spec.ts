import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { detective, walk } from "./detective";
import { CASES, WALKTHROUGHS, type CaseName, type Step } from "./walkthroughs";

const caseId = process.env.VERIFY_CASE as CaseName | undefined;

test("verify: play a case and capture evidence", async ({ page }, info) => {
  test.skip(!caseId, "set VERIFY_CASE to one of " + CASES.join(", "));
  if (!caseId) return;
  const steps = process.env.VERIFY_STEPS
    ? (JSON.parse(readFileSync(process.env.VERIFY_STEPS, "utf8")) as Step[])
    : WALKTHROUGHS[caseId];
  const out = resolve(process.env.VERIFY_OUT ?? "e2e/.out", info.project.name);
  mkdirSync(out, { recursive: true });
  const shot = (name: string) => page.screenshot({ path: resolve(out, `${name}.png`) });
  const taken = new Set<string>();
  const once = async (name: string) => {
    if (taken.has(name)) return;
    taken.add(name);
    await shot(name);
  };

  const delay = Number(process.env.VERIFY_FRAME_DELAY_MS ?? "0");
  if (delay > 0) {
    await page.routeWebSocket(/\/ask$/, (ws) => {
      const server = ws.connectToServer();
      let queue = Promise.resolve();
      server.onMessage((message) => {
        queue = queue
          .then(() => new Promise((resolve) => setTimeout(resolve, delay)))
          .then(() => {
            ws.send(message);
          });
      });
    });
  }

  const d = detective(page);
  await d.start(caseId);
  await shot("start");
  let n = 0;
  const walked = await walk(d, steps, {
    whileStreaming: () => once("chat-streaming"),
    beforeConfirm: () => once("accuse"),
    afterStep: async (step) => {
      n += 1;
      const kind = Object.keys(step)[0] ?? "step";
      await shot(`${String(n).padStart(2, "0")}-${kind}`);
      if (kind === "ask") await once("chat-reply");
      if (kind === "search") await once("archive-highlight");
    },
  });
  if (walked.ruling) await shot("reveal");
  console.log(JSON.stringify({ out, ruling: walked.ruling, asks: walked.asks }, null, 2));
  expect(walked.asks.length + walked.searches.length).toBeGreaterThan(0);
});
