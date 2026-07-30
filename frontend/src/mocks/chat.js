/* ================= Chat mocks — plain-browser demo only =================
   Same shape as real data so ChatMessage/ChatHistory render them unchanged:
   messages are chak dump objects ({role, content}, content is markdown),
   history rows are the `convs` items the agent's `list` reply carries.
   Used solely when ?demo=1 and the agent WS is unreachable. */

export const DEMO_CHAT_MESSAGES = [
  {
    role: "assistant",
    content: "Morning. Across your 4 active clients: `Sarah Mitchell` got a new " +
      "bank statement overnight (auto-filed to assets/), and `Robert Alvarez` has " +
      "had 5 docs outstanding for 6 days — want me to draft a follow-up?",
  },
  { role: "user", content: "Who's closest to being ready to submit?" },
  {
    role: "assistant",
    content: "`James & Amy Chen` — file is complete, income verified, 1003 draft " +
      "generated. One click to export MISMO 3.4 for your LOS.",
  },
];

const now = Math.floor(Date.now() / 1000);
export const DEMO_CONVS = [
  { id: "demo-1", title: "Sarah Mitchell · Income Review", context: { client: { name: "Sarah Mitchell" } }, updated: now - 60 * 40 },
  { id: "demo-2", title: "Product Lookup", context: { view: "products" }, updated: now - 3600 * 2 },
  { id: "demo-3", title: "Daily Briefing", context: {}, updated: now - 3600 * 3 },
  { id: "demo-4", title: "Robert Alvarez · Follow-up email", context: { client: { name: "Robert Alvarez" } }, updated: now - 86400 },
  { id: "demo-5", title: "James Chen · Pre-approval letter", context: { client: { name: "James Chen" } }, updated: now - 86400 * 5 },
];
