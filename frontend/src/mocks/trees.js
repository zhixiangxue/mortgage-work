/* Client folder tree: files map to viewer docs via `doc`.
   Flat by default — LOs organize however they like; anything can live here
   (doc PDFs, chat screenshots, call transcripts). AI output goes to ai/ as .ai
   files (plain markdown under the hood). */
export const CLIENT_TREE = [
  { name: "PROFILE.md", type: "md", doc: "profile", git: "mod" },
  { name: "income", type: "dir", open: true, children: [
    { name: "paystub-2026-06.pdf", type: "pdf", doc: "paystub" },
    { name: "paystub-2026-07.pdf", type: "pdf", doc: "paystub" },
    { name: "w2-2025.pdf", type: "pdf", doc: "paystub" },
  ]},
  { name: "assets", type: "dir", open: true, children: [
    { name: "boa-statement-jun.pdf", type: "pdf", doc: "paystub" },
    { name: "boa-statement-jul.pdf", type: "pdf", doc: "paystub", git: "new" },
  ]},
  { name: "credit", type: "dir", children: [
    { name: "credit-report.pdf", type: "pdf", doc: "paystub" },
  ]},
  { name: "notes", type: "dir", children: [
    { name: "sms-screenshot-0714.png", type: "img" },
    { name: "call-transcript-0715.txt", type: "txt" },
    { name: "intro-thread.eml", type: "eml" },
  ]},
  { name: "ai", type: "dir", open: true, children: [
    { name: "missing-docs.ai", type: "ai", doc: "missing", git: "mod" },
    { name: "income-analysis.ai", type: "ai", doc: "income", git: "mod" },
    { name: "urla-1003-draft.pdf", type: "pdf", doc: "paystub", git: "new" },
  ]},
];

/* Product library: LO drops lender docs here, organized however they like */
export const PRODUCT_TREE = [
  { name: "UWM", type: "dir", open: true, children: [
    { name: "conventional-matrix.pdf", type: "pdf", doc: "guideline" },
    { name: "rate-sheet-07-28.pdf", type: "pdf", doc: "guideline", idx: "indexing" },
  ]},
  { name: "Rocket TPO", type: "dir", children: [
    { name: "jumbo-guidelines.pdf", type: "pdf", doc: "guideline" },
  ]},
  { name: "A&D Mortgage", type: "dir", open: true, children: [
    { name: "non-qm-bank-statement.pdf", type: "pdf", doc: "guideline" },
    { name: "dscr-matrix.pdf", type: "pdf", doc: "guideline", idx: "failed" },
  ]},
  { name: "FHA - VA", type: "dir", children: [
    { name: "fha-handbook-4000.1.pdf", type: "pdf", doc: "guideline" },
  ]},
];

/* Scaffolded folder for freshly created clients (instead of Sarah's demo data) */
export function freshClientTree(c) {
  return [
    { name: "PROFILE.md", type: "md", doc: "p_" + c.id, git: "new" },
    { name: "income", type: "dir", children: [] },
    { name: "assets", type: "dir", children: [] },
    { name: "credit", type: "dir", children: [] },
    { name: "ai", type: "dir", children: [] },
  ];
}
