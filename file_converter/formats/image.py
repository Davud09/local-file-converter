from pathlib import Path

from ..errors import FileConverterError
from ..models import ConversionOptions
from ..registry import register


def jpeg_to_png(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    try:
        from PIL import Image
    except ImportError as error:
        raise FileConverterError(
            "JPEG to PNG conversion requires Pillow. Install dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from error

    try:
        with Image.open(source) as image:
            image.save(destination, format="PNG", compress_level=1)
    except (OSError, ValueError) as error:
        raise FileConverterError(f"Could not convert {source} to PNG: {error}") from error


def register_routes() -> None:
    register(".jpeg", ".png", jpeg_to_png, "Convert JPEG images to PNG using Pillow")
    register(".jpg", ".png", jpeg_to_png, "Convert JPEG images to PNG using Pillow")
