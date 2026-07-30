/* ================= Tools (LO-facing agent capabilities) =================
   What the agent is allowed to do, in the LO's language — not the infra
   behind it (engines/ports live in the developer-facing Runtime view).
   One list for both surfaces: the sidebar panel shows `installed` tools,
   the Tool Market doc shows everything (VS Code extensions model — browse,
   install, and the card appears in the panel; remove it from the panel).
   `status` is tool health (up/off), `on` is the LO's permission switch. */
import { reactive } from "vue";

export const TOOLS = reactive([
  // Installed out of the box
  { id: "search",  name: "Document Search",    tag: "FILES",    desc: "Search across client files and lender guidelines", status: "up", on: true,  installed: true },
  { id: "income",  name: "Income Analysis",    tag: "INCOME",   desc: "Read paystubs & W-2s, compute qualifying income",  status: "up", on: true,  installed: true },
  { id: "draft",   name: "Form Drafting",      tag: "FORMS",    desc: "Draft URLA-1003 from collected documents",         status: "up", on: true,  installed: true },
  { id: "missing", name: "Missing Docs Check", tag: "TRACKING", desc: "Track what's still needed for each client",        status: "up", on: true,  installed: true },
  // On the market shelf
  { id: "credit",  name: "Credit Report Pull", tag: "CREDIT",   desc: "Pull tri-merge credit reports for a borrower",     status: "up", on: false, installed: false },
  { id: "dti",     name: "DTI Calculator",     tag: "INCOME",   desc: "Compute front / back-end ratios from the file",    status: "up", on: false, installed: false },
  { id: "rates",   name: "Rate Sheet Lookup",  tag: "PRICING",  desc: "Find today's pricing across your lenders",         status: "up", on: false, installed: false },
  { id: "email",   name: "Email Drafting",     tag: "COMMS",    desc: "Draft borrower & processor emails in your voice",  status: "up", on: false, installed: false },
  { id: "voe",     name: "VOE Request",        tag: "FORMS",    desc: "Prepare employment verification requests",         status: "up", on: false, installed: false },
  { id: "apprsl",  name: "Appraisal Tracker",  tag: "TRACKING", desc: "Follow appraisal orders and their ETAs",           status: "up", on: false, installed: false },
  { id: "comply",  name: "Compliance Check",   tag: "REVIEW",   desc: "Flag missing disclosures before submission",       status: "up", on: false, installed: false },
  { id: "notes",   name: "Meeting Notes",      tag: "COMMS",    desc: "Summarize borrower calls into the client file",    status: "up", on: false, installed: false },
]);

export const installedTools = () => TOOLS.filter(t => t.installed);
