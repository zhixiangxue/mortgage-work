/* ================= Chat mock threads ================= */
export const CHAT_HOME = `
  <div class="msg ai">
    <div class="bubble">Morning. Across your 4 active clients: <code class="inline">Sarah Mitchell</code> got a new bank statement overnight (auto-filed to assets/), and <code class="inline">Robert Alvarez</code> has had 5 docs outstanding for 6 days — want me to draft a follow-up?</div></div>
  <div class="msg user">
    <div class="bubble">Who's closest to being ready to submit?</div></div>
  <div class="msg ai">
    <div class="bubble"><code class="inline">James &amp; Amy Chen</code> — file is complete, income verified, 1003 draft generated. One click to export MISMO 3.4 for your LOS.<span style="color:var(--brand)">▊</span></div></div>`;

export const CHAT_CLIENT = `
  <div class="msg user">
    <div class="bubble">Run an income check on Sarah — did we get everything we need?</div></div>
  <div class="msg ai">
    <div class="bubble">
      <div class="trace"><div class="t-head"><span>AGENT · 6 FILES READ · 2 WRITTEN</span><span>4.2s</span></div>
<pre><span class="op">READ</span>  income/paystub-2026-06.pdf <span class="okx">✓</span>
<span class="op">READ</span>  income/paystub-2026-07.pdf <span class="okx">✓</span>
<span class="op">READ</span>  income/w2-2025.pdf <span class="okx">✓</span>
<span class="op">READ</span>  assets/boa-statement-*.pdf <span class="okx">✓✓</span>
<span class="op">READ</span>  products/A&amp;D/non-qm-bank-statement.pdf <span class="okx">✓</span>
<span class="op">WRITE</span> ai/income-analysis.ai <span class="okx">✓</span>
<span class="op">WRITE</span> ai/missing-docs.ai <span class="okx">✓</span></pre></div>
      Qualifying income comes to <code class="inline">$19,900/mo</code> — David's W-2 base plus Sarah's 12-mo bank-statement average at a 50% expense factor. Back-end DTI is <code class="inline">30.9%</code>, comfortable.
      Two gaps: <b>Apr &amp; May statements</b> are missing, and there's an <b>$18k deposit on 06/14</b> that needs an LOE if you go conventional. Full breakdown written to <code class="inline">ai/income-analysis.ai</code>.
      <div class="apply-row"><button class="btn-sm primary" onclick="openDoc('income')">Open Analysis</button><button class="btn-sm" onclick="openDoc('missing')">Missing Docs</button><button class="btn-sm">Draft Email</button></div>
    </div></div>
  <div class="msg user">
    <div class="bubble">Would she clear A&amp;D's bank statement program instead?</div></div>
  <div class="msg ai">
    <div class="bubble">Yes — 12-mo business statements at 80% LTV needs FICO 680; she's at <code class="inline">742</code>. The 06/14 deposit wouldn't need sourcing under this program. Comparing rate impact vs conventional now<span style="color:var(--brand)">▊</span></div></div>`;

export const CHAT_PRODUCTS = `
  <div class="msg user">
    <div class="bubble">Which of my lenders can do 85 LTV on a bank statement loan?</div></div>
  <div class="msg ai">
    <div class="bubble">
      <div class="trace"><div class="t-head"><span>AGENT · SEARCHED PRODUCT LIBRARY</span><span>1.8s</span></div>
<pre><span class="op">SCAN</span>  products/**/*.pdf · 9 docs <span class="okx">✓</span>
<span class="op">MATCH</span> A&amp;D Mortgage · non-qm-bank-statement.pdf p.3 <span class="okx">✓</span></pre></div>
      Only <b>A&amp;D Mortgage</b> — 24-mo business statements, 85% LTV, min FICO 700, up to $3M. UWM and Rocket TPO don't have bank-statement docs in your library; if you have their non-QM sheets, drop them in and I'll index them.
      <div class="apply-row"><button class="btn-sm primary" onclick="openDoc('guideline')">Open Matrix p.3</button><button class="btn-sm">Compare All</button></div>
    </div></div>`;

/* Scaffold thread shown right after a new client folder is created */
export function chatFreshClient(c) {
  return `
    <div class="msg ai">
      <div class="bubble">
        <div class="trace"><div class="t-head"><span>AGENT · SCAFFOLD</span><span>0.3s</span></div>
<pre><span class="op">MKDIR</span> clients/${c.id}/ <span class="okx">✓</span>
<span class="op">WRITE</span> PROFILE.md <span class="okx">✓</span>
<span class="op">SYNC</span>  backed up <span class="okx">✓</span></pre></div>
        Folder ready for <code class="inline">${c.name}</code>. Drop whatever you have — paystubs, bank statements, a credit pull — and I'll classify each file, extract the data into PROFILE.md, and start a missing-docs checklist for a ${c.purpose.toLowerCase()} at ${c.amount}.
      </div>
    </div>`;
}

export const CHAT_HISTORY = [
  { title: "Sarah · Income Review", when: "10:47 AM", thread: "client" },
  { title: "Product Lookup", when: "9:12 AM", thread: "products" },
  { title: "Daily Briefing", when: "8:30 AM", thread: "home" },
  { title: "Robert · Follow-up email", when: "Yesterday" },
  { title: "James · Pre-approval letter", when: "Jul 25" },
  { title: "Nina · First-call prep", when: "Jul 21" },
];
