import { readdirSync } from "node:fs";
import { expect, it } from "vitest";
import { CASE_IDS } from "./cases";

it("CASE_IDS lists exactly the case files in cases/", () => {
  const files = readdirSync(new URL("../../../cases/", import.meta.url))
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""))
    .sort();
  expect([...CASE_IDS].sort()).toEqual(files);
});
