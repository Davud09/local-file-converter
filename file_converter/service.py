from pathlib import Path

from .errors import FileConverterError
from .formats import archive as archive_operations
from .models import ConversionOptions
from .registry import ConversionRoute, get_route, list_routes


def available_routes() -> tuple[ConversionRoute, ...]:
    return list_routes()


def convert_file(
    source: Path, destination: Path, *, compact_json: bool = False
) -> None:
    source = source.expanduser()
    destination = destination.expanduser()

    if not source.exists() or not source.is_file():
        raise FileConverterError(f"Input file does not exist: {source}")
    if not destination.parent.exists():
        raise FileConverterError(
            f"Output folder does not exist: {destination.parent}"
        )
    if source.resolve() == destination.resolve():
        raise FileConverterError("Input and output files must be different.")

    route = get_route(source.suffix, destination.suffix)
    if route is None:
        raise FileConverterError(
            f"No conversion route for {source.suffix or '(no extension)'} -> "
            f"{destination.suffix or '(no extension)'}. Run `python -m "
            "file_converter list` to see supported routes."
        )
    if compact_json and route.target_extension != ".json":
        raise FileConverterError(
            "--compact-json is only valid when the output format is JSON."
        )

    route.converter(
        source,
        destination,
        ConversionOptions(compact_json=compact_json),
    )


def create_zip(archive_path: Path, inputs: list[Path]) -> None:
    archive_path = archive_path.expanduser()
    if archive_path.suffix.lower() != ".zip":
        raise FileConverterError("ZIP output path must use the .zip extension.")
    if not archive_path.parent.exists():
        raise FileConverterError(
            f"Output folder does not exist: {archive_path.parent}"
        )
    expanded_inputs = [item.expanduser() for item in inputs]
    archive_resolved = archive_path.resolve()
    for item in expanded_inputs:
        item_resolved = item.resolve()
        if item_resolved == archive_resolved or (
            item.is_dir() and archive_resolved.is_relative_to(item_resolved)
        ):
            raise FileConverterError(
                "The output ZIP must not be one of its inputs or inside an input folder."
            )
    archive_operations.create_zip(archive_path, expanded_inputs)


def extract_zip(archive_path: Path, destination: Path) -> None:
    archive_path = archive_path.expanduser()
    destination = destination.expanduser()
    if not archive_path.is_file():
        raise FileConverterError(f"ZIP archive does not exist: {archive_path}")
    if archive_path.suffix.lower() != ".zip":
        raise FileConverterError("Input archive must use the .zip extension.")
    archive_operations.extract_zip(archive_path, destination)
