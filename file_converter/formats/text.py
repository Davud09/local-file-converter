import shutil
import re
from pathlib import Path

from ..errors import FileConverterError
from ..models import ConversionOptions
from ..registry import register


def _read_text(source: Path) -> str:
    try:
        return source.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise FileConverterError(
            f"{source} is not valid UTF-8 text."
        ) from error


def _write_text(destination: Path, content: str) -> None:
    destination.write_text(content, encoding="utf-8", newline="")


def text_to_markdown(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    shutil.copyfile(source, destination)


def markdown_to_text(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    content = _read_text(source)
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    content = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", content)
    content = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", content)
    content = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", content)
    content = re.sub(r"(?m)^\s*>\s?", "", content)
    content = re.sub(r"(?m)^\s*[-*+]\s+", "- ", content)
    content = re.sub(r"(?<!\\)[*_~`]", "", content)
    _write_text(destination, content)


def register_routes() -> None:
    register(".txt", ".md", text_to_markdown, "Copy UTF-8 text into a Markdown file")
    register(".md", ".txt", markdown_to_text, "Remove common Markdown styling")
