import type { CaseId } from "@/api";

/** The playable cases until `GET /cases` lands (P4-2). A Vitest fails when cases/ drifts. */
export const CASE_IDS = ["gallery", "lighthouse", "manor"] as unknown as readonly CaseId[];

export const DEFAULT_CASE = "manor" as CaseId;

export function isCaseId(value: string | null): value is CaseId {
  return value !== null && (CASE_IDS as readonly string[]).includes(value);
}
