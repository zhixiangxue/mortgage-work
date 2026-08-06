# David & Jennifer Park - Jumbo Purchase

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | David Park (borrower) + Jennifer Park (co-borrower) |
| **Loan Type** | Jumbo Conventional (exceeds ~$806,500 conforming limit) |
| **Purpose** | Purchase, primary residence |
| **Property** | 18400 N Scottsdale Rd, Scottsdale, AZ 85255 (new construction) |
| **Purchase Price** | $1,100,000 |
| **Loan Amount** | $880,000 (80% LTV) |
| **Rate** | 30-yr fixed @ 6.25% |
| **Qualifying FICO** | 748 (Jennifer, lower) |

## Client Story

David is a Director of Engineering at Intel earning $210K base + ~$75K RSU (2-yr avg). Jennifer is a Senior PM at AWS earning $175K. Together they pull in ~$38K/mo qualifying income. They're buying a $1.1M new construction luxury home in Silverleaf with 20% down ($220K).

The loan at $880K exceeds the conforming limit (~$806,500), so it's a Jumbo. They qualify easily: FICO 748, DTI at 19% back-end, and $1.6M in liquid assets (211 months of reserves - absurdly excessive for any Jumbo program's 6-12 month requirement).

## Key Numbers

| Metric | Value |
|---|---|
| Combined monthly income | $38,333 ($17,500 + $6,250 RSU + $14,583) |
| Proposed PITIA | $6,518/mo (P&I $5,418 + tax $700 + ins $250 + HOA $150) |
| Front-end DTI | 17.0% |
| Back-end DTI | 19.1% |
| LTV | 80.0% (20% down, no PMI) |
| Liquid assets | $110K checking + $850K brokerage + $635K 401k = $1,595,074 |
| Reserves post-close | ~$1,375,074 (~211 months PITIA) |

## Deliberate Test Traps

1. **Conforming vs Jumbo threshold** - Loan amount $880K exceeds the conforming limit (~$806,500). The system must recognize this as a Jumbo loan, not a Conventional Conforming. Jumbo has stricter requirements (700+ FICO, 20% down, 6-12mo reserves) but no PMI at 80% LTV.
2. **RSU 2-year averaging** - 2024 vesting $55K, 2025 vesting $95K, 2026 projected $120K. Per Fannie/Freddie guidelines, RSU income uses a 2-yr average ($75K/yr). The system should NOT use the latest year ($95K or $120K annualized) alone.
3. **Semi-monthly payroll income** - Jennifer is paid semi-monthly (24 pay periods). Each check is $7,291.67. Monthly income = $14,583, NOT $7,292. The system must correctly annualize from pay frequency, not just multiply the single check.
4. **Amex Platinum charge card exclusion** - Listed with $8,500 balance but no preset spending limit. Should be excluded from DTI (or use reported monthly payment if any). The credit report explicitly notes "pay in full, current."
5. **$15,000 Vanguard-to-Chase transfer** - Large inter-account transfer visible in both statements. Should be recognized as internal asset transfer (not unexplained large deposit) since the matching Vanguard liquidation is documented.

## Document Checklist

### identity/ (3 files)
| File | Description |
|---|---|
| driver-license.pdf | David + Jennifer driver licenses (AZ) |
| occupancy-affidavit.pdf | Primary residence intent (joint) |
| residency-history.pdf | 2-year residency history |

### income/ (5 files)
| File | Description |
|---|---|
| david-paystub-2026-07.pdf | Intel paystub Jul 2026 ($17,500/mo, YTD $122,500) |
| david-w2-2025.pdf | 2025 W-2 ($245K Box 1, $95K Box 12-V RSU) |
| david-rsu-statement.pdf | RSU vesting: 2023 $42K, 2024 $55K, 2025 $95K, 2-yr avg $75K/yr |
| jennifer-paystub-2026-07.pdf | AWS paystub Jul 2026 ($7,291.67 semi-monthly, YTD $87,500) |
| jennifer-w2-2025.pdf | 2025 W-2 ($175K Box 1) |

### assets/ (4 files)
| File | Description |
|---|---|
| chase-checking-2026-07.pdf | Chase Private Client Checking joint, $110,000 (contains $15K Vanguard transfer + $22K EMD withdrawal) |
| vanguard-brokerage-2026-06.pdf | Vanguard joint brokerage, $850K (VTSAX/VTIAX/VBTLX/VMFXX) |
| david-401k-2026-06.pdf | David Intel 401(k) (Fidelity), $420,575 |
| jennifer-401k-2026-06.pdf | Jennifer Amazon 401(k) (Fidelity), $214,499 |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge. David 762, Jennifer 748, qualifying 748. BMW lease $650, Chase Sapphire $150, Amex Platinum (charge card, excluded). No collections, no public records. |

### property/ (2 files)
| File | Description |
|---|---|
| purchase-contract.pdf | Purchase contract $1,100,000, Jumbo financing, 20% down |
| property-disclosure.pdf | New construction SFR, built 2025, 3,800 sqft, 5bd/4.5ba, pool/spa, smart home. HOA $150/mo. |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0806.txt | LO intake call notes from 08/06/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: RSU 2-yr averaging, semi-monthly payroll annualization, high-income dual W-2
- **asset-calc**: Inter-account transfer tracing ($15K Vanguard->Chase), 401(k) reserve calculation, Jumbo reserve requirement (6-12 months)
- **credit-report-analyzer**: Charge card exclusion (Amex Platinum), dual co-borrower FICO selection
- **dti-calculator**: Jumbo DTI thresholds (typically 43%, lender-specific)
- **ltv-cltv**: Jumbo at 80% LTV (no PMI), conforming vs jumbo loan size detection
- **payment-calculator**: PITIA on high-value property ($1.1M)
- **doc-checklist**: Jumbo-specific requirements (appraisal by lender panel, 6-12mo reserves)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_jumbo_client.py
```
