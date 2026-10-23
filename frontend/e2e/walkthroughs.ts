export type Step =
  | { readonly ask: { readonly suspect: string; readonly question: string } }
  | { readonly search: string }
  | { readonly hint: true }
  | { readonly open: string }
  | { readonly accuse: { readonly suspect: string; readonly clues: "all" } };

export const CASES = ["manor", "gallery", "lighthouse"] as const;
export type CaseName = (typeof CASES)[number];

export const WALKTHROUGHS: Record<CaseName, readonly Step[]> = {
  manor: [
    { ask: { suspect: "Mrs. Pike", question: "Where were you at 10pm?" } },
    { ask: { suspect: "Mrs. Pike", question: "Whom did you see at 10pm?" } },
    { search: "empty velvet case in the dressing table" },
    { hint: true },
    { open: "Garden pavilion visitors' book" },
    { accuse: { suspect: "Clara Ashcombe", clues: "all" } },
  ],
  gallery: [
    { open: "Security desk memo" },
    { open: "East hall camera log" },
    { open: "Catering invoice" },
    { ask: { suspect: "Theo Vance", question: "Where were you at 7pm?" } },
    { ask: { suspect: "Pia Lund", question: "Whom did you see at 7pm?" } },
    { search: "a second copy of the footage is kept at the security desk" },
    { hint: true },
    { accuse: { suspect: "Sam Okafor", clues: "all" } },
  ],
  lighthouse: [
    { ask: { suspect: "Nell Trask", question: "Where were you at 9pm?" } },
    { search: "when was high water on Thursday" },
    { hint: true },
    { open: "Boathouse ledger" },
    { accuse: { suspect: "Mr. Quill", clues: "all" } },
  ],
};
