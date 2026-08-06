# Example Clients - Test Fixture Generation Standard

> This directory contains synthetic borrower files for system testing.
> Each client is a complete, self-consistent documentation set designed
> to exercise specific mortgage skills and edge cases.

## Current Clients

| # | Client | Loan Type | Purpose | PDFs | Key Test Focus |
|---|---|---|---|---|---|
| 1 | james-emily-whitfield | Conventional Conforming | Purchase (primary) | 18 | RSU averaging, large deposit sourcing, charge card exclusion |
| 2 | carlos-mendez | FHA | Purchase (primary) | 13 | Front-end DTI >31%, thin reserves, incomplete gift verification |
| 3 | sofia-reyes | Non-QM Bank Statement | Purchase (primary) | 20 | Bank statement income method, asset shortfall, no tax returns |
| 4 | marcus-chen | DSCR | Purchase (investment) | 10 | DSCR ratio, LLC reserve gap, no personal income docs |
| 5 | linda-robert-hayes | HELOC | Home equity (2nd lien) | 13 | CLTV/HCLTV, retirement income, interest-only payment |
| 6 | michael-jennifer-donnelly | VA | Purchase (primary) | 13 | Zero down, funding fee waiver (10% disability), no PMI |
| 7 | david-jennifer-park | Conventional Jumbo | Purchase (primary) | 15 | Jumbo qualifying, RSU vesting, dual high income, 4 asset accounts |
| 8 | richard-patricia-gold | Non-QM Asset Depletion | Purchase (primary) | 13 | Asset depletion (assets/360), retirement income, no W-2/tax returns |
| 9 | thomas-wright | Conventional Investment | Purchase (investment) | 11 | 75% market rent rule, Schedule E, reserve stacking, investment rate premium |
| 10 | michael-sarah-thompson | Conventional Cash-Out Refi | Cash-out refinance | 12 | Debt consolidation DTI exclusion, 80% LTV cap, FICO utilization depression |
| 11 | wei-chen | Non-QM DSCR Foreign National | Purchase (investment) | 11 | No SSN (ITIN), no US credit, foreign income docs, DSCR qualification |
| 12 | robert-chang | Non-QM 1099 Income | Purchase (primary) | 12 | 1099 aggregation, CPA P&L vs standard factor, DTI method sensitivity |

**Total: 161 text-based PDFs + 60 metadata files = 221 files.**

---

## How to Create a New Client

### Step 1: Pick a loan type

