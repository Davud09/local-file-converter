import argparse
import sys
from pathlib import Path

from .errors import FileConverterError
from .registry import ConversionRoute
from .service import available_routes, convert_file, create_zip, extract_zip


def _add_convert_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", type=Path, help="Input file")
    parser.add_argument("destination", type=Path, help="Output file")
    parser.add_argument(
        "--compact-json",
        action="store_true",
        help="Write compact JSON output (for example CSV -> JSON)",
    )


def _format_route(route: ConversionRoute) -> str:
    return (
        f"{route.source_extension} -> {route.target_extension}: "
        f"{route.description}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file-converter",
        description="Convert supported files using registered conversion routes.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    convert_parser = commands.add_parser("convert", help="Convert one file")
    _add_convert_arguments(convert_parser)

    commands.add_parser("list", help="List supported file conversion routes")

    zip_create_parser = commands.add_parser(
        "zip-create", help="Create a ZIP archive from files or folders"
    )
    zip_create_parser.add_argument("archive", type=Path, help="Output .zip file")
    zip_create_parser.add_argument(
        "inputs", type=Path, nargs="+", help="Files or folders to add"
    )

    zip_extract_parser = commands.add_parser(
        "zip-extract", help="Safely extract a ZIP archive"
    )
    zip_extract_parser.add_argument("archive", type=Path, help="Input .zip file")
    zip_extract_parser.add_argument(
        "destination", type=Path, help="Folder to extract into"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "convert":
            convert_file(
                arguments.source,
                arguments.destination,
                compact_json=arguments.compact_json,
            )
            print(f"Converted {arguments.source} -> {arguments.destination}")
        elif arguments.command == "list":
            for route in available_routes():
                print(_format_route(route))
            print("ZIP: use `zip-create` and `zip-extract`.")
        elif arguments.command == "zip-create":
            create_zip(arguments.archive, arguments.inputs)
            print(f"Created {arguments.archive}")
        elif arguments.command == "zip-extract":
            extract_zip(arguments.archive, arguments.destination)
            print(f"Extracted {arguments.archive} -> {arguments.destination}")
    except (FileConverterError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0
