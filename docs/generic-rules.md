# Generic financial-document rules

Rules are independent of institution names and file paths. No bank adapter, private name/address list or document-derived configuration is shipped.

## Priority

1. Explicit sensitive labels and adjacent values (name, address, account, reference), plus address-block geometry. A value under “Naam” is replaced even when it equals a generic word such as “Datum”.
2. Validated structured values: international IBAN country/length/checksum rules from python-stdnum; BIC token syntax; phone numbering plans from phonenumbers. Invalid IBAN-like data is still replaced, but flagged.
3. Dutch postcode/street patterns, email shapes, calendar-valid dates, decimal/currency amounts. These identify value types, not financial roles or real-world identity. No remote lookup.
4. Description-column geometry derived from generic headers, not a particular bank template. Whole descriptions are replaced, including multiline fragments. Keywords inside transaction content are not automatically exempt.
5. Exact generic template vocabulary and structural pagination. Mixed or unexplained content stays unresolved. BIC detection requires a single uppercase token or explicit label; whitespace removal must not turn pagination into a false BIC.

## Corpus investigation

A local read-only pass extracted 106,062 fragments from 484 PDFs. An initial generic-vocabulary pass found recurring labels such as Omschrijving, Rekeningnummer, BIC, Pagina and Betaalrekening. A later candidate-vocabulary pass checked document-frequency counts for generic terms such as jaaroverzicht, tegenrekening, boekingsdatum and mededeling. Only general rules and aggregate observations are recorded here; no private documents, text samples, names, addresses, filenames, paths or maps are included.

In one five-page bank statement, the earlier matcher left 201 unknown fragments; the expanded rules left 87 and the direct-editing engine performed 134 replacements with no font fallback. This is a usability observation, not measured PII recall, anonymisation certification, or evidence that all accounting relationships are correct.

## Limits and follow-ups

- Distinguish detection certainty from financial reconciliation. Review the ledger at document level; do not assign a low detector score to every clearly recognisable money value merely because its accounting role is unknown.
- A live address lookup discloses the query and does not prove anonymity. A future optional local address database (such as a locally provisioned BAG extract) could validate address existence without a network request. It must not be committed as personal configuration.
- Unknown free text still needs review. Evaluate an existing Dutch NER integration on fabricated ground truth rather than adding bank-specific exceptions.
- Prefer regression tests with fabricated layouts and deliberate collisions over learning an unrestricted allowlist from private document text.
