import argparse
import sys
from pathlib import Path

from waraq.convert import ConvertError, convert_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="waraq",
        description="Convert a file to Markdown.",
    )
    parser.add_argument("file", help="input file")
    parser.add_argument("-o", "--output", help="write here instead of stdout")
    args = parser.parse_args(argv)
    try:
        text = convert_path(args.file)
    except ConvertError as exc:
        print(f"waraq: {exc}", file=sys.stderr)
        return 1
    if args.output:
        try:
            Path(args.output).write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            print(f"waraq: {exc}", file=sys.stderr)
            return 1
        return 0
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        try:
            out.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    try:
        out.write(text)
    except BrokenPipeError:
        return 0
    except OSError as exc:
        print(f"waraq: {exc}", file=sys.stderr)
        return 1
    return 0
