# Statement Scrub

A local, review-led tool for turning financial PDFs into synthetic development fixtures through reviewed, destructive text replacement. Its first consumer is [Werkelijk Rendement](https://github.com/brouns-tech/box3-werkelijk-rendement), but it runs independently.

**Developer preview:** this is a working manual-review MVP, not an automatic anonymisation guarantee. It supports text-based bank-statement layouts and a fictional single-account ledger. A human decides what is safe to retain. International IBANs, BICs, Dutch phone/address patterns, calendar dates, money, generic headings and labelled/description-column content are recognised. Unknown free text still requires review. No institution-specific adapters are used.

## Run

Requires Python 3.11–3.13. From this repository:

```sh
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
statement-scrub ui
```

Open `http://127.0.0.1:8501`. The launcher binds to loopback, disables Streamlit telemetry/file watching, and leaves XSRF protection enabled. Do not run this as a public or shared server.

Choose a PDF with the single document picker. Optional synthetic settings are always visible beside it, with explanatory tooltips. Click **Anonymise** to apply them and start review. No source-directory configuration is stored or used. Use `--port` if another local application occupies port 8501.

Try a wholly fabricated example first:

```sh
statement-scrub demo --output /path/outside/the/repository/demo.pdf
```

The demo command refuses to overwrite existing files. Use one fictional transaction when mapping the demo.

## Review workflow

1. Choose one PDF and click **Anonymise**. The optional seed/year/count settings need no adjustment to get started.
2. In **PDF · click to edit**, click a text field. Its original and replacement appear in the adjacent editor. Green means replaced; amber means unresolved or blocked; grey means kept/omitted. A recognised field is not a document-level approval.
3. Select a synthetic field or edit **Replacement text**, then **Apply and confirm**. Increase width if the original space is too narrow. Layout failures are flagged per field and keep the original in the draft; they block final export.
4. Use **Redact a region** and drag over private image content, signatures or other regions. Affected text fields are also omitted. Undo restores the last region's field decisions.
5. Inspect **Edited PDF**. The original layout, images, graphics and untouched fonts are retained. Selected text is actually removed, not covered by an overlay. Replacement text reuses the embedded font if its characters are available; otherwise the UI reports a compatible-family fallback.
6. Expand **Detailed field review** only when useful. Unresolved decisions appear first; a reason explains the matched rule or fit problem.
7. Resolve outstanding fields, review images and all output pages, and check accounting relationships before downloading. Any edits invalidate prior output approvals.

The editing engine uses PyMuPDF redaction/reinsertion on an in-memory copy. It strips metadata, attachments, annotations, forms, links, scripts and other document-level auxiliary structures, and saves a new non-incremental file with garbage collection. The original is never modified. Drafts may still contain unresolved private text and cannot be downloaded through the review gate.

The synthetic scenario is independent of source values and provides internally consistent account/transaction fields. **Generic detection does not infer every accounting role.** Automatically replacing a date/amount is not proof that the displayed statement reconciles; verify or remap balances, totals and transaction relationships before sharing.

The privacy boundary remains the reviewer plus the explicit export gates. Generic labels are kept only after sensitive context and typed-value rules have been considered. No document text, maps, source paths or source hashes are published automatically. Address/phone validation runs locally; no addresses or document content are sent to lookup services.

## Current limits

- Text-based PDFs only, up to 30 MB / 30 pages / 150,000 characters. Scans, encrypted PDFs, rotated pages and optional-content layers are unsupported.
- Rotated marginal text is not yet represented by editable fields; final export is blocked on such documents. The original remains visible for inspection.
- Some fonts are subsets lacking replacement glyphs. These use a reported fallback; font appearance is not guaranteed to be identical in every PDF. Fit failures leave the original visible and require resolution.
- Generic detection is not full NER. Unknown personal/free text requires review. Street/postcode recognition does not establish that an address exists. BIC validation establishes syntax, not current bank registration.
- Only a single-account synthetic bank ledger is modelled. Broker/securities, multi-currency and linked-account accounting are not reconciled automatically.
- Images and graphics are retained; redact private image regions explicitly and inspect all pages. PDF redaction has limits on unusual content, so no guarantee of anonymity is made for arbitrary PDFs.
- Review state is memory-only. Closing/restarting loses decisions. Keep source files and downloaded candidates outside the repository.
- Native PDF parsing is local, not a hardened sandbox. Only open documents you trust to process locally.

## Development and verification

```sh
python -m pytest -q
python -m build
```

Tests generate their PDFs from fabricated strings, including hidden attachment/annotation/metadata markers, repeated amounts and split glyphs. No private fixture corpus is distributed. CI is configured for Linux and Windows on Python 3.11/3.13; configured jobs are not evidence of a completed Windows validation.

The design and discovery work is tracked in [WR-4](https://brouns.atlassian.net/browse/WR-4). Experiment details and follow-ups belong in its comments. The safe-contribution release gate remains open until wider layout/privacy validation and the fixture-intake workflow are complete.

## Reuse and licensing

Our original source files remain MIT licensed. **The direct-editing dependency PyMuPDF/MuPDF is AGPL-3.0 or commercially licensed.** The MIT notice does not remove the AGPL obligations for distributing the combined application or providing a network service. This local developer preview is not a claim that a bundled binary can be distributed under MIT alone. Review the combined distribution/source-offer requirements before a release, or obtain an appropriate commercial licence.

We reuse python-stdnum for IBAN/BIC validation, phonenumbers (libphonenumber) for phone validation, PDFium for extraction/preview, PyMuPDF for editing, streamlit-image-coordinates for clicking/region selection, and Streamlit for the UI. ReportLab remains for wholly fabricated fixtures and the earlier reconstruction test baseline. No anonymisation-framework source code is copied into this repository.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [generic rule design](docs/generic-rules.md). Dependencies are pinned in `uv.lock`; private source documents and machine-specific settings are excluded from Git.
