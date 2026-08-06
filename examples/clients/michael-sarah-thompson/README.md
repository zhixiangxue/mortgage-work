# Michael & Sarah Thompson - Cash-Out Refinance

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Michael D. Thompson + Sarah E. Thompson (joint) |
| **Loan Type** | Conventional Cash-Out Refinance |
| **Purpose** | Cash-out refinance (debt consolidation + home improvements) |
| **Property** | 7842 W Desert Cove Dr, Phoenix, AZ 85037 (SFR, built 2010) |
| **Appraised Value** | $520,000 |
| **New Loan** | $416,000 (80% LTV) |
| **Existing Mortgage** | $271,043 payoff (Wells Fargo, 3.75%) |
| **Rate** | 30-yr fixed @ 6.5% |
| **Qualifying FICO** | 698 (Sarah, lower co-borrower) |

## Client Story

Michael (Intel software engineer, $135K) and Sarah (marketing director, $72K) bought their Phoenix home in 2021 for $380,000. It's now appraised at $520,000, giving them $249K in equity. They accumulated $78,000 in credit card debt from medical expenses and home repairs at ~22% APR, paying $2,340/mo in minimums.

The cash-out refinance pays off the existing $271K mortgage, retires all $78K credit card debt, covers $16K closing costs, and leaves $51K for a kitchen/bathroom remodel. The new $416,000 loan at 6.5% raises their mortgage payment by $1,221/mo but eliminates $2,340/mo in credit card payments - net savings of $1,119/mo.

The critical test: the three credit card accounts being paid off at closing ($2,340/mo) MUST be excluded from DTI. With exclusion: back-end DTI = 23.7% (passes). Without exclusion: 37.3% (fails conventional 36%).

## Key Numbers

| Metric | Value |
|---|---|
| Combined qualifying income | $17,250/mo ($11,250 + $6,000) |
| New PITIA | $3,274/mo (P&I $2,629 + tax $450 + ins $150 + HOA $45) |
| Remaining debt post-consolidation | $820/mo (auto $520 + student $300) |
| Credit card debt being paid off | $78,000 (Chase $32K + Amex $26K + Discover $20K) |
| Credit card payments excluded | $2,340/mo ($960 + $780 + $600) |
| Front-end DTI | 19.0% |
| Back-end DTI (post-consolidation) | 23.7% |
| **Back-end DTI (WITHOUT exclusion)** | **37.3% (FAILS 36%)** |
| LTV | 80.0% (at conventional cash-out max) |
| Net cash to borrowers | $50,957 ($41K remodel + $10K reserve) |
| Net monthly savings | $1,119/mo (card payments eliminated - mortgage increase) |

## Deliberate Test Traps

1. **Debt consolidation DTI exclusion** - The three credit card accounts ($78K balance, $2,340/mo payments) are being paid off at closing from loan proceeds. The system MUST exclude them from DTI calculation. Without exclusion, back-end DTI = 37.3% and the file fails conventional guidelines. This is the most common analytical error in cash-out refinance DTI calculation.
2. **80% LTV cash-out maximum** - Conventional cash-out is capped at 80% LTV. $416,000 / $520,000 = exactly 80.0%. The system must verify this is at (not over) the maximum. Even $1 over would require a different program.
3. **FICO depression from utilization** - Sarah's FICO 698 is lower than expected for the income level. The system should recognize this is caused by high revolving utilization ($78K / $90K limits = 87%), not credit mismanagement. Post-consolidation, utilization drops to 0% and scores should recover 30-50 points.
4. **Seasoning / payment history** - Owned since 03/2021 (5+ years), well past the 6-month Fannie cash-out seasoning requirement. Perfect mortgage payment history (0x30 in 24 months). The system should verify both seasoning and payment history as qualifying conditions.
5. **Rate increase justification** - Rate jumps from 3.75% to 6.5%, but the debt consolidation makes financial sense ($1,119/mo net savings). The system should not flag the rate increase as problematic when the purpose is clearly documented.

## Document Checklist

### identity/ (2 files)
| File | Description |
|---|---|
| driver-license.pdf | Michael + Sarah driver licenses (AZ) |
| occupancy-affidavit.pdf | Primary residence certification (joint) |

### income/ (4 files)
| File | Description |
|---|---|
| michael-paystub-2026-07.pdf | Intel paystub (semi-monthly, $5,625/period) |
| michael-w2-2025.pdf | W-2 2025: Box 1 $135,000 |
| sarah-paystub-2026-07.pdf | Metro Marketing paystub (semi-monthly, $3,000/period) |
| sarah-w2-2025.pdf | W-2 2025: Box 1 $72,000 |

### assets/ (1 file)
| File | Description |
|---|---|
| bofa-checking-2026-07.pdf | BofA Advantage Checking (joint), $12,000. Shows card payments as withdrawals. |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge. Michael 705, Sarah 698. 3 cards being paid off ($78K total). Perfect mortgage history (0x30 in 24mo). |

### property/ (4 files)
| File | Description |
|---|---|
| appraisal.pdf | Uniform Residential Appraisal. Value $520,000. Prior sale $380,000 (03/2021). |
| deed.pdf | Warranty Deed. Purchased 03/2021 for $380,000. JTWROS. |
| existing-mortgage-statement.pdf | Wells Fargo statement. Balance $271,043 @ 3.75%. P&I $1,408/mo. |
| property-disclosure.pdf | SFR 2010, 2,400 sqft. Cash-out use breakdown: $78K consolidation + $41K remodel. |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0804.txt | LO intake call notes from 08/04/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **dti-calculator**: Debt consolidation exclusion (paid-off accounts removed from DTI), pass/fail depends on exclusion
- **ltv-cltv**: Cash-out maximum at 80% LTV (exactly at the cap)
- **payment-calculator**: New PITIA vs existing payment, net monthly savings calculation
- **credit-report-analyzer**: Utilization-driven FICO depression, dual co-borrower score selection
- **doc-checklist**: Cash-out refinance document requirements (appraisal, deed, existing mortgage statement, payment history)
- **income-calc**: Dual W-2 income verification (semi-monthly payroll)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_cashout_refi_client.py
```
