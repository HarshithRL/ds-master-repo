# KB builder

Read-only `/project/**`. Write evidence via structured output only — never invent numbers.

- Bid id is `artifact.vendor_id`. A consortium is one bid, multiple legal entities.
- `not_stated` ≠ `not_offered` ≠ `extraction_failed`.
- Citation-or-abstain: claim_text + artifact_id + page, or status `not_stated`.
- Dual offer: T&M and fixed_price are separate `pricing_line` rows.
