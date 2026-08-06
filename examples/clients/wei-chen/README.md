# Wei Chen - Non-QM DSCR Foreign National

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Wei Chen (PRC citizen, foreign national) |
| **Loan Type** | Non-QM DSCR (Foreign National) |
| **Purpose** | Purchase, investment (non-owner occupied duplex) |
| **Property** | 2615 Westheimer Rd, Houston, TX 77098 (Duplex, 2 units) |
| **Purchase Price** | $350,000 |
| **Loan Amount** | $245,000 (70% LTV) |
| **Rate** | 30-yr fixed @ 7.5% (foreign national premium) |
| **DSCR** | 1.34 (rent $3,200 / PITIA $2,388) |
| **Identification** | ITIN 987-65-4321 (NO SSN) |

## Client Story

Wei Chen is a Chinese citizen and Senior Software Architect at Shenzhen Yuanjing Technology earning ~$92K USD. He wants to invest in US real estate - a $350K duplex in Houston's Galleria area. Both units are already leased at $1,600/mo ($3,200 total gross rent).

For qualification, this is a DSCR loan: the property's cash flow qualifies the loan, not personal income. DSCR = $3,200 / $2,388 PITIA = 1.34, which exceeds the 1.25 standard threshold. The borrower has no SSN (uses ITIN), no US credit history (China Baihang score 782), and funds were wired from China Merchants Bank.

This file tests whether the system can handle a completely foreign documentation set: passport instead of driver license, ITIN instead of SSN, international credit instead of US tri-merge, translated income documents, and foreign wire transfer for source of funds.

## Key Numbers

| Metric | Value |
|---|---|
| Gross monthly rent | $3,200 (Unit A $1,600 + Unit B $1,600) |
| Monthly PITIA | $2,388 (P&I $1,713 + tax $525 + ins $150) |
| DSCR | **1.34** (passes 1.25 standard) |
| LTV | 70.0% (30% down, no PMI) |
| Foreign income (context) | ~$92,182/yr (660,000 CNY at 7.16 CNY/USD) |
| China credit score | 782 (Baihang, excellent) |
| US credit score | None (no SSN, no US history) |
| Wire transfer | $140,000 from China Merchants Bank |

## Deliberate Test Traps

1. **No SSN (ITIN only)** - The borrower has no US Social Security Number. The system must NOT flag "missing SSN" as an error or blocker. ITIN 987-65-4321 is a valid tax identification for foreign nationals. This is the #1 most common system failure on foreign national files.
2. **No US credit history** - No US tri-merge credit report exists. The international credit report (China Baihang score 782) is the alternative. The system must NOT flag "missing credit report" as an error. For Non-QM DSCR, international credit is acceptable.
3. **DSCR qualification independent of personal income** - The system must understand that for DSCR loans, the property's cash flow qualifies the loan. Personal income documentation (translated Chinese bank statements) is supplementary context, not the qualification basis. The DSCR ratio (1.34) is the qualifying metric.
4. **Foreign document validation** - All income documents are originally in Chinese, translated and notarized. The system must recognize translated/notarized/apostilled documents as valid. Employment verification includes apostille via Texas Secretary of State.
5. **Foreign source of funds** - The $140,000 wire transfer originated from China Merchants Bank. The system must verify: W-8BEN on file, OFAC/AML screening passed, source of funds traced to 8 years of verified salary/savings.

## Document Checklist

### identity/ (3 files)
| File | Description |
|---|---|
| passport.pdf | PRC passport (EY89345672), B1/B2 US visa, valid to 2031 |
| itin-letter.pdf | IRS CP565 ITIN assignment (987-65-4321), no SSN |
| occupancy-affidavit.pdf | Investment property (non-owner occupied), signed via RON from Shenzhen |

### income/ (2 files) - Foreign verification (NOT primary qualification for DSCR)
| File | Description |
|---|---|
| foreign-employment-letter.pdf | Shenzhen Yuanjing Technology, ~$92K/yr. Translated/notarized/apostilled. |
| foreign-bank-statements.pdf | China Merchants Bank 12-month summary. Avg $6,680/mo USD. Translated. |

### assets/ (2 files)
| File | Description |
|---|---|
| us-checking-2026-07.pdf | Wells Fargo Checking, $35,000. Opened 06/2026 via wire. No payroll. |
| wire-transfer-confirmation.pdf | $140,000 from CMB. W-8BEN, OFAC clear, source verified. |

### credit/ (1 file)
| File | Description |
|---|---|
| international-credit-report.pdf | Experian International (China bureau). Baihang 782. No US credit. 0 late in 5yr. |

### property/ (3 files)
| File | Description |
|---|---|
| purchase-contract.pdf | $350,000, Non-QM DSCR Foreign National, 30% down, close 09/30/2026 |
| property-disclosure.pdf | Duplex 2012, 2,800 sqft. Both units leased $1,600/mo. Tax $6,300/yr. Flood Zone X. |
| lease-analysis.pdf | Current leases + 3 market comps. DSCR calculation: 1.34. |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0805.txt | LO intake call notes from 08/05/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: Foreign income documentation recognition, DSCR method (property cash flow, not personal income), currency conversion handling
- **dti-calculator**: DSCR ratio calculation (rent / PITIA), no personal DTI needed for DSCR program
- **ltv-cltv**: Foreign national DSCR at 70% LTV (25-30% down requirement)
- **payment-calculator**: PITIA with Houston's high property taxes (~1.8%), wind/hail insurance
- **credit-report-analyzer**: International credit report (no US FICO), Baihang score interpretation
- **doc-checklist**: Foreign national documentation set (passport, ITIN, translated docs, international credit, wire transfer)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_foreign_dscr_client.py
```
