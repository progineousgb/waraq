import csv
import io
import re
import zipfile
import zlib
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_DOCX_XML = 64 * 1024 * 1024

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ConvertError(Exception):
    pass


def convert_path(path):
    try:
        return _convert_path(path)
    except OSError as exc:
        raise ConvertError(str(exc)) from exc


def _convert_path(path):
    src = Path(path)
    if not src.exists():
        raise ConvertError(f"no such file: {path}")
    if not src.is_file():
        raise ConvertError(f"not a file: {path}")
    ext = src.suffix.lower()
    if ext in {".txt", ".md"}:
        return _text_file(src)
    if ext in {".html", ".htm"}:
        return html_to_markdown(_read_text(src))
    if ext == ".csv":
        return csv_to_markdown(_read_text(src))
    if ext == ".docx":
        return docx_to_markdown(src)
    if ext == ".pdf":
        return pdf_to_markdown(src)
    raise ConvertError(f"unsupported file type: {ext or src.name}")


def _read_text(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConvertError(f"file is not valid UTF-8: {path}") from exc


def _text_file(path):
    text = _read_text(path).replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def csv_to_markdown(text):
    try:
        parsed = csv.reader(io.StringIO(text))
        rows = [row for row in parsed if row]
    except csv.Error as exc:
        raise ConvertError(f"could not read CSV: {exc}") from exc
    if not rows:
        return ""
    width = max(len(row) for row in rows)

    def cell(value):
        value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
        return value.replace("|", "\\|").strip()

    def line(row):
        cells = [cell(value) for value in row]
        if len(cells) < width:
            cells.extend([""] * (width - len(cells)))
        return "| " + " | ".join(cells) + " |"

    body = [line(rows[0]), "| " + " | ".join(["---"] * width) + " |"]
    body.extend(line(row) for row in rows[1:])
    return "\n".join(body) + "\n"


def docx_to_markdown(path):
    try:
        with zipfile.ZipFile(path) as package:
            try:
                info = package.getinfo("word/document.xml")
            except KeyError as exc:
                raise ConvertError("docx is missing word/document.xml") from exc
            # file_size comes from the zip header, so the read is capped too.
            if info.file_size > MAX_DOCX_XML:
                raise ConvertError("docx text part is too large")
            try:
                with package.open(info) as part:
                    xml = part.read(MAX_DOCX_XML + 1)
            except (RuntimeError, NotImplementedError, zlib.error) as exc:
                raise ConvertError("could not read docx") from exc
            if len(xml) > MAX_DOCX_XML:
                raise ConvertError("docx text part is too large")
    except zipfile.BadZipFile as exc:
        raise ConvertError("not a docx file") from exc
    if xml.startswith(b"\xef\xbb\xbf"):
        xml = xml[3:]
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ConvertError(f"could not read docx: {exc}") from exc
    paragraphs = []
    for node in root.iter(W + "p"):
        text = _paragraph_text(node).strip()
        if text:
            paragraphs.append(text)
    if not paragraphs:
        return ""
    return "\n\n".join(paragraphs) + "\n"


def _paragraph_text(paragraph):
    # Nested w:p nodes are visited by the caller on their own.
    # A stack instead of recursion, so deeply nested XML cannot crash it.
    parts = []
    stack = list(reversed(list(paragraph)))
    while stack:
        child = stack.pop()
        if child.tag == W + "p":
            continue
        if child.tag == W + "t":
            parts.append(child.text or "")
        elif child.tag == W + "tab":
            parts.append("\t")
        elif child.tag in {W + "br", W + "cr"}:
            parts.append("\n")
        else:
            stack.extend(reversed(list(child)))
    return "".join(parts)


def pdf_to_markdown(path):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ConvertError("PDF support needs pypdf (pip install pypdf)") from exc
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ConvertError("encrypted PDF is not supported")
        pages = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            extracted = extracted.strip()
            if extracted:
                pages.append(extracted)
    except ConvertError:
        raise
    except Exception as exc:
        raise ConvertError(f"could not read PDF: {exc}") from exc
    if not pages:
        return ""
    return "\n\n".join(pages) + "\n"


_LIST_ITEM = re.compile(r"^(?:- |\d+\. )")


def _md_link(text, href):
    text = text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    cleaned = []
    for ch in href.strip():
        if ch.isspace():
            cleaned.append("%20")
        elif ch == "<":
            cleaned.append("%3C")
        elif ch == ">":
            cleaned.append("%3E")
        elif ch == "\\":
            cleaned.append("%5C")
        else:
            cleaned.append(ch)
    href = "".join(cleaned)
    if not href:
        return text
    if "(" in href or ")" in href:
        return f"[{text}](<{href}>)"
    return f"[{text}]({href})"


def html_to_markdown(text):
    parser = _HTMLToMarkdown()
    try:
        parser.feed(text)
        parser.close()
    except ConvertError:
        raise
    except Exception as exc:
        raise ConvertError(f"could not read HTML: {exc}") from exc
    return parser.render()


class _HTMLToMarkdown(HTMLParser):
    SKIP = {"script", "style", "head", "title"}
    WRAP = {
        "div",
        "section",
        "article",
        "main",
        "header",
        "footer",
        "nav",
        "body",
        "html",
        "table",
        "tbody",
        "thead",
        "tr",
        "td",
        "th",
        "form",
        "figure",
        "figcaption",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.buf = []
        self.capture = None
        self.href = ""
        self.blocks = []
        self.lists = []
        self.pending_marker = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr = {key.lower(): (value or "") for key, value in attrs}
        if tag in self.SKIP:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "ul", "ol"} or tag in self.WRAP:
            self._flush_text()
        if tag in {"ul", "ol"}:
            self.lists.append([tag, 0])
        elif tag == "li":
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.pending_marker = f"{self.lists[-1][1]}. "
            else:
                self.pending_marker = "- "
        elif tag == "br":
            self._append("\n")
        elif tag == "a":
            self.capture = []
            self.href = attr.get("href", "").strip()
        elif tag in {"strong", "b"}:
            self._append("**")
        elif tag in {"em", "i"}:
            self._append("*")
        elif tag == "code":
            self._append("`")
        elif tag == "img":
            alt = attr.get("alt", "").strip()
            if alt:
                self._append(alt)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "a" and self.capture is not None:
            self._close_anchor(force=True)
            return
        if tag in {"strong", "b"}:
            self._append("**")
            return
        if tag in {"em", "i"}:
            self._append("*")
            return
        if tag == "code":
            self._append("`")
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._stop_anchor()
            text = self._consume()
            if text:
                self.blocks.append("#" * int(tag[1]) + " " + text)
            return
        if tag == "p":
            self._stop_anchor()
            text = self._consume()
            if text:
                self.blocks.append(text)
            return
        if tag == "li":
            self._stop_anchor()
            text = self._consume()
            self.pending_marker = None
            if text:
                self.blocks.append(text)
            return
        if tag in {"ul", "ol"}:
            self._stop_anchor()
            self._flush_text()
            self.pending_marker = None
            if self.lists:
                self.lists.pop()
            return
        if tag in self.WRAP:
            self._stop_anchor()
            self._flush_text()

    def handle_data(self, data):
        if self.skip_depth:
            return
        self._append(data)

    def close(self):
        super().close()
        self._flush_text()

    def render(self):
        self._flush_text()
        items = [block for block in self.blocks if block.strip()]
        if not items:
            return ""
        out = []
        for index, block in enumerate(items):
            if index:
                prev = items[index - 1]
                if _LIST_ITEM.match(prev) and _LIST_ITEM.match(block):
                    out.append("\n")
                else:
                    out.append("\n\n")
            out.append(block)
        out.append("\n")
        return "".join(out)

    def _append(self, text):
        if not text or self.skip_depth:
            return
        if self.capture is not None:
            self.capture.append(text)
        else:
            self.buf.append(text)

    def _stop_anchor(self):
        if self.capture is None:
            return
        if "".join(self.capture).strip():
            self._close_anchor(force=True)
        else:
            self.capture = None
            self.href = ""

    def _close_anchor(self, force):
        if self.capture is None:
            return
        raw = "".join(self.capture)
        if not force and not raw.strip():
            return
        text = re.sub(r"\s+", " ", raw).strip()
        href = self.href
        self.capture = None
        self.href = ""
        self._append(_md_link(text, href))

    def _consume(self):
        self._close_anchor(force=False)
        raw = "".join(self.buf)
        self.buf = []
        text = _normalize(raw)
        if text and self.pending_marker:
            text = self.pending_marker + text
            self.pending_marker = None
        return text

    def _flush_text(self):
        text = self._consume()
        if text:
            self.blocks.append(text)


def _normalize(raw):
    raw = raw.replace("\xa0", " ").replace("\r", "")
    lines = []
    for line in raw.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)
