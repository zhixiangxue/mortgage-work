/* ================= Mock data: clients ================= */
export const CLIENTS = [
  { id: "sarah",  name: "Sarah Mitchell",  purpose: "Purchase", amount: "$680,000", stage: "docs",   stageLbl: "Collecting Docs", missing: 3, touched: "2h ago",  city: "Irvine, CA" },
  { id: "james",  name: "James & Amy Chen", purpose: "Purchase", amount: "$1,150,000", stage: "active", stageLbl: "Pre-Approved", missing: 0, touched: "Yesterday", city: "San Jose, CA" },
  { id: "robert", name: "Robert Alvarez",  purpose: "Refinance", amount: "$412,000", stage: "docs",   stageLbl: "Collecting Docs", missing: 5, touched: "3d ago",  city: "Phoenix, AZ" },
  { id: "nina",   name: "Nina Petrova",    purpose: "Cash-out Refi", amount: "$520,000", stage: "lead", stageLbl: "New Lead", missing: 0, touched: "1w ago", city: "Seattle, WA" },
];

export const CLOSED = [
  { id: "tom",    name: "Tom Becker",  purpose: "Purchase", amount: "$495,000", stage: "closed", stageLbl: "Closed 06/30", missing: 0, touched: "Jun 30", city: "Austin, TX" },
  { id: "lisa",   name: "Lisa Wong",   purpose: "Refinance", amount: "$310,000", stage: "closed", stageLbl: "Closed 05/12", missing: 0, touched: "May 12", city: "Denver, CO" },
];

export const PURPOSES = ["Purchase", "Refinance", "Cash-Out Refinance", "HELOC", "Investment Property"];

/* Citizenship status drives product eligibility (agency vs Non-QM etc.) */
export const CITIZENSHIP = ["US Citizen", "Permanent Resident", "Non-Permanent Resident", "Foreign National"];

/* Underwriting looks at the least favorable status across all borrowers;
   the array above is ordered from least to most restrictive */
export const effectiveCitizenship = statuses =>
  statuses.reduce((worst, s) => CITIZENSHIP.indexOf(s) > CITIZENSHIP.indexOf(worst) ? s : worst, CITIZENSHIP[0]);
