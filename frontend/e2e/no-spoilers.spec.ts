import { expect, test } from "@playwright/test";
import { detective, leaked, recordTraffic, walk } from "./detective";
import { CASES, WALKTHROUGHS } from "./walkthroughs";

for (const caseId of CASES) {
  test(`${caseId}: nothing before the reveal names the solution`, async ({ page }) => {
    const traffic = recordTraffic(page);
    const d = detective(page);
    await d.start(caseId);
    const screens: string[] = [];
    const walked = await walk(d, WALKTHROUGHS[caseId], async () => {
      screens.push(
        await page.evaluate(() => document.body.innerText),
        await page.evaluate(() => JSON.stringify(Object.entries(sessionStorage))),
      );
    });
    expect(walked.ruling, "the walkthrough reached the accusation").not.toBeNull();
    expect(walked.asks.length).toBeGreaterThan(0);

    const bodies = await traffic.bodies();
    expect(bodies.some((b) => b.includes('"type":"chunk"'))).toBe(true);
    expect(bodies.some((b) => b.includes('"correct"'))).toBe(true);
    expect(leaked(caseId, [...bodies, ...screens])).toEqual([]);
  });
}

test("the leak matcher catches a culprit id (negative control)", () => {
  expect(leaked("manor", ['{"suspect": "clara"}']).map(([token]) => token)).toEqual(["clara"]);
});
