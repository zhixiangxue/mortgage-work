/* Client folder tree: files map to viewer docs via `doc`.
   Flat by default — LOs organize however they like; anything can live here
   (doc PDFs, chat screenshots, call transcripts). AI output goes to ai/ as .ai
   files (plain markdown under the hood). */
export const CLIENT_TREE = [
  { name: "client.yaml", type: "md", doc: "clientmeta", git: "mod" },
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
    { name: "profile.ai", type: "ai", doc: "profile", git: "mod" },
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

/* A freshly created client: client.yaml + five advisory document buckets.
   The buckets are mortgage data-collection scaffolding — LOs can rename,
   delete, or reorganize them. clerk creates ai/ on its own once documents
   arrive, wherever they live in the tree. */
export function freshClientTree(c) {
  return [
    { name: "client.yaml", type: "md", doc: "c_" + c.id, git: "new" },
    { name: "1-identity", type: "dir", children: [] },
    { name: "2-income", type: "dir", children: [] },
    { name: "3-assets", type: "dir", children: [] },
    { name: "4-credit", type: "dir", children: [] },
    { name: "5-property", type: "dir", children: [] },
  ];
}
