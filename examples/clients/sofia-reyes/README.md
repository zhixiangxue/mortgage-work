# Sofia Reyes - Non-QM Bank Statement Purchase

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Sofia Reyes (sole borrower, self-employed) |
| **Loan Type** | Non-QM Bank Statement |
| **Purpose** | Purchase, primary residence |
| **Property** | 2317 Bissonnet St, Houston, TX 77005 |
| **Purchase Price** | $585,000 |
| **Loan Amount** | $468,000 (80% LTV) |
| **Rate** | 30-yr fixed @ 7.25% (Non-QM premium) |
| **FICO** | 708 |

## Client Story

Sofia is a self-employed interior designer who owns Reyes Interior Design Studio LLC (formed Feb 2021). She earns approximately $298K/year in business deposits but has no W-2 and has not submitted tax returns. She qualifies for a Non-QM Bank Statement loan where income is calculated from 12 months of business bank deposits using an expense factor.

This is a fundamentally different qualification path from W-2 borrowers: no paystubs, no W-2s, no tax returns. Instead, 12 months of bank statements plus a CPA letter serve as income documentation. The trade-off is a higher interest rate (7.25% vs ~6.25% for conventional).

## Key Numbers

| Metric | Value |
|---|---|
| 12-month business deposits | $298,000 (Aug 2025 - Jul 2026) |
| Monthly average deposits | $24,833 |
| Expense factor | 50% (service-based SMLLC) |
| **Qualifying monthly income** | **$12,417/mo** ($298K x 50% / 12) |
| Proposed PITIA | $4,156/mo (P&I $3,193 + tax $780 + ins $183) |
| Front-end DTI | 33.5% |
| Back-end DTI | 36.7% |
| Business checking (Jul 2026) | $21,000 |
| Personal checking (Jul 2026) | $61,200 |
| Total liquid | $82,200 |

## Deliberate Test Traps

1. **Asset shortfall** - Total liquid funds ($82,200) do NOT cover the $117,000 down payment. The file is ~$35K short. Sofia claims a separate investment account exists but no statement has been provided. The system must flag insufficient funds for down payment.
2. **No tax returns** - Unlike QM loans, this Non-QM program doesn't require tax returns. The system should NOT flag "missing tax returns" as a deficiency - it should recognize the bank statement program.
3. **Business vs personal account mixing** - Both business and personal accounts are at Wells Fargo. The system should correctly identify the business account for income calculation and the personal account for asset verification.

## Document Checklist

### identity/ (3 files)
| File | Description |
|---|---|
| driver-license.pdf | Sofia driver license (TX) |
| occupancy-affidavit.pdf | Primary residence intent affidavit |
| business-license.pdf | Texas Secretary of State filing for Reyes Interior Design Studio LLC, EIN 87-2941XXX |

### income/ (1 file)
| File | Description |
|---|---|
| cpa-letter.pdf | CPA confirmation letter (Hernandez & Park CPA) verifying business authenticity, operating since Feb 2021, and that the Wells Fargo business checking is the primary operating account |

### assets/ (13 files)
| File | Description |
|---|---|
| bank-statement-2025-08.pdf | Business checking, Aug 2025 (deposits $26,200) |
| bank-statement-2025-09.pdf | Business checking, Sep 2025 (deposits $24,800) |
| bank-statement-2025-10.pdf | Business checking, Oct 2025 (deposits $25,500) |
| bank-statement-2025-11.pdf | Business checking, Nov 2025 (deposits $23,900) |
| bank-statement-2025-12.pdf | Business checking, Dec 2025 (deposits $28,100) |
| bank-statement-2026-01.pdf | Business checking, Jan 2026 (deposits $22,300) |
| bank-statement-2026-02.pdf | Business checking, Feb 2026 (deposits $21,700) |
| bank-statement-2026-03.pdf | Business checking, Mar 2026 (deposits $27,400) |
| bank-statement-2026-04.pdf | Business checking, Apr 2026 (deposits $25,600) |
| bank-statement-2026-05.pdf | Business checking, May 2026 (deposits $24,200) |
| bank-statement-2026-06.pdf | Business checking, Jun 2026 (deposits $26,800) |
| bank-statement-2026-07.pdf | Business checking, Jul 2026 (deposits $21,500) |
| personal-checking-2026-07.pdf | Personal checking, Jul 2026 (ending $61,200) |

> **Note:** Total 12-month business deposits = $298,000. Monthly avg = $24,833. Qualifying income = $298K x 50% / 12 = $12,417/mo.

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge credit report. FICO 708. Tradelines: auto $320, revolving $80. No collections, no public records. |

### property/ (2 files)
| File | Description |
|---|---|
| purchase-contract.pdf | Purchase contract for 2317 Bissonnet St, $585,000 |
| property-disclosure.pdf | Seller's disclosure (SFR, built 1998, 2,420 sqft) |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0801.txt | LO intake call notes from 08/01/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: Bank statement method (deposits x expense factor / 12), Non-QM income calculation, no W-2/tax return path
- **asset-calc**: Insufficient funds detection ($82K vs $117K needed), business vs personal account separation
- **credit-report-analyzer**: Non-QM qualifying score, tradeline extraction
- **dti-calculator**: Non-QM DTI thresholds (typically 43-50%, lender-specific vs Conventional 28/36)
- **ltv-cltv**: 80% LTV Non-QM
- **payment-calculator**: PITIA at 7.25% Non-QM premium rate
- **doc-checklist**: Non-QM bank statement document requirements (12-mo statements + CPA letter, NO tax returns needed)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_bankstmt_client.py
```
