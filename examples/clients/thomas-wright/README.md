# Thomas Wright - Conventional Investment Property

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Thomas James Wright (single borrower, individual) |
| **Loan Type** | Conventional Investment Property |
| **Purpose** | Purchase, investment (non-owner occupied rental) |
| **Property** | 1820 Collier Rd, Atlanta, GA 30318 (SFR, built 1995) |
| **Purchase Price** | $285,000 |
| **Loan Amount** | $213,750 (75% LTV) |
| **Rate** | 30-yr fixed @ 7.0% (investment premium) |
| **Qualifying FICO** | 742 |

## Client Story

Thomas is a Senior IT Project Manager at Delta Air Lines earning $110K/yr. He already owns one investment property (a condo on Peachtree Rd generating $800/mo net per Schedule E) and is buying a $285K SFR as his second rental. He puts 25% down for a $213,750 loan at 7.0%.

The critical test in this file is how the system handles **investment property income qualification**. Fannie Mae requires 75% of the subject property's market rent ($1,900 x 75% = $1,425/mo) to be included in qualifying income. With it, total qualifying income is $11,392/mo and back-end DTI is 33.2% (passes 36%). Without it, DTI jumps to 37.9% and the file fails.

## Key Numbers

| Metric | Value |
|---|---|
| W-2 base income | $110,000/yr = $9,166.67/mo |
| Existing rental (Schedule E) | $800/mo net |
| Subject property 75% rent | $1,425/mo (75% x $1,900 market rent) |
| Total qualifying income | **$11,391.67/mo** |
| Proposed PITIA | $1,847/mo (P&I $1,422 + tax $300 + ins $125) |
| Front-end DTI | 16.2% |
| Back-end DTI | 33.2% |
| **DTI WITHOUT 75% rent** | **37.9% (FAILS 36%)** |
| LTV | 75.0% (25% down, no PMI) |
| Reserve requirement | 6 mo PITIA x 2 properties = $20,202 |
| Available liquid | $151,175 (checking + savings) |

## Deliberate Test Traps

1. **Subject property 75% market rent** - Fannie Mae requires 75% of gross market rent to be included in qualifying income for investment property purchases. The system must identify the $1,900/mo market rent estimate (property disclosure), apply the 75% haircut ($1,425/mo), and add it to qualifying income. If this is missed, DTI = 37.9% and the file incorrectly fails conventional guidelines.
2. **Investment property reserve stacking** - Fannie requires 6 months of PITIA for EACH financed investment property owned. Post-purchase Thomas owns 2 properties. The system must calculate: 6 x $1,847 (subject) + 6 x $1,520 (existing) = $20,202, not just the subject property reserves.
3. **Investment property rate premium** - 7.0% is 50-75 bps above owner-occupied conventional rates. The system should recognize this as normal for investment property pricing, not flag it as an anomaly.
4. **Schedule E vs credit report** - The existing investment mortgage appears in both Schedule E (as an expense reducing net rental income to $800/mo) and the credit report (as a $1,520/mo liability). The system must NOT double-count this debt. Standard practice: count the $1,520/mo in DTI debts and use the $800/mo Schedule E net income in qualifying income.

## Document Checklist

### identity/ (2 files)
| File | Description |
|---|---|
| driver-license.pdf | Thomas Wright driver license (GA) |
| occupancy-affidavit.pdf | Investment property certification (non-owner occupied) |

### income/ (3 files)
| File | Description |
|---|---|
| thomas-paystub-2026-07.pdf | Delta Air Lines paystub (bi-weekly, $4,230.77/period) |
| thomas-w2-2025.pdf | W-2 2025: Box 1 $110,000, 401k $8,000 |
| schedule-e-2025.pdf | Schedule E: Property 1 (Peachtree Rd), net rental $9,600/yr ($800/mo) |

### assets/ (3 files)
| File | Description |
|---|---|
| chase-checking-2026-07.pdf | Chase Total Checking, $66,000 (Jul 2026). EMD withdrawal $4,000. |
| chase-savings-2026-06.pdf | Chase Premier Savings, $85,175 (Jun 2026) |
| fidelity-401k-2026-06.pdf | Fidelity 401(k), vested $165,000 (Jun 2026) |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge. FICO 742. Existing investment mortgage $1,520/mo, auto $340/mo, 2 revolving ($75/mo total). Clean. |

### property/ (2 files)
| File | Description |
|---|---|
| purchase-contract.pdf | $285,000, Conventional Investment, 25% down, close 09/25/2026 |
| property-disclosure.pdf | SFR 1995, 1,650 sqft, 3bd/2ba. Roof 2018, HVAC 2019. Market rent $1,900/mo. |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0803.txt | LO intake call notes from 08/03/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: Investment property 75% market rent rule, Schedule E net rental income, W-2 base
- **dti-calculator**: DTI with investment property rental income offset (pass/fail depends on 75% rule inclusion)
- **ltv-cltv**: Conventional investment at 75% LTV (no PMI)
- **payment-calculator**: PITIA for investment property (no MIP, no PMI)
- **asset-calc**: Investment property reserve stacking (6 mo PITIA per property)
- **doc-checklist**: Investment property document requirements (Schedule E, occupancy affidavit for non-owner occupied)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_conv_investment_client.py
```
