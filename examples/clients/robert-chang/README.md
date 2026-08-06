# Robert Chang - Non-QM 1099 Income

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Robert James Chang (sole proprietor, IT contractor) |
| **Loan Type** | Non-QM 1099 Income |
| **Purpose** | Purchase, primary residence (first-time homebuyer) |
| **Property** | 4827 Madison Ave, San Diego, CA 92115 (SFR, built 1962, remodeled 2019) |
| **Purchase Price** | $575,000 |
| **Loan Amount** | $460,000 (80% LTV) |
| **Rate** | 30-yr fixed @ 6.875% |
| **Qualifying FICO** | 738 |

## Client Story

Robert is a 39-year-old IT contractor who has been freelancing for 4 years. His primary clients are Microsoft and Amazon (through staffing agencies Insight Global and Kelly Services), plus smaller direct contracts with Qualcomm and Sony. His 1099 income has grown steadily: $132K (2024) to $145K (2025), averaging $138,500/yr gross.

The critical test: the income calculation method. With a CPA-prepared P&L showing actual expenses ($17K/yr average), qualifying income is $10,125/mo and back-end DTI is 43.1% (passes Non-QM 50%). With a standard 25% expense factor, qualifying income drops to $8,656/mo and back-end DTI becomes 50.4% (fails Non-QM 50% by 0.4 points). The method choice determines qualification.

## Key Numbers

| Metric | CPA P&L Method | Standard Factor (25%) |
|---|---|---|
| 2-yr avg gross | $138,500/yr | $138,500/yr |
| Expenses | $17,000 (actual) | $34,625 (25% factor) |
| Net income | $121,500/yr = **$10,125/mo** | $103,875/yr = **$8,656/mo** |
| PITIA | $3,710/mo | $3,710/mo |
| Front-end DTI | 36.6% | 42.9% |
| Back-end DTI | **43.1% (PASS Non-QM 50%)** | **50.4% (FAIL Non-QM 50%)** |

## Deliberate Test Traps

1. **Multiple 1099-NEC aggregation** - The borrower has 3 separate 1099-NEC forms for 2025 ($85K + $42K + $18K = $145K total) plus a summary for 2024 ($132K). The system must aggregate ALL forms to arrive at total income. Missing any one form understates income.
2. **CPA P&L vs standard expense factor** - This is the make-or-break trap. CPA P&L with actual expenses ($17K/yr) gives $10,125/mo income and 43.1% DTI (passes). Standard 25% factor gives $8,656/mo income and 50.4% DTI (fails by 0.4%). The system must correctly apply the CPA method when a CPA-prepared P&L is on file.
3. **No W-2 (pure 1099)** - The borrower has no W-2 employer. The system must NOT flag "missing W-2" as an error. All income is 1099-NEC from multiple payers.
4. **Business vs personal accounts** - The borrower has both a Chase Business Checking (~$48K, operating funds) and Chase Personal Checking ($22K). Owner draws transfer from business to personal monthly. The system must distinguish business operating funds from personal reserves.
5. **Charge card exclusion** - Amex Blue is a charge card (paid in full monthly, no preset limit). Standard practice excludes charge cards from DTI. The system must NOT include the $1,200 Amex balance in DTI calculation.
6. **Income trending** - Income grew 9.8% YoY ($132K to $145K). The system should use 2-year average (standard Non-QM approach), not just the most recent year, even though the most recent year would produce better DTI.

## Document Checklist

### identity/ (2 files)
| File | Description |
|---|---|
| driver-license.pdf | Robert Chang driver license (CA) |
| business-license.pdf | San Diego Business Tax Certificate (sole proprietor, NAICS 541512) |

### income/ (5 files) - 1099-NEC forms + CPA P&L
| File | Description |
|---|---|
| 1099-nec-microsoft-2025.pdf | Insight Global (for Microsoft), $85,000 |
| 1099-nec-amazon-2025.pdf | Kelly Services (for Amazon), $42,000 |
| 1099-nec-others-2025.pdf | Qualcomm $12K + Sony $4K + others $2K = $18,000 |
| 1099-summary-2024.pdf | 2024 summary: $132K total (Microsoft $78K + Amazon $38K + direct $16K) |
| cpa-profit-loss.pdf | CPA-prepared 2-yr P&L. Net: 2024 $116K, 2025 $127K, avg $121.5K |

### assets/ (2 files)
| File | Description |
|---|---|
| chase-personal-2026-07.pdf | Chase Personal Checking, $22,000. Shows owner draws from business. |
| vanguard-brokerage-2026-06.pdf | Vanguard taxable brokerage, $95,000 (ETFs + cash) |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge. FICO 738. Auto $450 + student $200 + revolving $40. Amex Blue charge card (excluded). First-time buyer (no mortgage history). |

### property/ (2 files)
| File | Description |
|---|---|
| purchase-contract.pdf | $575,000, Non-QM 1099, 20% down, close 09/28/2026 |
| property-disclosure.pdf | SFR 1962 (remodeled 2019), 1,850 sqft, 3bd/2ba. Tax $6,325/yr. |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0806.txt | LO intake call notes from 08/06/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: 1099-NEC income aggregation (multiple forms), CPA P&L method vs standard expense factor, sole proprietor income calculation, income trending (2-yr average)
- **dti-calculator**: Non-QM DTI thresholds (50% cap), charge card exclusion, sensitivity to income method
- **ltv-cltv**: Non-QM 1099 at 80% LTV (no PMI)
- **payment-calculator**: PITIA for California (Prop 13 tax rate ~1.1%)
- **credit-report-analyzer**: Charge card exclusion (Amex Blue), first-time homebuyer (no mortgage history)
- **doc-checklist**: Non-QM 1099 document requirements (1099-NEC forms, CPA P&L, business license, NO W-2)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_1099_client.py
```
