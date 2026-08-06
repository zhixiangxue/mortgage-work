# Marcus Chen / MCR Properties LLC - DSCR Investment Purchase

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | MCR Properties LLC (Texas LLC, Marcus Chen 100% member) |
| **Loan Type** | DSCR (Debt Service Coverage Ratio) - Non-QM Investment |
| **Purpose** | Purchase, investment property (non-owner occupied) |
| **Property** | 3805 Mill Creek Drive, Dallas, TX 75287 |
| **Purchase Price** | $340,000 |
| **Loan Amount** | $255,000 (75% LTV) |
| **Rate** | 30-yr fixed @ 7.0% |
| **DSCR** | **1.26** ($2,950 rent / $2,342 PITIA) |
| **Personal FICO** | 742 (Marcus as personal guarantor) |

## Client Story

Marcus is an experienced real estate investor with 3 existing rental properties in Dallas. He's purchasing his 4th investment property through his LLC (MCR Properties LLC, formed Jan 2024). The financing is a DSCR loan, which is fundamentally different from owner-occupied loans: the property's rental income must cover the debt service (PITIA), not the borrower's personal income.

DSCR = monthly gross rent / monthly PITIA. At 1.26, the rent ($2,950) exceeds the total monthly housing cost ($2,342) by 26%, which clears the standard 1.25 minimum for best-tier pricing. No personal income documents are required - the property qualifies itself.

## Key Numbers

| Metric | Value |
|---|---|
| Monthly gross rent (per lease) | $2,950 |
| Proposed PITIA | $2,342/mo (P&I $1,697 + tax $458 + ins $142 + HOA $45) |
| **DSCR** | **1.26** (exceeds 1.25 standard minimum) |
| Market rent average | $2,925/mo (lease is at/above market) |
| LLC business checking (Jul 2026) | $73,000 |
| Personal checking (Jul 2026) | $47,100 |
| Down payment | $85,000 (25%) |
| Estimated closing + reserves | ~$95,600 total needed from LLC |
| **Asset gap** | **~$8,000** (LLC funds insufficient for DP + 6-mo reserves) |

## DSCR Calculation Detail

```
DSCR = Gross Monthly Rent / PITIA

Gross Monthly Rent:        $2,950  (per current lease, signed 07/15/2026)
PITIA:
  P&I ($255K @ 7.0%, 30yr): $1,697
  Property tax ($5,500/yr):   $458
  Insurance ($1,700/yr):      $142
  HOA ($45/mo):                $45
  Total PITIA:              $2,342

DSCR = $2,950 / $2,342 = 1.26
```

DSCR 1.26 > 1.25 minimum -> qualifies for best DSCR pricing tier.

## Deliberate Test Traps

1. **LLC reserve gap** - Business checking ($73K) minus down payment ($85K) minus 6-month reserves ($14K) = negative ~$8K. The LLC doesn't have enough funds for both the down payment AND the reserve requirement. The system should flag this shortfall and suggest personal funds contribution to LLC.
2. **No personal income documents** - Unlike QM loans, DSCR doesn't use personal DTI. The system should NOT flag "missing W-2s" or "missing tax returns" - it should recognize the DSCR qualification path.
3. **Personal credit context only** - The credit report shows personal debts (investment mortgage $2,180/mo, auto lease $599/mo) that are NOT included in DTI for DSCR purposes. The system should recognize these are context-only and not count them against qualification.

## Document Checklist

### identity/ (2 files)
| File | Description |
|---|---|
| driver-license.pdf | Marcus Chen driver license (TX) |
| llc-formation.pdf | MCR Properties LLC Texas Secretary of State formation document (formed 01/2024), EIN, registered agent, Marcus Chen as 100% managing member |

### income/ (2 files) - Property income, NOT borrower income
| File | Description |
|---|---|
| current-lease.pdf | 12-month residential lease for 3805 Mill Creek Dr. Tenant: Jennifer Walsh. Rent: $2,950/mo. Signed 07/15/2026. |
| market-rent-analysis.pdf | Comparable rent analysis for the subject property area (3 comps avg $2,925/mo, confirming lease is at market) |

### assets/ (2 files)
| File | Description |
|---|---|
| business-checking-2026-07.pdf | MCR Properties LLC business checking (Chase), ending $73,000 (Jul 2026) |
| personal-checking-2026-07.pdf | Marcus Chen personal checking (Chase), ending $47,100 (Jul 2026) |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge personal credit report for Marcus Chen. FICO 742. Tradelines shown for context only (NOT used in DSCR DTI): investment mortgage $2,180/mo, auto lease $599/mo. No collections, no public records. |

### property/ (3 files)
| File | Description |
|---|---|
| purchase-contract.pdf | Purchase contract for 3805 Mill Creek Dr, $340,000 (investment, non-owner occupied) |
| property-disclosure.pdf | Seller's disclosure (SFR, built 2005, 1,820 sqft) |
| schedule-e.pdf | Marcus's 2025 Schedule E showing 3 existing rental properties with positive cash flow |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0802.txt | LO intake call notes from 08/02/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: DSCR method (rent / PITIA), no personal income path, lease vs market rent verification
- **asset-calc**: LLC vs personal fund separation, reserve shortfall detection
- **credit-report-analyzer**: DSCR credit-quality tier (FICO 742 = best tier), personal debts as context-only
- **dti-calculator**: DSCR ratio calculation (not traditional front/back DTI)
- **ltv-cltv**: 75% LTV DSCR investment property
- **payment-calculator**: PITIA for DSCR (includes HOA)
- **doc-checklist**: DSCR-specific document requirements (LLC formation, lease, market rent analysis, NO personal income docs)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_dscr_client.py
```