Use the [Product Taxonomy](#product-taxonomy) below to identify which loan type you need.
Each loan type determines which document clusters are required and which income calculation
method applies.

### Step 2: Define the borrower profile

Sketch out a realistic borrower story. The profile should answer three questions
(the "LO triangulation"):

1. **Who is the borrower?** - W-2 employee, self-employed, retiree, investor, foreign national...
2. **What is the property?** - Primary residence, second home, investment (1-4 unit), commercial (5+)...
3. **Which product?** - Conventional, FHA, DSCR, Bank Statement, HELOC...

The answers determine which [Document Clusters](#document-clusters) are needed.

### Step 3: Lock down the numbers

Every fixture must be **numerically self-consistent**. This is the most important rule.
Use the project's skill scripts to validate:

```powershell
# Validate LTV/CLTV
echo '{"value":720000,"loan_amount":576000}' | .\.venv\Scripts\python.exe mortgage-skills\ltv-cltv\scripts\ltv_cltv.py

# Validate DTI
echo '{"income":38234,"pitia":4875,"other_debts":1030}' | .\.venv\Scripts\python.exe mortgage-skills\dti-calculator\scripts\dti_calc.py

# Validate PITIA
echo '{"loan_amount":576000,"rate":6.5,"term":30,"tax_annual":11520,"ins_annual":2400,"hoa_monthly":75}' | .\.venv\Scripts\python.exe mortgage-skills\payment-calculator\scripts\payment_calc.py
```

The numbers in PROFILE.md, ai/profile.ai, client.yaml, and all PDFs must agree.
If income is $118K in the W-2 PDF, it must be $118K everywhere.

### Step 4: Design test traps (optional but recommended)

Each fixture should include **2-3 deliberate gaps or edge cases** to test whether the system
can detect them. Examples:

- Unverified large deposit in bank statement (no LOX on file)
- Asset shortfall (liquid funds < down payment + closing costs)
- DTI borderline (exceeds guideline but under hard cap)
- Missing donor bank statement for gift funds
- RSU averaging ambiguity (different amounts across years)

Document these traps explicitly in the client's README under "Deliberate Test Traps".

### Step 5: Generate PDFs

All PDFs must be **text-based** (selectable, extractable text), not scanned images.
Use PyMuPDF (fitz) with the project venv:

```powershell
.\.venv\Scripts\python.exe tmp\gen_<client>.py
```

See [PDF Generation Standard](#pdf-generation-standard) below for technical requirements.

### Step 6: Create metadata files

Each client needs these non-PDF files (see [Directory Structure](#directory-structure)):

- `client.yaml` - structured loan metadata
- `PROFILE.md` - LO analysis narrative
- `ai/profile.ai` - clerk-maintained verifiable facts with source citations
- `notes/intake-call-MMDD.txt` - LO intake call notes
- `README.md` - client overview and test focus

### Step 7: Validate

Run the skill scripts against your fixture numbers to confirm everything is self-consistent.
Check that every PDF is text-extractable (the generation script should assert this).

---

## Directory Structure

Every client follows this structure:

```
<client-slug>/
├── client.yaml              # Structured loan metadata (schema, name, purpose, amount, etc.)
├── PROFILE.md               # LO narrative analysis (snapshot, ratios, open items, "my read")
├── README.md                # Client overview, key numbers, test traps, document checklist
├── identity/                # Cluster 1: Identity & Occupancy
│   ├── driver-license.pdf
│   ├── occupancy-affidavit.pdf
│   └── [residency-history.pdf | business-license.pdf | llc-formation.pdf | ...]
├── income/                  # Cluster 2: Income & Employment (varies by loan type)
│   ├── [w2-*.pdf]           # QM W-2 path
│   ├── [paystub-*.pdf]      # QM W-2 path
│   ├── [voe.pdf]            # Verification of Employment (FHA/VA)
│   ├── [cpa-letter.pdf]     # Non-QM bank statement path
│   ├── [current-lease.pdf]  # DSCR path
│   └── ...
├── assets/                  # Cluster 3: Assets & Source of Funds
│   ├── [checking-*.pdf]
│   ├── [bank-statement-*.pdf]  # 12-24 months for bank statement loans
│   ├── [gift-letter.pdf]
│   ├── [donor-bank-statement.pdf]
│   └── ...
├── credit/                  # Cluster 4: Credit & Liabilities
│   └── credit-report.pdf    # Tri-merge report with FICO scores + full tradelines
├── property/                # Cluster 5: Property & Title
│   ├── [purchase-contract.pdf]  # For purchase transactions
│   ├── [property-disclosure.pdf]
│   ├── [appraisal.pdf]          # For refinance/HELOC
│   ├── [deed.pdf]               # For refinance/HELOC
│   └── ...
├── notes/
│   └── intake-call-MMDD.txt # LO intake call notes (free-form)
└── ai/
    └── profile.ai           # Clerk-maintained structured facts with source citations
```

### File naming conventions

- **Directories**: Always lowercase, match cluster names (`identity`, `income`, `assets`, `credit`, `property`)
- **PDFs**: lowercase, hyphen-separated, include date or period where applicable
  - `chase-checking-2026-07.pdf` (bank statement with period)
  - `james-w2-2025.pdf` (W-2 with borrower first name + year)
  - `bank-statement-2025-08.pdf` (bank statement loan: monthly statements)
- **Notes**: `intake-call-MMDD.txt` (date of the call)
- **No special characters** in filenames (no spaces, no Unicode)

---

## Document Clusters

All LO documentation falls into **5 clusters**. The required documents within each cluster
vary by loan type. Clusters 1 (identity), 3 (assets), and 4 (credit) are relatively fixed;
clusters 2 (income) and 5 (property) vary dramatically by loan type.

### Cluster 1: Identity & Occupancy (all loans)

| Document | Required For | Notes |
|---|---|---|
| Driver license / passport / green card | All borrowers | Government-issued photo ID |
| Occupancy affidavit | All (primary residence) | Owner-occupant intent |
| Residency history (12-month) | Most loans | Address history |
| Business license / LLC formation | Self-employed, DSCR | Entity verification |
| SSN / ITIN documentation | All | Credit pull authorization |

### Cluster 2: Income & Employment (highest variation)

This cluster changes completely based on the loan type and borrower profile:

| Loan Type | Income Documents | Method |
|---|---|---|
| **QM Conventional/FHA/VA (W-2)** | 2yr W-2 + recent paystubs + VOE | Base + bonus + overtime + RSU (2yr avg) |
| **QM Conventional (self-employed)** | 2yr 1040 + Schedule C/SE + CPA letter | Tax return net income |
| **Non-QM Bank Statement** | 12/24mo bank statements + CPA letter | Deposits x expense factor / months |
| **Non-QM 1099** | 1099 forms + bank statements | 1099 income cross-validated |
| **Non-QM P&L** | CPA-signed P&L statement | P&L net income |
| **Non-QM Asset Depletion** | Retirement/investment account statements | Assets / 360 = monthly income |
| **Non-QM DSCR** | Lease + market rent analysis (NO personal income) | Rent / PITIA = DSCR ratio |
| **Retirement income** | Pension award letter + SS benefit letter | Verified stable income |
| **Foreign National** | Home-country income (translated/notarized) | Lender-specific |

### Cluster 3: Assets & Source of Funds

| Document | Required For | Notes |
|---|---|---|
| Checking/savings statements (2mo) | All loans | Must source large deposits (>1% loan or ~$500-$1,000) |
| Investment/brokerage statements | Most loans | For reserves and asset depletion |
| Gift letter + donor bank statement | If gift funds used | Both letter AND donor capacity required |
| Business checking statements | Self-employed, DSCR | LLC/operating funds |
| Retirement account statements | HELOC, asset depletion | IRA/401k/pension |

### Cluster 4: Credit & Liabilities

| Document | Required For | Notes |
|---|---|---|
| Tri-merge credit report | All loans | Equifax + Experian + TransUnion, FICO scores, full tradelines |
| Tradeline detail | All loans | Monthly payment, balance, limit for DTI calculation |
| Payment history (existing mortgage) | Refinance, HELOC | 12-24 month history on first mortgage |
| Credit event documentation | Non-QM credit repair | Bankruptcy discharge, foreclosure completion |

### Cluster 5: Property & Title (second highest variation)

| Document | Transaction Type | Notes |
|---|---|---|
| Purchase contract | Purchase | Price, address, property type |
| Property disclosure | Purchase | Seller's disclosure (condition, age, sqft) |
| Appraisal | All (purchase: ordered during process; refi/HELOC: already done) | Market value, property details |
| Title commitment / deed | All | Ownership verification |
| First mortgage statement | Refinance, HELOC | Existing lien balance, rate, payment |
| Lease + market rent analysis | DSCR, investment | Rental income verification |
| Schedule E | Investment (context) | Existing rental properties |
| HOA documents | If applicable | Budget, insurance, CCRs |

---

## Product Taxonomy

> Condensed from the DeepSeek reference document. Full version:
> `tmp/美国的房贷产品分成那几个大类？...md`

US mortgages are a **three-dimensional structure**. Any specific loan is the intersection
of three dimensions:

- **Dimension A (Qualification):** QM vs Non-QM
- **Dimension B (Purpose):** Purchase / Refinance / Home Equity
- **Dimension C (Property):** Primary / Second home / Investment (1-4 unit) / Commercial (5+)

### Dimension A: QM vs Non-QM

```
├── QM (Qualified Mortgage)
│   ├── Conventional Conforming (Fannie/Freddie)
│   ├── Conventional Jumbo (above conforming limit)
│   ├── FHA (3.5% down, 580+ FICO)
│   ├── VA (zero down, military)
│   └── USDA (zero down, rural)
│
└── Non-QM (crosses all property uses)
    ├── Self-employed: Bank Statement / 1099 / P&L
    ├── Asset-based: Asset Depletion
    ├── Investment-only: DSCR ★ (the only investment-exclusive Non-QM)
    ├── Identity: ITIN / Foreign National
    ├── Credit repair: Recent bankruptcy / foreclosure
    └── Special: Crypto / Trust / Seasonal income
```

### Dimension B: Purpose

```
├── Purchase (buy a property)
├── Refinance
│   ├── Rate-and-Term (change rate/term, no cash)
│   ├── Cash-Out ★ (crosses into Home Equity dimension)
│   └── Streamline (FHA/VA/USDA simplified)
└── Home Equity Access (don't touch first mortgage)
    ├── HELOC (revolving credit, floating rate, IO draw period)
    └── Home Equity Loan (lump sum, fixed rate, 2nd lien)
```

### Dimension C: Property Use

```
├── Primary Residence (most loan types available)
├── Second Home (Conventional + most Non-QM)
├── Investment 1-4 Unit (Conventional Investment + DSCR + Non-QM)
└── Commercial 5+ Unit (separate underwriting world)
```

### Loan Type Matrix (which fixtures cover which types)

| Loan Type | Qualification | Purpose | Property | Fixture Client |
|---|---|---|---|---|
| Conventional Conforming | QM | Purchase | Primary | james-emily-whitfield |
| Conventional Jumbo | QM | Purchase | Primary | david-jennifer-park |
| Conventional Investment | QM | Purchase | Investment | thomas-wright |
| Conventional Cash-Out Refi | QM | Cash-out refinance | Primary | michael-sarah-thompson |
| FHA | QM | Purchase | Primary | carlos-mendez |
| VA | QM | Purchase | Primary | michael-jennifer-donnelly |
| HELOC | QM | Home equity | Primary (existing) | linda-robert-hayes |
| Non-QM Bank Statement | Non-QM | Purchase | Primary | sofia-reyes |
| Non-QM 1099 Income | Non-QM | Purchase | Primary | robert-chang |
| Non-QM Asset Depletion | Non-QM | Purchase | Primary | richard-patricia-gold |
| DSCR | Non-QM | Purchase | Investment | marcus-chen |
| Non-QM DSCR Foreign National | Non-QM | Purchase | Investment | wei-chen |

### Fixture pipeline (planned)

| Tier | Loan Types | Status |
|---|---|---|
| **Tier 1 (done)** | Conventional / FHA / Bank Statement / DSCR / HELOC | 5 clients created |
| **Tier 2 (done)** | VA / Jumbo / Asset Depletion / Conventional Investment / Cash-Out Refi | 5 clients created |
| **Tier 3 (done)** | Foreign National DSCR / 1099 Income | 2 clients created |
| **Tier 4 (planned)** | USDA / Credit Repair (bankruptcy) / S-Corp Self-Employed / Second Home | Not yet started |

---

## Key Metrics & Formulas

Every fixture must have internally consistent calculations. Here are the core formulas
used across all loan types:

### LTV / CLTV / HCLTV

```
LTV    = First Loan Amount / Property Value
CLTV   = (First Loan + Second Loan) / Property Value
HCLTV  = (First Loan + HELOC Full Draw) / Property Value
```

Typical limits: Conventional purchase 80-97%, FHA 96.5%, DSCR 75%, HELOC CLTV 80-90%.

### DTI (Debt-to-Income)

```
Front-end DTI = PITIA / Monthly Income        (housing only)
Back-end DTI  = (PITIA + Other Debts) / Monthly Income  (all debts)
```

Typical limits: Conventional 28/36, FHA 31/43 (manual) or AUS, VA 41%, Non-QM 43-50%.

### PITIA (Principal, Interest, Taxes, Insurance, HOA)

```
PITIA = P&I + (Property Tax / 12) + (Insurance / 12) + HOA + MIP (if FHA)
```

For FHA, add annual MIP / 12 to PITIA.

### DSCR (Debt Service Coverage Ratio)

```
DSCR = Gross Monthly Rent / PITIA
```

Minimum: 1.0 (floor), 1.25 (standard pricing tier).

### Income Calculation Methods

| Method | Formula |
|---|---|
| **W-2 base** | Annual base / 12 |
| **W-2 bonus/overtime** | 2-year average / 12 |
| **RSU (Fannie)** | 2-year vesting average / 12 |
| **Bank Statement** | Total deposits x expense factor / months |
| **DSCR** | Rent / PITIA (not personal income) |
| **Asset Depletion** | Eligible assets / 360 |
| **Pension/SS** | Monthly benefit amount |

### FHA MIP Structure

```
Upfront MIP = 1.75% x Base Loan Amount  (financed into loan)
Annual MIP  = 0.55% x Base Loan Amount / 12  (monthly, for life of loan at >90% LTV)
Total Loan  = Base Loan + Upfront MIP
```

---

## PDF Generation Standard

All fixture PDFs must be **text-based** (selectable text, extractable via `get_text()`),
not scanned image PDFs.

### Requirements

1. **Use PyMuPDF (fitz)** with the project venv
2. **Base-14 fonts only** (Helvetica family) - these only support Latin-1 encoding
3. **Normalize non-Latin-1 punctuation** before inserting text:
   - Em dash `—` (U+2014) -> `-`
   - En dash `–` (U+2013) -> `-`
   - Smart quotes `''""` -> `''""`
4. **Verify text extraction** after generation: `assert title in page.get_text()`
5. **Page size**: US Letter (612 x 792 points)
6. **Margins**: 72pt (1 inch) left/right, 72pt top

### Generation script template

```python
import fitz, os

PAGE_W, PAGE_H = 612, 792
ROOT = os.path.join("examples", "clients", "<client-slug>")

def _clean(s):
    """Normalize non-Latin-1 punctuation for base-14 fonts."""
    return (s.replace("\u2014", "-").replace("\u2013", "-")
             .replace("\u2019", "'").replace("\u2018", "'")
             .replace("\u201c", '"').replace("\u201d", '"'))

def make_pdf(rel_path, title, body_items):
    """
    rel_path: relative path from client root, e.g. "income/james-w2-2025.pdf"
    title:    string, shown as page title
    body_items: list of (kind, text) tuples where kind is:
        "h" -> section header (bold, 12pt)
        "p" -> paragraph (word-wrapped, 11pt)
        "kv" -> key-value line (11pt)
    """
    title = _clean(title)
    body_items = [(k, _clean(t)) for k, t in body_items]
    path = os.path.join(ROOT, *rel_path.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)

    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = 72
    page.insert_text((72, y), title, fontsize=16, fontname="hebo")  # Helvetica-Bold
    y += 24

    for kind, text in body_items:
        if kind == "h":
            y += 8
            page.insert_text((72, y), text, fontsize=12, fontname="hebo")
            y += 20
        elif kind == "p":
            for line in _wrap(text, width=85):
                page.insert_text((72, y), line, fontsize=11, fontname="helv")
                y += 16
        else:  # kv
            page.insert_text((72, y), text, fontsize=11, fontname="helv")
            y += 16
        if y > PAGE_H - 60:
            break

    doc.save(path)
    doc.close()

    # Verify text is extractable
    d = fitz.open(path)
    assert title in d[0].get_text(), f"Text extraction failed for {path}"
    d.close()
```

### Existing generation scripts

| Script | Client |
|---|---|
| `tmp/gen_example_client.py` | james-emily-whitfield |
| `tmp/gen_fha_client.py` | carlos-mendez |
| `tmp/gen_bankstmt_client.py` | sofia-reyes |
| `tmp/gen_dscr_client.py` | marcus-chen |
| `tmp/gen_heloc_client.py` | linda-robert-hayes |
| `tmp/gen_va_client.py` | michael-jennifer-donnelly |
| `tmp/gen_jumbo_client.py` | david-jennifer-park |
| `tmp/gen_asset_depletion_client.py` | richard-patricia-gold |
| `tmp/gen_conv_investment_client.py` | thomas-wright |
| `tmp/gen_cashout_refi_client.py` | michael-sarah-thompson |
| `tmp/gen_foreign_dscr_client.py` | wei-chen |
| `tmp/gen_1099_client.py` | robert-chang |

---

## Metadata File Standards

### client.yaml

```yaml
schema: 1
name: <Borrower Name>
purpose: <purchase | refinance | heloc | cash_out>
amount: <loan amount in dollars>
stage: docs
city: <City, State>
contact:
  phone: "+1 (xxx) xxx-xxxx"
  email: <borrower>@example.com
borrowers:
  - name: <Borrower Name>
    role: borrower
    citizenship: us_citizen
  - name: <Co-borrower Name>     # if applicable
    role: co_borrower
    citizenship: us_citizen
created: YYYY-MM-DD
```

### PROFILE.md structure

```markdown
# <Borrower Name> - <Loan Type>, <City>

## Snapshot
- Borrowers, purpose, property, price, loan amount, LTV, FICO

## Borrower facts
- Employment, income sources, citizenship

## Income (LO estimate)
- Monthly income breakdown by source

## Ratios
- PITIA, front-end DTI, back-end DTI

## Assets
- Account balances, gift funds, cash to close, reserves

## Open items
- What's still missing or pending

## My read
- LO's qualitative assessment of the file

## Open questions
- Items to verify with underwriting or borrower
```

### ai/profile.ai structure

```markdown
# <Borrower Name> - clerk

> Maintained by clerk - as of <date>
> Verifiable facts with sources. Judgement and strategy live in PROFILE.md.

## Loan
- purpose, amount, stage, location, occupancy, target program (each with source citation)

## Borrowers
- Name, role, citizenship, employment (with source citations)

## Income
- Each income source with monthly amount and source document

## Equity / LTV
- Appraised value, loan amounts, LTV, CLTV (with calculations)

## Credit
- FICO scores, qualifying score, payment history, tradelines

## Ratios
- PITIA, front/back DTI

## Assets
- Each account with balance and source document

## Property
- Type, ownership, taxes, insurance, existing mortgage details

## Documents on file
- Full file listing by cluster

## Open items
- Pending documents and conditions

## Context
- Chronological log of key events (intake call, etc.)
```

### notes/intake-call-MMDD.txt

Free-form LO intake call notes. Should capture:
- Borrower name(s) and property address
- Loan purpose and target program
- Key financial details (income, assets, credit)
- LO's qualitative read
- Next steps

---

## Reference

- **DeepSeek product taxonomy conversation:**
  `tmp/deepseek-chat.md`
  (Full 1161-line conversation covering product classification tree, Non-QM family,
  Cash-Out Refinance positioning, LO documentation clusters, and workflow)

- **Skill scripts for validation:**
  - `mortgage-skills/ltv-cltv/scripts/ltv_cltv.py`
  - `mortgage-skills/dti-calculator/scripts/dti_calc.py`
  - `mortgage-skills/payment-calculator/scripts/payment_calc.py`

- **Existing real clients (for structural reference):**
  `nmls-10293847/clients/` (daniel-grace-okafor, priya-raman, etc.)
