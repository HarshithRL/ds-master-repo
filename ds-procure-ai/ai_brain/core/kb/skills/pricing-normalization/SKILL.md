---
name: pricing-normalization
description: Use when extracting or comparing commercial terms — rate cards,
  day rates vs fixed fee vs T&M, multi-year discounts, FTE/man-day conversion,
  currency, Etex-side effort, Annexe A02, or when two vendors quote in
  different structures and must be compared.
---
# Pricing normalization

## Offer types (closed)

`pricing_line.offer_type` is only `fixed_price` or `time_and_materials`.
Reject any other label; do not coerce "blended" or "retainer" into either
without a cited sentence that maps it.

## Rate structures

- **Day rate** — one person-day. Record `rate` + `rate_unit=day`.
- **Hourly** — do not convert to day unless the cited page gives the hours
  per day. If it does not, leave `rate_unit=hour` and do not invent 8h.
- **FTE / man-day** — convert only with an explicit factor on the page
  (e.g. "1 FTE = 220 days"). Otherwise `not_stated` for the converted figure.
- **Fixed fee** — `offer_type=fixed_price`, `line_total` from the cited
  number. Do not derive it from a rate × days unless both factors are cited.

## Comparing T&M to fixed-price

Do not produce a single "equivalent price" unless both sides share cited
volume (days or FTE) and currency. Prefer two rows, one per `offer_type`.
Multi-year discounts stay on `discount_terms`; do not bake them into year-1
`line_total`.

## Currency and Etex effort

Default display currency in this corpus is EUR. Do not FX-convert.
`etex_effort_days` is buyer-side time (RACI / Annexe A02), never vendor
days relabelled. If A02 is incomplete, set `annexe_a02_completed=0`.
