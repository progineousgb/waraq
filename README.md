waraq converts a file to Markdown.

Install from this directory:

```
pip install -e .
```

Usage:

```
waraq FILE [-o OUT]
```

With no `-o`, Markdown is written to standard output.

```
waraq notes.html -o notes.md
```

Supported types are `.txt`, `.md`, `.html`, `.htm`, `.csv`, `.docx`, and `.pdf`.
PDF needs pypdf, which the install above pulls in. If that package is missing, PDF exits with an error and the other types still work.

`.txt` and `.md` are copied through without added headings or code fences.
HTML keeps headings, links, lists, and paragraphs.
CSV (comma-separated) becomes a table.
A Word file becomes one block per paragraph, with a blank line between blocks.
Characters are copied as they appear in the file, including non-ASCII and right-to-left text.

Tests:

```
python -m unittest discover -s tests -v
```
