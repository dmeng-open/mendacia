import { expect, test } from "@playwright/test";
import { detective } from "./detective";

test("a replayed manor game from start to reveal", async ({ page }) => {
  const d = detective(page);
  await d.start("manor");
  await expect(page.getByText("20 questions left")).toBeVisible();
  const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
  expect(await fits(), "no horizontal scroll").toBe(true);

  const first = await d.ask("Mrs. Pike", "Where were you at 10pm?");
  expect(first.reply).toContain("I was in the kitchen at ten o'clock");
  expect(first.phases.indexOf("checking")).toBeGreaterThanOrEqual(0);
  expect(first.phases.indexOf("checking")).toBeLessThan(first.phases.indexOf("streaming"));

  const second = await d.ask("Mrs. Pike", "Whom did you see at 10pm?");
  expect(second.phases).toContain("checking");
  expect(second.firstChunkMs, "Ask to first chunk, ms").not.toBeNull();
  expect(second.firstChunkMs).toBeLessThanOrEqual(300);
  test
    .info()
    .annotations.push({ type: "first-chunk-ms", description: String(second.firstChunkMs) });
  await d.show("Case");
  await expect(page.getByText("18 questions left")).toBeVisible();

  const hits = await d.search("empty velvet case in the dressing table");
  expect(hits.titles[0]).toBe("Housekeeper's note on the letter opener case");
  expect(hits.marks).toBeGreaterThan(0);

  expect(await d.hint()).toContain("pavilion");
  expect(await d.open("Garden pavilion visitors' book")).toContain("Finch");
  expect(await d.clues()).toHaveLength(3);

  expect(await d.accuse("Clara Ashcombe", "all")).toBe("Correct.");
  const timeline = page.getByRole("region", { name: "Timeline" });
  await expect(timeline.getByRole("heading", { name: "Timeline" })).toBeVisible();
  expect(await timeline.getByRole("listitem").count()).toBeGreaterThan(0);
  expect(await fits(), "no horizontal scroll on the reveal").toBe(true);
  await expect(page.getByText("You cited 3 of the 3 clues in the solution chain.")).toBeVisible();
});
