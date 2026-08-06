# Linda & Robert Hayes - HELOC (Home Equity Line of Credit)

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Linda Hayes (borrower) + Robert Hayes (co-borrower) |
| **Loan Type** | HELOC (Home Equity Line of Credit) - Second Lien |
| **Purpose** | Home improvements (kitchen renovation + pool deck resurfacing) |
| **Subject Property** | 7820 E Mountain View Rd, Scottsdale, AZ 85255 |
| **Appraised Value** | $650,000 (appraisal dated 2026-08-03) |
| **Existing First Mortgage** | $278,000 @ 3.25% fixed (Rocket Mortgage) |
| **Requested HELOC** | $100,000 (interest-only draw period) |
| **LTV (first only)** | 42.8% |
| **CLTV (first + HELOC)** | 58.2% |
| **Qualifying FICO** | 778 (Robert, lower) |

## Client Story

Linda is a middle school principal earning $118K/year. Robert retired in June 2024 and collects a pension ($4,850/mo from Arizona State Retirement) plus Social Security ($2,650/mo). Together they earn ~$17,333/mo.

They've owned their Scottsdale home since 2016 (paid $485K, now appraised at $650K). Their first mortgage is at an excellent 3.25% rate, which they absolutely do not want to disturb. Instead of a cash-out refinance (which would mean giving up that rate), they're taking a $100K HELOC as a second lien to fund a kitchen renovation ($60K) and pool deck resurfacing ($40K).

This is a textbook clean HELOC file: massive equity ($372K available, requesting only 27%), pristine credit (FICO 778+, zero lates in 24 months), and rock-solid income. CLTV at 58% is well within any HELOC program's comfort zone.

## Key Numbers

| Metric | Value |
|---|---|
| Combined monthly income | $17,333/mo (Linda $9,833 + Robert pension $4,850 + Robert SS $2,650) |
| Monthly housing cost | $2,558/mo (first mortgage $1,850 + HELOC IO at full draw $708) |
| Other monthly debts | $425/mo (auto $380 + revolving $45) |
| Front-end DTI | 14.8% |
| Back-end DTI | 17.2% |
| **LTV (first only)** | **42.8%** ($278K / $650K) |
| **CLTV (first + HELOC)** | **58.2%** (($278K + $100K) / $650K) |
| Available equity | $372,000 |
| HELOC as % of equity | 27% |
| Post-HELOC equity cushion | $272,000 (41.8%) |
| Liquid assets | $49,000 (checking) + $528,500 (IRA) = $577,500 |

## HELOC Structure

| Parameter | Value |
|---|---|
| Credit line | $100,000 |
| Draw period | 10 years (interest-only on drawn balance) |
| Repayment period | 20 years (P&I after draw period ends) |
| Rate | Prime + 0.5% margin (floating, currently ~8.5% APR) |
| Interest-only payment at full draw | $100K @ 8.5% / 12 = ~$708/mo |
| Closing costs | Minimal (~$500, appraisal already completed) |
| Use of proceeds | Kitchen renovation (~$60K) + pool deck resurfacing (~$40K) |

## Deliberate Test Traps

1. **Second lien, not a purchase** - Unlike the other 4 clients, this is NOT a purchase transaction. The system should recognize the HELOC purpose and switch to CLTV/HCLTV calculations instead of simple LTV. It should also recognize the existing first mortgage as a competing lien.
2. **Retirement income qualification** - Robert's pension ($4,850) and Social Security ($2,650) must be qualified as stable income. The system should accept retirement income documentation (award letters/benefit statements) as valid income, not flag them as "non-W-2."
3. **Interest-only payment calculation** - The HELOC payment during the draw period is interest-only, which is calculated differently from amortizing P&I. At full draw ($100K @ ~8.5%), the monthly payment is ~$708, not a standard amortized payment.

## Document Checklist

### identity/ (2 files)
| File | Description |
|---|---|
| driver-license.pdf | Linda + Robert driver licenses (AZ) |
| occupancy-affidavit.pdf | Primary residence confirmation (required: HELOC is only for owner-occupied) |

### income/ (4 files)
| File | Description |
|---|---|
| linda-paystub-2026-07.pdf | Linda paystub Jul 2026 (Principal, Scottsdale USD, $9,833/mo gross) |
| linda-w2-2025.pdf | Linda 2025 W-2 (Box 1: $118,000) |
| robert-pension-statement.pdf | Robert pension benefit letter (AZ State Retirement, $4,850/mo, retired 06/01/2024) |
| robert-social-security.pdf | Robert Social Security benefit letter ($2,650/mo, early retirement at 62) |

### assets/ (2 files)
| File | Description |
|---|---|
| checking-2026-07.pdf | BofA joint checking, ending $49,000 (Jul 2026) |
| ira-statement-2026-06.pdf | Fidelity IRA (Robert), $528,500 (Jun 2026) |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge credit report. Linda FICO 792 (rep), Robert FICO 778 (rep). Qualifying = 778 (lower). First mortgage: 0x30 late in 24 months. Tradelines: first mortgage, auto $380, revolving $45. No collections, no public records, 0 inquiries in 12 months. |

### property/ (4 files)
| File | Description |
|---|---|
| deed.pdf | Warranty deed showing ownership since 05/22/2016, original purchase $485,000 |
| first-mortgage-statement.pdf | Rocket Mortgage statement (current balance $278,000 @ 3.25% fixed, P&I $1,570/mo + escrow $280/mo) |
| appraisal.pdf | Full appraisal dated 2026-08-03, appraised value $650,000 (SFR, Pueblo style, built 2004, 2,960 sqft, 4bd/3ba, in-ground pool) |
| property-disclosure.pdf | Property disclosure (taxes $6,800/yr, insurance $2,400/yr with pool rider, no HOA) |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0804.txt | LO intake call notes from 08/04/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: W-2 + pension + Social Security income qualification, retirement income documentation
- **asset-calc**: Joint checking + retirement account (IRA) verification, reserve calculation
- **credit-report-analyzer**: Dual co-borrower FICO selection (lower = 778), first mortgage payment history, tradeline extraction
- **dti-calculator**: HELOC interest-only payment in front-end DTI, extremely low ratios
- **ltv-cltv**: HELOC-specific CLTV and HCLTV calculations (first + second lien), LTV with existing mortgage
- **payment-calculator**: Interest-only payment at floating rate (Prime + margin)
- **doc-checklist**: HELOC-specific documents (existing mortgage statement, deed, appraisal for existing property)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_heloc_client.py
```
