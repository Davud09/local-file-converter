import shutil
import subprocess
import tempfile
from pathlib import Path

from ..errors import FileConverterError
from ..models import ConversionOptions
from ..registry import register


def _convert_with_libreoffice(
    source: Path, destination: Path, output_format: str
) -> None:
    soffice = shutil.which("soffice")
    if soffice is None:
        raise FileConverterError(
            "DOCX/PDF conversion requires LibreOffice. Install it and add `soffice` "
            "to PATH."
        )

    with tempfile.TemporaryDirectory(prefix="file-converter-") as temporary_directory:
        result = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                output_format,
                "--outdir",
                temporary_directory,
                str(source),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        generated = Path(temporary_directory) / f"{source.stem}.{output_format}"
        if result.returncode or not generated.is_file():
            detail = result.stderr.strip() or result.stdout.strip()
            message = detail or "LibreOffice did not produce an output file."
            raise FileConverterError(f"LibreOffice conversion failed: {message}")
        shutil.move(str(generated), str(destination))


def docx_to_pdf(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    _convert_with_libreoffice(source, destination, "pdf")


def pdf_to_docx(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    _convert_with_libreoffice(source, destination, "docx")


def epub_to_pdf(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    ebook_convert = shutil.which("ebook-convert")
    if ebook_convert is None:
        raise FileConverterError(
            "EPUB to PDF conversion requires Calibre. Install it and add "
            "`ebook-convert` to PATH."
        )

    result = subprocess.run(
        [ebook_convert, str(source), str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or not destination.is_file():
        detail = result.stderr.strip() or result.stdout.strip()
        message = detail or "Calibre did not produce an output file."
        raise FileConverterError(f"Calibre conversion failed: {message}")


def register_routes() -> None:
    register(".docx", ".pdf", docx_to_pdf, "Convert DOCX to PDF using LibreOffice")
    register(".pdf", ".docx", pdf_to_docx, "Convert PDF to DOCX using LibreOffice")
    register(".epub", ".pdf", epub_to_pdf, "Convert EPUB to PDF using Calibre")
