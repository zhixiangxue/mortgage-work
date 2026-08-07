---
name: mortgage_memory_extraction
description: Extract mortgage-relevant signals from loan officer conversations.
---

Your job is to extract **actionable knowledge** from conversations between a
loan officer (LO) and their AI assistant. Focus on:

1. **Fact corrections** — the LO identifies an error in a client's profile
   (e.g. "the loan amount is wrong", "that's not his employer")
2. **New information** — the LO shares borrower details not yet on disk
   (e.g. "borrower switched jobs last month, now at Tesla")
3. **Decision/strategy** — the LO commits to a program direction or approach
   (e.g. "let's go DSCR instead of conventional")
4. **LO preferences/habits** — recurring patterns in how this LO works
   (e.g. "always asks for two bank statements even when one suffices")

**Ignore:**
- Tool testing / skill experiments (e.g. "try the hello skill")
- Idle queries with no actionable outcome ("what's the status?")
- File-reading sequences where the LO is just browsing

Each extracted memory should be a self-contained, third-person statement.
If the memory relates to a specific client, name the client explicitly.
