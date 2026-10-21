# waraq

waraq converts one file to Markdown. It looks at the extension, converts that file, and writes the Markdown to standard output, or to the path you pass with `-o`.

## What you get

Markdown text. A `.txt` or `.md` file is copied through. HTML becomes headings, paragraphs, links, and lists. A CSV file becomes a Markdown table whose first row is the header. A Word file becomes one block of text per paragraph. A PDF becomes the text extracted from each page.

With no `-o`, that text is the whole standard output. With `-o`, waraq writes the same text to that file as UTF-8 and prints nothing.

## Install and run

waraq needs Python 3.11 or newer. From this directory:

```
pip install -e .
```

The install puts a `waraq` command on PATH and installs pypdf, which PDF conversion uses. Then:

```
waraq notes.html
waraq roster.csv
waraq note.docx -o note.md
```

`python -m waraq` runs the same program. Paths below are examples; any filename works.

## Example

These results are from running `waraq` on this machine. The Markdown blocks are the standard output, unchanged.

`notes.html`:

```html
<!DOCTYPE html>
<html>
<head>
<title>Field notes</title>
</head>
<body>
<h1>Field notes</h1>
<p>See the <a href="https://example.com/report">report</a> before the gate check.</p>
<ul>
<li>North gate</li>
<li>South gate</li>
</ul>
</body>
</html>
```

`waraq notes.html` printed:

```markdown
# Field notes

See the [report](https://example.com/report) before the gate check.

- North gate
- South gate
```

`roster.csv`:

```csv
name,role,note
Ada,editor,on time
Lin,runner,"a|b"
```

`waraq roster.csv` printed:

```markdown
| name | role | note |
| --- | --- | --- |
| Ada | editor | on time |
| Lin | runner | a\|b |
```

The pipe in `a|b` is escaped so it stays inside the cell.

A `.docx` whose paragraphs were `Shift notes.` and `The gate was open.` was converted with `waraq note.docx`. It printed:

```text
Shift notes.

The gate was open.
```

A one-page PDF whose page text is `HelloPDF` was converted with `waraq hello.pdf`. It printed:

```text
HelloPDF
```

## Flags and files

```text
waraq [-h] [-o OUTPUT] file
```

`file` is the input path. The extension selects the converter:

- `.txt` and `.md` are copied. Newlines are normalized, and a final newline is added when the file does not already end with one.
- `.html` and `.htm` keep `h1` through `h6`, paragraphs, links, `ul` / `ol` / `li`, `strong` / `b`, `em` / `i`, `code`, and line breaks. `script`, `style`, `head`, and `title` are dropped. An image contributes its alt text.
- `.csv` is read as comma-separated values. The first row is the header. Short rows are padded to the widest row. A newline inside a cell becomes a space.
- `.docx` is read as a zip package. Paragraph text comes from `word/document.xml`, which may be at most 64 MB once unpacked.
- `.pdf` is read with pypdf. Each non-empty page is one block.

`-o` and `--output` write the Markdown to that path instead of stdout. `-h` and `--help` print the usage line.

Text inputs have to be UTF-8. A leading BOM is accepted. A missing file, a directory, an unsupported extension, a CSV waraq cannot parse, or a docx that is not a zip of `word/document.xml` prints `waraq: ...` on standard error and exits 1.

From this directory, the tests are:

```text
python -m unittest discover -s tests -v
```

## Limits

waraq does not turn HTML tables into Markdown tables. Each cell is a separate block of text. This file:

```html
<table>
<tr><th>Site</th><th>Status</th></tr>
<tr><td>North</td><td>open</td></tr>
</table>
```

`waraq table.html` printed:

```text
Site

Status

North

open
```

A docx is paragraph text. Styles, lists, and tables from Word are not rebuilt. Empty paragraphs are skipped, and a blank line separates the paragraphs that remain.

Encrypted PDFs are rejected. The error is `encrypted PDF is not supported`. If pypdf is not installed, a PDF exits with an error and the other extensions still work. A page with no extracted text is omitted.
