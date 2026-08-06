# James & Emily Whitfield - Conventional Conforming Purchase

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | James Whitfield (borrower) + Emily Whitfield (co-borrower) |
| **Loan Type** | Conventional Conforming (Fannie Mae) |
| **Purpose** | Purchase, primary residence |
| **Property** | 3724 Cedar Ridge Pass, Austin, TX 78737 |
| **Purchase Price** | $720,000 |
| **Loan Amount** | $576,000 (80% LTV) |
| **Rate** | 30-yr fixed @ 6.5% |
| **Qualifying FICO** | 762 (Emily, lower co-borrower) |

## Client Story

James is a Senior Engineering Manager at Vantage Technologies earning $215K base + ~$26K bonus + ~$94K RSU. Emily is a Marketing Director at BrightPath Media earning $148K base + ~$7K bonus. Both are W-2 employees with stable employment history. They're buying their first home in Austin at $720K with 20% down to avoid PMI.

The file is clean: strong dual income (~$38K/mo qualifying), low DTI (front 12.7% / back 15.4%), ample assets ($165K checking + $285K brokerage + $50K gift). FICO 762 is solidly Conventional-tier.

## Key Numbers

| Metric | Value |
|---|---|
| Combined monthly income | ~$38,234 |
| Proposed PITIA | $4,875/mo (P&I $3,640 + tax $960 + ins $200 + HOA $75) |
| Front-end DTI | 12.7% |
| Back-end DTI | 15.4% |
| Liquid assets | $165,840 (checking) + $285,000 (brokerage) |
| Gift funds | $50,000 (from father, gift letter + donor statement on file) |
| Cash to close | ~$136,800 |

## Deliberate Test Traps

This fixture is designed with specific gaps to test system capabilities:

1. **Unverified $8,500 Zelle deposit** (chase-checking-2026-07.pdf, 07/12 entry) - No LOX on file. The system should flag this as a large/unexplained deposit that must be sourced or backed out.
2. **RSU 2-year averaging ambiguity** - 2025 W-2 Box 12-V shows $54,600; 2026 annualizes to $93,600. Fannie requires 2-yr trend. The system should recognize RSU income needs averaging, not just take the latest figure.
3. **Amex Platinum charge card** - Listed in credit report with $3,200 balance but no preset spending limit. The system should exclude this from DTI (or use monthly payment if reported).

## Document Checklist

### identity/ (3 files)
| File | Description |
|---|---|
| driver-license.pdf | James + Emily driver licenses (TX) |
| occupancy-affidavit.pdf | Primary residence intent affidavit |
| residency-history.pdf | 2-year residency history |

### income/ (7 files)
| File | Description |
|---|---|
| james-w2-2025.pdf | James 2025 W-2 ($215K Box 1, $54,600 Box 12-V RSU) |
| james-paystub-2026-06.pdf | James paystub Jun 2026 |
| james-paystub-2026-07.pdf | James paystub Jul 2026 (YTD gross $136,400) |
| james-rsu-statement.pdf | RSU vesting schedule + 2-yr history |
| emily-w2-2025.pdf | Emily 2025 W-2 ($148K Box 1) |
| emily-paystub-2026-06.pdf | Emily paystub Jun 2026 |
| emily-paystub-2026-07.pdf | Emily paystub Jul 2026 (YTD gross $80,300) |

### assets/ (5 files)
| File | Description |
|---|---|
| chase-checking-2026-06.pdf | Chase Premier Checking statement Jun 2026 |
| chase-checking-2026-07.pdf | Chase Premier Checking statement Jul 2026 (contains $8,500 Zelle trap) |
| vanguard-brokerage-2026-06.pdf | Vanguard Brokerage statement ($285K market value) |
| gift-letter.pdf | Gift letter from Robert Whitfield (father), $50,000 |
| donor-bank-statement.pdf | Donor's bank statement confirming capacity |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge credit report. James FICO 786, Emily FICO 762. Tradelines: auto $545, student loan $385, two revolving (min $100 + Amex charge $3,200) |

### property/ (2 files)
| File | Description |
|---|---|
| purchase-contract.pdf | Purchase contract for 3724 Cedar Ridge Pass, $720,000 |
| property-disclosure.pdf | Seller's property disclosure (SFR, built 2014, 2,840 sqft) |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0728.txt | LO intake call notes from 07/28/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: RSU 2-yr averaging, dual W-2 income, bonus annualization
- **asset-calc**: Large deposit sourcing ($8,500 Zelle), gift fund verification, reserve calculation
- **credit-report-analyzer**: Tradeline extraction, charge card exclusion logic, FICO qualifying score selection
- **dti-calculator**: Front/back DTI with full tradeline schedule
- **ltv-cltv**: 80% LTV conventional purchase
- **payment-calculator**: PITIA calculation at 6.5%
- **doc-checklist**: Verify all 5 document clusters present

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_example_client.py
```
