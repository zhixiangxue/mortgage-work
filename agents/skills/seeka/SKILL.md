---
name: mortgage_memory_extraction
description: Extract mortgage-relevant signals from loan officer conversations.
---

Your job is to extract **actionable, reusable knowledge** from conversations
between a loan officer (LO) and their AI assistant.

## What to remember

### 1. Client facts — borrower details shared or updated verbally
- Employment changes: "borrower switched jobs last month, now at Tesla"
- Income specifics: "his base is actually $120K, not $96K"
- Asset details: "they have a second brokerage account at Schwab"
- Credit issues: "borrower had a late payment in March, it's since been resolved"
- Property details: "the appraisal came in $30K under contract price"
- Loan purpose, timeline constraints

### 2. Corrections — the LO fixes wrong information on file
- "That income figure is wrong, it should be $8,500/mo"
- "No, he doesn't work there anymore"
- "The loan amount is $420K, not $450K"
- These override stale data and must be preserved

### 3. Decisions & strategy — the LO commits to a direction
- "Let's go DSCR instead of conventional"
- "Client wants to close by end of month"
- "We're going to use the wife's income only"
- "I'm locking the rate today"

### 4. LO preferences & habits — recurring patterns in how this LO works
- "This LO always asks for two months of bank statements even when one suffices"
- "Prefers JMAC for jumbo loans"
- These are global (not client-specific) and should name the LO explicitly

## What NOT to remember

### Guideline / reference questions — the LO is just looking something up
- "What's the DTI limit for FHA?"
- "Does Fannie Mae allow gifted funds?"
- "What's the minimum FICO for a jumbo loan?"
- These have no lasting value; the LO will ask again if they need it again.
  EXCEPTION: if the LO REACTS to the answer (agrees, disagrees, corrects it),
  then the reaction itself may be worth remembering.

### Tool testing & experiments
- "Try the hello skill"
- "Can you read this PDF?" (just testing)
- Pure exploration with no client context

### Browsing without action
- The LO reads through documents but makes no judgment, correction, or decision
- "Show me the bank statements" → just looking, nothing to remember

### Status checks
- "What's the status of that file?"
- "Did the upload finish?"
- Transient, no lasting value

### Raw calculation results
- "DTI is 38.7%" — this is a computed output, not knowledge
- EXCEPTION: if the LO comments on the result ("that's too high, try without
the car loan"), the LO's reaction IS worth remembering

## Format
- Each memory must be a **self-contained, third-person statement**
- If it relates to a specific client, name the client explicitly:
  "Wei Chen switched jobs in June 2026 and now works at Google"
- If it's a global LO preference, name the LO:
  "LO Alice always requires two months of bank statements"
- Keep each memory under 3 sentences — single fact, not a paragraph
- Use exact names, dates, and numbers from the conversation — never paraphrase
  them loosely
