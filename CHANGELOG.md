# Changelog

## v0.1.1 (2026-10-22)

- Keep only http, https, mailto, and relative links. Other schemes such as javascript: are dropped.
- Encode &, <, and > in text so escaped markup never becomes real HTML.
- README: setup steps for Linux, macOS, and Windows.
- Add a CI workflow for ruff and tests.

## v0.1.0 (2026-10-21)

First tagged release. Convert documents to Markdown.

- Add waraq, a file-to-Markdown converter.
- Document waraq's converters with Markdown from a real run.
- Limit decompressed size and nesting depth, handle corrupt files
