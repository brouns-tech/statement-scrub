# Third-party components and provenance

The repository contains our implementation, not copied implementations from the investigated anonymisation projects. Installed dependency distributions carry their own licence files. Preserve those when redistributing them; this file is not a replacement for their notices.

| Direct component | Pinned version | Upstream licence / notes |
| --- | --- | --- |
| pypdfium2 | 5.14.0 | Apache-2.0 OR BSD-3-Clause; bundled PDFium has BSD-style and third-party notices |
| ReportLab | 5.1.0 | BSD-style; see installed distribution's licence |
| pypdf | 7.1.0 | BSD-3-Clause |
| Streamlit | 1.50.0 | Apache-2.0 |
| PyMuPDF / MuPDF | 2.1 | AGPL-3.0 or commercial; combined distribution is not MIT-only |
| phonenumbers | 9.0.43 | Apache-2.0 |
| streamlit-image-coordinates | 0.4.1 | MIT |
| python-stdnum | 2.1 | LGPL-2.1-or-later; used as an unmodified installed dependency for IBAN/BIC validation |

The application does not bundle NLP model weights. `uv.lock` pins the resolved dependency graph; install with `uv sync --extra dev` for that exact graph, or use the pip instructions for compatible transitive dependencies. Frozen/binary redistribution requires a full transitive/native notice inventory before release.

Research/design references (no source code copied):

- [Microsoft Presidio](https://github.com/microsoft/presidio): candidate detection framework; not a dependency in this MVP.
- [Redacto](https://github.com/Taronyuu/redacto-nl): existing Dutch/English Presidio integration to evaluate for an optional detector.
- [Rotterdam / MinBZK maskeringsscript](https://github.com/MinBZK/maskeringsscript): Dutch financial/text detection comparison candidate (EUPL-1.2).
- [UK bank statement anonymiser](https://github.com/boscorat/uk-bank-statement-anonymiser): PDF-preservation investigation informed the decision to reconstruct fresh PDFs instead of global string rewriting.
- [Anonymiq](https://github.com/ConductionNL/anonymiq): reversible output paths are unsuitable for public synthetic fixtures.

Project-specific review details, source revisions and experiment results are in the comments of WR-4. No third-party project licence implies clearance for its dependencies or model weights.

## Direct-editing licence boundary

PyMuPDF/MuPDF is supplied under AGPL or commercial terms: https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright . Preserve its notices and comply with the applicable combined-work/source-availability obligations when distributing or serving the application. The project's MIT source notice does not relicense PyMuPDF. No binary release or remote service is published by this implementation task.
