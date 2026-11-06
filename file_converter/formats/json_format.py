import json
from pathlib import Path

import orjson

from ..errors import FileConverterError
from ..models import ConversionOptions
from ..registry import register


def format_json(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    raw_data = source.read_bytes()
    try:
        value = orjson.loads(raw_data)
    except orjson.JSONDecodeError as error:
        try:
            value = json.loads(raw_data.decode("utf-8"))
        except UnicodeDecodeError as decode_error:
            raise FileConverterError(
                f"{source} is not valid UTF-8 text."
            ) from decode_error
        except json.JSONDecodeError as json_error:
            raise FileConverterError(
                f"Invalid JSON in {source} at line {json_error.lineno}, "
                f"column {json_error.colno}: {json_error.msg}"
            ) from json_error

        # Retain stdlib compatibility for values such as NaN accepted by json.
        if options.compact_json:
            formatted = json.dumps(
                value, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        else:
            formatted = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    else:
        dump_options = 0 if options.compact_json else orjson.OPT_INDENT_2
        try:
            formatted = orjson.dumps(value, option=dump_options)
        except orjson.JSONEncodeError:
            # The stdlib supports arbitrary-size integers that orjson rejects.
            if options.compact_json:
                formatted = json.dumps(
                    value, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
            else:
                formatted = json.dumps(
                    value, ensure_ascii=False, indent=2
                ).encode("utf-8")

    with destination.open("wb", buffering=1024 * 1024) as output_file:
        output_file.write(formatted)
        output_file.write(b"\n")


def register_routes() -> None:
    register(".json", ".json", format_json, "Pretty-print or compact JSON")
