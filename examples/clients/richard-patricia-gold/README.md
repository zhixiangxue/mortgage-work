# Richard & Patricia Gold - Non-QM Asset Depletion Purchase

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Richard Gold (retired, ExxonMobil 35yr) + Patricia Gold (retired) |
| **Loan Type** | Non-QM Asset Depletion |
| **Purpose** | Purchase, primary residence |
| **Property** | 2270 Harbor View Dr, Naples, FL 34102 (waterfront, direct Gulf access) |
| **Purchase Price** | $850,000 |
| **Loan Amount** | $637,500 (75% LTV) |
| **Rate** | 30-yr fixed @ 6.75% (Non-QM premium) |
| **Qualifying FICO** | 775 (Patricia, lower) |

## Client Story

Richard and Patricia are a retired couple buying a $850K waterfront home in Naples, FL. Richard retired from ExxonMobil after 35 years with a $3,650/mo pension. Together they collect $8,640/mo in stable retirement income (pension + SS).

The key to this file is the **Asset Depletion** income method: their $4.5M in liquid/investment assets divided by 360 months = $12,550/mo in qualifying income. Total qualifying income: **$21,190/mo**. No W-2s, no tax returns required - the assets ARE the income.

## Key Numbers

| Metric | Value |
|---|---|
| Eligible assets | $4,517,850 (Schwab $2.2M + IRA Richard $1.48M + IRA Patricia $630K + CD $207K) |
| Asset depletion income | $4,517,850 / 360 = **$12,550/mo** |
| Pension + SS income | $8,640/mo ($3,650 pension + $3,275 SS-R + $1,715 SS-P) |
| Total qualifying income | **$21,190/mo** |
| Proposed PITIA | $5,233/mo (P&I $4,135 + tax $850 + ins $248) |
| Front-end DTI | 24.7% |
| Back-end DTI | 24.9% |
| LTV | 75.0% (25% down, no PMI) |

## Deliberate Test Traps

1. **Asset depletion formula** - Income is NOT from W-2 or tax returns. It's calculated from eligible assets / 360. The system must identify all eligible asset accounts (brokerage, IRA, IRA, CD), exclude the checking account (opering funds), sum them, and divide by 360. A common error: using 240 months instead of 360, or including the checking balance.
2. **No W-2 / no tax returns** - This is a Non-QM program that doesn't require traditional income documents. The system should NOT flag "missing W-2s" or "missing tax returns." Instead, it should recognize the Asset Depletion qualification path from asset statements + pension/SS award letters.
3. **CD early withdrawal penalty** - The $207K Wells Fargo CD matures 03/2027. The 3-month interest penalty for early withdrawal should NOT reduce the asset's value for qualification purposes. The system should count it at full balance.
4. **Flood zone AE insurance** - The property is in FEMA flood zone AE (waterfront). Insurance estimate of $4,800 includes wind + flood + hazard. The system should recognize that flood insurance is mandatory and included in PITIA.

## Document Checklist

### identity/ (2 files)
| File | Description |
|---|---|
| driver-license.pdf | Richard + Patricia driver licenses (FL) |
| occupancy-affidavit.pdf | Primary residence intent (joint) |

### income/ (3 files) - Retirement income + asset statements serve as income docs
| File | Description |
|---|---|
| social-security-letter-richard.pdf | SSA benefit letter: $3,275.30/mo net (retirement, started 06/2021) |
| social-security-letter-patricia.pdf | SSA benefit letter: $1,715.30/mo net (retirement, started 03/2023) |
| pension-letter.pdf | ExxonMobil pension: $3,650/mo (J&S 100%), Richard retired 06/2021 after 35yr |

### assets/ (5 files) - These ARE the income documentation for Asset Depletion
| File | Description |
|---|---|
| wells-fargo-checking-2026-07.pdf | WF Premier Checking joint, $51,041 (Jul 2026) - NOT eligible for depletion |
| schwab-brokerage-2026-06.pdf | Schwab joint brokerage, $2,200,000 (stocks/ETFs/bonds/cash) |
| ira-richard-2026-06.pdf | Fidelity Traditional IRA (Richard), $1,480,000 |
| ira-patricia-2026-06.pdf | Fidelity Traditional IRA (Patricia), $630,000 |
| cd-2026-06.pdf | Wells Fargo CD joint, $207,850 (24-mo, 4.25% APY, matures 03/2027) |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge. Richard 788, Patricia 775, qualifying 775. Amex Platinum (charge card, excluded) + Chase Sapphire $40/mo. No collections, no public records, 0 inquiries. |

### property/ (2 files)
| File | Description |
|---|---|
| purchase-contract.pdf | Purchase contract $850,000, Non-QM Asset Depletion, 25% down |
| property-disclosure.pdf | SFR waterfront, built 2003, 2,950 sqft, 4bd/3ba, private dock. Flood Zone AE. Hurricane shutters. Ins $4,800/yr (wind+flood+hazard). |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0805.txt | LO intake call notes from 08/05/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: Asset Depletion method (eligible assets / 360), retirement income (pension + SS award letters), no W-2/tax return path
- **asset-calc**: Asset eligibility classification (brokerage/IRA/CD eligible vs checking not), CD early withdrawal penalty treatment
- **credit-report-analyzer**: Charge card exclusion (Amex Platinum), dual co-borrower FICO selection
- **dti-calculator**: Non-QM DTI thresholds (43-50%), extremely low debt load
- **ltv-cltv**: Non-QM at 75% LTV (no PMI)
- **payment-calculator**: PITIA with high Florida insurance (wind + flood + hazard for Zone AE)
- **doc-checklist**: Non-QM Asset Depletion document requirements (asset statements + award letters, NO W-2s or tax returns)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_asset_depletion_client.py
```
