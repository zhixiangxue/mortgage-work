# Michael & Jennifer Donnelly - VA Purchase

> **Fixture client for system testing** - Generated 2026-08-07

## Client Overview

| Field | Value |
|---|---|
| **Borrower** | Michael Donnelly (borrower, US Army veteran) + Jennifer Donnelly (co-borrower) |
| **Loan Type** | VA (Veterans Affairs) |
| **Purpose** | Purchase, primary residence |
| **Property** | 4218 Eagleview Dr, Colorado Springs, CO 80918 |
| **Purchase Price** | $450,000 |
| **Loan Amount** | $450,000 (100% LTV, zero down) |
| **VA Funding Fee** | $0 (WAIVED - 10% service-connected disability) |
| **Rate** | 30-yr fixed @ 5.5% |
| **No PMI** | VA loans have no PMI at any LTV |
| **Qualifying FICO** | 718 (Michael, lower co-borrower) |

## Client Story

Michael is an Army veteran (2010-2018, E-5 Sergeant, two tours in Afghanistan) now serving as a Police Officer in Colorado Springs. Jennifer is an RN at UCHealth Memorial Hospital. Together they earn ~$12,675/mo ($78K police + $175 VA disability + $72K nursing).

They're buying a $450K home with 100% VA financing - zero down payment. Michael's 10% service-connected disability rating (hearing loss) exempts them from the VA funding fee ($10,350 saved) and VA loans have no PMI. Seller is contributing $9K toward closing costs, so their out-of-pocket is minimal.

## Key Numbers

| Metric | Value |
|---|---|
| Combined monthly income | $12,675 ($6,500 + $175 VA disability + $6,000) |
| Proposed PITIA | $3,060/mo (P&I $2,555 + tax $350 + ins $130 + HOA $25) |
| Front-end DTI | 24.1% |
| Back-end DTI | 30.7% |
| LTV | 100.0% (zero down, VA allows up to 100%) |
| VA funding fee | $0 (exempt - 10% disability, normally $10,350) |
| Checking balance | $19,605 (Jul 2026) |
| Seller concessions | $9,000 (VA max 4% of purchase price) |

## Deliberate Test Traps

1. **Funding fee waiver detection** - COE shows 10% service-connected disability rating. Per 38 USC 3729(b), this means the VA funding fee is WAIVED ($0, not $10,350). The system must read the COE and apply the exemption. The payment calculator at 100% LTV would not know about this - it's VA-specific logic.
2. **No PMI at 100% LTV** - Standard payment/LTV calculators will flag PMI required at 100% LTV. But VA loans are exempt from PMI at ALL LTV levels. The system should recognize VA = no PMI and not add $386/mo to PITIA.
3. **Tax-free disability income** - Michael's $175/mo VA disability is tax-free and counts as qualifying income at full amount (no gross-up needed). The system should recognize this as valid income from the VA award letter.
4. **PERA-exempt W-2** - Michael's W-2 shows $0 Social Security wages (Colorado PERA government pension exemption). This is normal but may confuse automated income verification that expects SS wages > 0.

## Document Checklist

### identity/ (4 files)
| File | Description |
|---|---|
| driver-license.pdf | Michael + Jennifer driver licenses (CO) |
| occupancy-affidavit.pdf | Primary residence intent (joint) |
| dd-214.pdf | Michael's DD-214: US Army 2010-2018, E-5 Sergeant, Honorable discharge |
| coe.pdf | VA Certificate of Eligibility: entitlement $112,500, first-time use, 10% disability -> funding fee EXEMPT |

### income/ (5 files)
| File | Description |
|---|---|
| michael-paystub-2026-07.pdf | CSPD paystub Jul 2026 ($6,500/mo monthly, YTD $48,300) |
| michael-w2-2025.pdf | 2025 W-2 ($78,200 Box 1, PERA exempt SS = $0) |
| jennifer-paystub-2026-07.pdf | UCHealth paystub Jul 2026 ($2,769 bi-weekly, YTD $40,200) |
| jennifer-w2-2025.pdf | 2025 W-2 ($72,400 Box 1) |
| va-disability-letter.pdf | VA award letter: 10% rating, $175.08/mo, tax-free |

### assets/ (1 file)
| File | Description |
|---|---|
| chase-checking-2026-07.pdf | Chase Total Checking joint, ending $19,605 (Jul 2026) |

### credit/ (1 file)
| File | Description |
|---|---|
| credit-report.pdf | Tri-merge. Michael 718, Jennifer 735, qualifying 718. Tradelines: auto $445, student $285, revolving $95 + $0. No collections, no public records. |

### property/ (2 files)
| File | Description |
|---|---|
| purchase-contract.pdf | Purchase contract $450,000, VA financing, zero down, $9K seller concessions |
| property-disclosure.pdf | SFR built 2005, 2,400 sqft, 4bd/3ba, 2-car garage. Radon mitigation installed. HOA $25/mo. |

### notes/ (1 file)
| File | Description |
|---|---|
| intake-call-0805.txt | LO intake call notes from 08/05/2026 |

### ai/ (1 file)
| File | Description |
|---|---|
| profile.ai | Clerk-maintained structured facts with source citations |

## Skills to Test

- **income-calc**: W-2 + VA disability (tax-free) income qualification, dual W-2, PERA-exempt SS wages
- **asset-calc**: No down payment scenario, seller concessions toward closing costs
- **credit-report-analyzer**: Dual co-borrower FICO selection (lower = 718)
- **dti-calculator**: VA thresholds (back 41%, no front-end limit), residual income concept
- **ltv-cltv**: 100% LTV (VA max), no PMI despite 100% LTV
- **payment-calculator**: VA-specific: no PMI in PITIA, no funding fee financed
- **doc-checklist**: VA-specific documents (DD-214, COE, disability letter)

## Regeneration

```powershell
.\.venv\Scripts\python.exe tmp\gen_va_client.py
```
