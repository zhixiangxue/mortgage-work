# Carlos Mendez - FHA Purchase

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Carlos Mendez (sole borrower, first-time homebuyer) |
| **Loan Type** | FHA (Federal Housing Administration) |
| **Purpose** | Purchase, primary residence |
| **Property** | 1420 Mesquite Trail, San Antonio, TX 78245 |
| **Purchase Price** | $310,000 |
| **Base Loan Amount** | $299,150 (96.5% LTV, 3.5% down) |
| **Upfront MIP (1.75%)** | $5,235.13 (financed) |
| **Total FHA Loan** | $304,385.13 |
| **Rate** | 30-yr fixed @ 6.875% |
| **FICO** | 672 |

## Client Story

Carlos is an Electrician Foreman at Lone Star Electrical Contractors, earning $98K base salary. He's a first-time homebuyer purchasing a modest $310K home in San Antonio with FHA financing (only 3.5% down). His credit score of 672 qualifies for FHA but not top-tier Conventional pricing.

His income has been trending upward steadily: $84.2K (2024) -> $92.6K (2025) -> $98K (2026 base), which is a positive compensating factor. However, his reserve position after closing will be thin (~$7,780 remaining in checking).

## Key Numbers

| Metric | Value |
|---|---|
| Monthly income (base only) | $8,167/mo |
| Overtime (2-yr avg) | $625/mo (could be added) |
| Proposed PITIA | $2,749/mo (P&I $2,000 + tax $463 + ins $150 + MIP $137) |
| **Front-end DTI** | **33.7%** (exceeds FHA manual 31% guideline) |
| **Back-end DTI** | **39.7%** (under FHA 43% cap) |
| Checking balance | $21,730 (Jul 2026) |
| Gift funds | $5,000 from mother (gift letter on file) |
| Cash to close | ~$13,950 |
| Post-close reserves | ~$7,780 (thin) |

## FHA MIP Structure

| Component | Rate | Amount |
|---|---|---|
| Upfront MIP | 1.75% | $5,235.13 (financed into loan) |
| Annual MIP | 0.55% | $1,645/yr = $137/mo (required for life of loan at >90% LTV) |

## Deliberate Test Traps

1. **Front-end DTI exceeds 31%** - At 33.7%, the front-end ratio exceeds the FHA manual underwriting guideline of 31%, but the back-end (39.7%) is under the 43% cap. The system should flag this exceedance while recognizing the file may still be insurable via AUS with compensating factors.
2. **Thin reserves** - Post-close checking balance (~$7,780) is very thin. FHA doesn't require formal reserves at this LTV, but if AUS asks for reserves, the file gets tight. The system should flag reserve adequacy.
3. **Gift donor statement missing** - Gift letter is on file but the donor's (mother Maria Mendez) bank statement has NOT been collected. The system should detect that gift verification is incomplete.

## Document Checklist

### identity/ (3 files)
| File | Description |
|---|---|
| driver-license.pdf | Carlos driver license (TX) |
| occupancy-affidavit.pdf | Primary residence intent (owner-occupant required for FHA) |
| residency-history.pdf | 2-year residency history |

### income/ (5 files)
| File | Description |
|---|---|
| carlos-w2-2024.pdf | 2024 W-2 (Box 1: $84,200) |
| carlos-w2-2025.pdf | 2025 W-2 (Box 1: $92,600) |
| carlos-paystub-2026-06.pdf | Paystub Jun 2026 (semi-monthly, YTD $49,000) |
| carlos-paystub-2026-07.pdf | Paystub Jul 2026 (YTD $57,167) |
| voe.pdf | Verbal Verification of Employment (employer confirms hire date 11/2019, position, no likelihood of change) |

### assets/ (2 files)
| File | Description |
|---|---|
| bbva-checking-2026-07.pdf | BBVA Smart Checking statement Jul 2026 (ending $21,730.50) |
| gift-letter.pdf | Gift letter from Maria Mendez (mother), $5,000 |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge credit report. FICO 672. Tradelines: auto $385, two revolving ($85 + $25). No collections, no public records. |

### property/ (2 files)
| File | Description |
|---|---|
| purchase-contract.pdf | Purchase contract for 1420 Mesquite Trail, $310,000 |
| property-disclosure.pdf | Seller's disclosure (SFR, built 2001, 1,580 sqft) |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0730.txt | LO intake call notes from 07/30/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: W-2 2-year trend (upward), base vs overtime income, FHA income calculation
- **asset-calc**: Gift fund verification completeness, post-close reserve adequacy
- **credit-report-analyzer**: FHA qualifying FICO (580+ floor), tradeline extraction
- **dti-calculator**: FHA front-end (31%) / back-end (43%) thresholds, manual vs AUS
- **ltv-cltv**: 96.5% LTV (FHA max), upfront MIP financing into base loan
- **payment-calculator**: PITIA with both upfront and annual MIP
- **doc-checklist**: FHA-specific document requirements (VOE, occupancy affidavit)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_fha_client.py
```
