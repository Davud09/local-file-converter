import csv
import html
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

import orjson

from ..errors import FileConverterError
from ..models import ConversionOptions
from ..registry import register

JSON_STREAM_BATCH_SIZE = 512


def _read_utf8(source: Path) -> str:
    try:
        return source.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise FileConverterError(f"{source} is not valid UTF-8 text.") from error


def csv_to_json(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    temporary_path: Path | None = None
    try:
        with source.open(
            encoding="utf-8", newline="", buffering=1024 * 1024
        ) as input_file:
            reader = csv.reader(input_file, strict=True)
            headers = next(reader, None)
            if not headers:
                raise FileConverterError("CSV input must contain a header row.")
            if len(headers) != len(set(headers)):
                raise FileConverterError("CSV input contains duplicate column names.")

            # Stream rows to a sibling temporary file to bound memory and avoid
            # leaving a partial destination if the input contains malformed CSV.
            with tempfile.NamedTemporaryFile(
                mode="wb",
                buffering=1024 * 1024,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as output_file:
                temporary_path = Path(output_file.name)
                output_file.write(b"[")
                row_count = 0
                batch: list[dict[str | None, str | None]] = []
                for values in reader:
                    if not values:
                        continue
                    if len(values) > len(headers):
                        raise FileConverterError(
                            "CSV rows must not contain more values than the header."
                        )
                    row = dict(zip(headers, values))
                    if len(values) < len(headers):
                        row.update(dict.fromkeys(headers[len(values) :]))
                    batch.append(row)
                    if len(batch) == JSON_STREAM_BATCH_SIZE:
                        _write_json_batch(
                            output_file,
                            batch,
                            is_first=row_count == 0,
                            compact=options.compact_json,
                        )
                        row_count += len(batch)
                        batch.clear()
                if batch:
                    _write_json_batch(
                        output_file,
                        batch,
                        is_first=row_count == 0,
                        compact=options.compact_json,
                    )
                    row_count += len(batch)
                output_file.write(
                    b"]\n"
                    if options.compact_json or not row_count
                    else b"\n]\n"
                )
        assert temporary_path is not None
        os.replace(temporary_path, destination)
    except UnicodeDecodeError as error:
        raise FileConverterError(f"{source} is not valid UTF-8 text.") from error
    except csv.Error as error:
        raise FileConverterError(f"Could not read CSV file: {error}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_json_batch(
    output_file: BinaryIO,
    rows: list[dict[str | None, str | None]],
    *,
    is_first: bool,
    compact: bool,
) -> None:
    option = orjson.OPT_INDENT_2 if not compact else 0
    serialized = orjson.dumps(rows, option=option)
    if compact:
        output_file.write((b"" if is_first else b",") + serialized[1:-1])
    else:
        # Drop each batch's array brackets so rows join into one JSON array.
        output_file.write((b"\n" if is_first else b",\n") + serialized[2:-2])


def _csv_value(value: object) -> object:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def json_to_csv(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    try:
        value = orjson.loads(source.read_bytes())
    except orjson.JSONDecodeError:
        try:
            value = json.loads(_read_utf8(source))
        except json.JSONDecodeError as json_error:
            raise FileConverterError(
                f"Invalid JSON in {source} at line {json_error.lineno}, "
                f"column {json_error.colno}: {json_error.msg}"
            ) from json_error

    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise FileConverterError("JSON to CSV requires a list of objects.")
    if not value:
        destination.write_text("", encoding="utf-8", newline="")
        return

    headers = list(value[0])
    header_tuple = tuple(headers)
    header_set = set(headers)
    if any(not isinstance(header, str) for header in headers):
        raise FileConverterError("JSON object keys must be strings for CSV output.")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            buffering=1024 * 1024,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as output_file:
            temporary_path = Path(output_file.name)
            writer = csv.writer(output_file)
            writer.writerow(headers)

            def rows_for_csv() -> Iterator[Iterator[object]]:
                for row in value:
                    if tuple(row) != header_tuple and row.keys() != header_set:
                        raise FileConverterError(
                            "Every JSON row must have the same object keys."
                        )
                    yield (_csv_value(row[key]) for key in headers)

            writer.writerows(rows_for_csv())
        assert temporary_path is not None
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _delimited_to_delimited(
    source: Path, destination: Path, *, input_delimiter: str, output_delimiter: str
) -> None:
    try:
        with source.open(
            encoding="utf-8", newline="", buffering=1024 * 1024
        ) as input_file:
            with destination.open(
                "w", encoding="utf-8", newline="", buffering=1024 * 1024
            ) as output_file:
                reader = csv.reader(input_file, delimiter=input_delimiter, strict=True)
                writer = csv.writer(output_file, delimiter=output_delimiter)
                writer.writerows(reader)
    except UnicodeDecodeError as error:
        raise FileConverterError(f"{source} is not valid UTF-8 text.") from error
    except csv.Error as error:
        raise FileConverterError(f"Could not convert delimited text: {error}") from error


def tsv_to_csv(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    _delimited_to_delimited(
        source, destination, input_delimiter="\t", output_delimiter=","
    )


def csv_to_tsv(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    _delimited_to_delimited(
        source, destination, input_delimiter=",", output_delimiter="\t"
    )


def _xml_value(element: ET.Element) -> object:
    value: dict[str, object] = {
        f"@{name}": attribute for name, attribute in element.attrib.items()
    }
    children = list(element)
    if children:
        for child in children:
            child_value = _xml_value(child)
            if child.tag in value:
                previous = value[child.tag]
                if isinstance(previous, list):
                    previous.append(child_value)
                else:
                    value[child.tag] = [previous, child_value]
            else:
                value[child.tag] = child_value
        text = (element.text or "").strip()
        if text:
            value["#text"] = text
        return value

    text = (element.text or "").strip()
    if not value:
        return text
    if text:
        value["#text"] = text
    return value


def xml_to_json(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    try:
        root = ET.fromstring(_read_utf8(source))
    except ET.ParseError as error:
        raise FileConverterError(f"Invalid XML in {source}: {error}") from error

    # Keep the document root as a key so its name is not lost in JSON.
    value = {root.tag: _xml_value(root)}
    serialized = orjson.dumps(
        value,
        option=0 if options.compact_json else orjson.OPT_INDENT_2,
    )
    with destination.open("wb", buffering=1024 * 1024) as output_file:
        output_file.write(serialized)
        output_file.write(b"\n")


class _PlainTextParser(HTMLParser):
    _block_tags = {
        "address",
        "article",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "ol",
        "p",
        "section",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style"}:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in self._block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag in self._block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def html_to_text(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    parser = _PlainTextParser()
    try:
        parser.feed(_read_utf8(source))
        parser.close()
    except (ValueError, AssertionError) as error:
        raise FileConverterError(f"Could not parse HTML in {source}: {error}") from error

    content = "".join(parser.parts)
    lines = [line.strip() for line in content.splitlines()]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    destination.write_text(cleaned + "\n", encoding="utf-8", newline="")


def text_to_html(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    temporary_path: Path | None = None
    try:
        with source.open(
            encoding="utf-8", buffering=1024 * 1024
        ) as input_file, tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            buffering=1024 * 1024,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as output_file:
            temporary_path = Path(output_file.name)
            output_file.write(
                "<!doctype html>\n<html lang=\"en\">\n<head>\n"
                '<meta charset="utf-8">\n<meta name="viewport" '
                'content="width=device-width, initial-scale=1">\n'
                "<title>Converted text</title>\n</head>\n<body>\n<pre>"
            )
            while chunk := input_file.read(1024 * 1024):
                output_file.write(html.escape(chunk))
            output_file.write("</pre>\n</body>\n</html>\n")
        assert temporary_path is not None
        os.replace(temporary_path, destination)
    except UnicodeDecodeError as error:
        raise FileConverterError(f"{source} is not valid UTF-8 text.") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", escaped)

    def make_link(match: re.Match[str]) -> str:
        label, target = match.groups()
        target = html.unescape(target)
        scheme = urlsplit(target).scheme.lower()
        if scheme not in {"", "http", "https", "mailto"} or target.startswith("//"):
            return label
        return f'<a href="{html.escape(target, quote=True)}">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", make_link, escaped)


def markdown_to_html(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    lines = _read_utf8(source).splitlines()
    output = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Converted Markdown</title>",
        "</head>",
        "<body>",
    ]
    paragraph: list[str] = []
    list_items: list[str] = []
    code_lines: list[str] | None = None

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            output.append("<ul>")
            output.extend(f"<li>{_inline_markdown(item)}</li>" for item in list_items)
            output.append("</ul>")
            list_items.clear()

    # Render a deliberately small, safe Markdown subset without another dependency.
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            if code_lines is None:
                code_lines = []
            else:
                output.append(
                    "<pre><code>"
                    + html.escape("\n".join(code_lines))
                    + "</code></pre>"
                )
                code_lines = None
            continue
        if code_lines is not None:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            output.append(
                f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>"
            )
        elif re.match(r"^[-*+]\s+", stripped):
            flush_paragraph()
            list_items.append(re.sub(r"^[-*+]\s+", "", stripped))
        else:
            flush_list()
            paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    if code_lines is not None:
        output.append(
            "<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>"
        )
    output.extend(["</body>", "</html>", ""])
    destination.write_text("\n".join(output), encoding="utf-8", newline="")


def register_routes() -> None:
    register(".csv", ".json", csv_to_json, "Convert CSV rows to a JSON array")
    register(".json", ".csv", json_to_csv, "Convert a JSON array of objects to CSV")
    register(".tsv", ".csv", tsv_to_csv, "Convert tab-separated data to CSV")
    register(".csv", ".tsv", csv_to_tsv, "Convert CSV data to tab-separated text")
    register(".xml", ".json", xml_to_json, "Convert XML structure to JSON")
    register(".html", ".txt", html_to_text, "Extract readable text from HTML")
    register(".txt", ".html", text_to_html, "Wrap UTF-8 text safely in an HTML page")
    register(".md", ".html", markdown_to_html, "Render common Markdown into HTML")
