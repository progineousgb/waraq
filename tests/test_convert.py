import io
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from waraq.cli import main
from waraq.convert import ConvertError, convert_path

HTML_SAMPLE = """<!DOCTYPE html>
<html>
<head>
<title>Ignore Me</title>
<style>h1{color:red}</style>
</head>
<body>
<h1>Title</h1>
<p>Hello <a href="https://example.com">link</a>.</p>
<p>مرحبا</p>
<ul>
<li>One</li>
<li>Two</li>
</ul>
<script>alert(1)</script>
</body>
</html>
"""

DOCX_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>First paragraph</w:t></w:r></w:p>
    <w:p>
      <w:r><w:t xml:space="preserve">مرحبا </w:t></w:r>
      <w:r><w:t>بالعالم</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""


def simple_pdf(text):
    stream = f"BT /F1 12 Tf 72 72 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    objects[3] = b"4 0 obj\n" + objects[3]
    header = b"%PDF-1.4\n"
    body = b"".join(objects)
    offsets = []
    pos = len(header)
    for obj in objects:
        offsets.append(pos)
        pos += len(obj)
    xref = ["xref\n0 6\n", "0000000000 65535 f \n"]
    for offset in offsets:
        xref.append(f"{offset:010d} 00000 n \n")
    trailer = (
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{pos}\n%%EOF\n".encode("ascii")
    )
    return header + body + "".join(xref).encode("ascii") + trailer


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, data):
        path = Path(self.tmp.name) / name
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8", newline="\n")
        return path

    def test_txt_passthrough(self):
        path = self.write("note.txt", "hello\nworld")
        self.assertEqual(convert_path(path), "hello\nworld\n")
        self.assertNotIn("#", convert_path(path))

    def test_md_passthrough(self):
        path = self.write("note.md", "# already\n\ntext\n")
        self.assertEqual(convert_path(path), "# already\n\ntext\n")

    def test_csv_table(self):
        path = self.write("rows.csv", "name,city\nAda,Cairo\n")
        self.assertEqual(
            convert_path(path),
            "| name | city |\n| --- | --- |\n| Ada | Cairo |\n",
        )

    def test_csv_unicode_and_pipe(self):
        path = self.write("rows.csv", 'اسم,note\nليلى,"a|b"\n')
        out = convert_path(path)
        self.assertIn("ليلى", out)
        self.assertIn("a\\|b", out)
        self.assertIn("| --- | --- |", out)

    def test_html_structure(self):
        path = self.write("page.html", HTML_SAMPLE)
        out = convert_path(path)
        self.assertEqual(
            out,
            "# Title\n\nHello [link](https://example.com).\n\nمرحبا\n\n- One\n- Two\n",
        )
        self.assertNotIn("Ignore Me", out)
        self.assertNotIn("alert", out)
        self.assertNotIn("color", out)

    def test_docx_paragraphs(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as package:
            package.writestr("word/document.xml", DOCX_XML.encode("utf-8"))
        path = self.write("sample.docx", buf.getvalue())
        self.assertEqual(convert_path(path), "First paragraph\n\nمرحبا بالعالم\n")

    def test_docx_too_large_is_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("word/document.xml", b"<a>" + b" " * (65 * 1024 * 1024) + b"</a>")
        path = self.write("big.docx", buf.getvalue())
        with self.assertRaisesRegex(ConvertError, "too large"):
            convert_path(path)

    def test_docx_deep_nesting(self):
        w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        xml = (
            f'<w:document xmlns:w="{w}"><w:body><w:p>'
            + "<w:r>" * 5000
            + "<w:t>deep</w:t>"
            + "</w:r>" * 5000
            + "</w:p></w:body></w:document>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as package:
            package.writestr("word/document.xml", xml)
        path = self.write("deep.docx", buf.getvalue())
        self.assertEqual(convert_path(path), "deep\n")

    def test_pdf_text(self):
        path = self.write("hello.pdf", simple_pdf("HelloPDF"))
        out = convert_path(path)
        self.assertIn("HelloPDF", out)

    def test_unknown_extension(self):
        path = self.write("blob.bin", b"abc")
        with self.assertRaises(ConvertError):
            convert_path(path)

    def test_cli_output_file(self):
        src = self.write("rows.csv", "a,b\n1,2\n")
        dest = Path(self.tmp.name) / "out.md"
        code = main([str(src), "-o", str(dest)])
        self.assertEqual(code, 0)
        self.assertEqual(
            dest.read_text(encoding="utf-8"),
            "| a | b |\n| --- | --- |\n| 1 | 2 |\n",
        )

    def test_cli_missing_file(self):
        missing = Path(self.tmp.name) / "nope.csv"
        with redirect_stderr(io.StringIO()):
            code = main([str(missing)])
        self.assertEqual(code, 1)

    def test_html_pretty_lists(self):
        path = self.write(
            "list.html",
            "<ul>\n<li>\nOne\n</li>\n<li><p>Two</p></li>\n</ul>\n"
            "<ol>\n<li>\nFirst\n</li>\n<li>Second</li>\n</ol>\n",
        )
        self.assertEqual(
            convert_path(path),
            "- One\n- Two\n1. First\n2. Second\n",
        )

    def test_html_link_parentheses_and_unclosed(self):
        path = self.write(
            "links.html",
            '<p><a href="https://en.wikipedia.org/wiki/Foo_(bar)">Wiki</a></p>'
            '<p>Hello <a href="http://x.com">link</p>',
        )
        out = convert_path(path)
        self.assertIn("https://en.wikipedia.org/wiki/Foo_(bar)", out)
        self.assertNotIn("%29", out)
        self.assertIn("link", out)
        self.assertIn("http://x.com", out)


class SafetyTests(unittest.TestCase):
    def test_unsafe_schemes_are_dropped(self):
        from waraq.convert import html_to_markdown
        for href in ["javascript:alert(1)", "JavaScript:alert(1)", "java\tscript:alert(1)",
                     " javascript:alert(1)", "data:text/html,x", "vbscript:x", "file:///etc/passwd"]:
            out = html_to_markdown(f'<p><a href="{href}">click</a></p>')
            self.assertEqual(out, "click\n", href)

    def test_safe_schemes_are_kept(self):
        from waraq.convert import html_to_markdown
        self.assertEqual(html_to_markdown('<p><a href="https://a.example/x">a</a></p>'), "[a](https://a.example/x)\n")
        self.assertEqual(html_to_markdown('<p><a href="http://a.example">a</a></p>'), "[a](http://a.example)\n")
        self.assertEqual(html_to_markdown('<p><a href="mailto:x@a.example">m</a></p>'), "[m](mailto:x@a.example)\n")
        self.assertEqual(html_to_markdown('<p><a href="/docs/page">r</a></p>'), "[r](/docs/page)\n")

    def test_escaped_markup_stays_text(self):
        from waraq.convert import html_to_markdown
        out = html_to_markdown("<p>&lt;script&gt;alert(1)&lt;/script&gt; &amp; more</p>")
        self.assertNotIn("<script>", out)
        self.assertEqual(out, "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more\n")
        out = html_to_markdown('<p><a href="https://a.example">&lt;img src=x onerror=alert(1)&gt;</a></p>')
        self.assertNotIn("<img", out)


if __name__ == "__main__":
    unittest.main()
