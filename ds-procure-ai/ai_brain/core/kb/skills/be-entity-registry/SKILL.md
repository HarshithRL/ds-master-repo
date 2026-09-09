---
name: be-entity-registry
description: Use when reading Belgian KBO/BCE extracts, mapping BE-X registry
  ids to legal entities, distinguishing KPMG Advisory SRL from KPMG Belgium
  BV (Group), rostering BDO from an Etex-named file, or splitting a
  TriFinance+Inetum consortium into two entities under one bid.
---
# Belgian entity registry (KBO/BCE)

## Identifiers

Belgian legal entities in this corpus use `BE-X-…` (enterprise numbers
with the `BE-X-` prefix as stored on `vendor.registry_id`). Trading name
≠ contracting entity. Match on registry id first, then legal name.

## Roster that must not be collapsed

This programme is **6 legal entities / 5 bids**:

| Bid (`artifact.vendor_id`) | Legal entities |
|---|---|
| KPMG (two entities, two artifacts) | KPMG Advisory SRL (`BE-X-439819279`); KPMG Belgium BV (Group) |
| PwC | PwC entity as cited |
| EY | EY entity as cited |
| BDO | BDO — filename is `Etex - SWIFT Support Independent Assessment_…`. Filenames lie. |
| TriFinance+Inetum | **One consortium bid, two entities.** Artifact column holds the *bid* id. Graph holds `MEMBER_OF_CONSORTIUM`. Never one `vendor_id` for both. |

A separate registry extract `TRIFINANCE_BELGIUM_NV_BE-X-882734939` is the
TriFinance legal entity, not a second bid.

## Reading an extract

- Legal name, enterprise number, and address come from the extract page.
- Parent/subsidiary (KPMG Group vs Advisory SRL) is a cited graph edge,
  not a rename.
- Do not treat "Belgium BV (Group)" CSR highlights as the Advisory SRL
  proposal, or vice versa.
