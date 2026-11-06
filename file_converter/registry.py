from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .models import ConversionOptions

Converter = Callable[[Path, Path, ConversionOptions], None]


@dataclass(frozen=True)
class ConversionRoute:
    source_extension: str
    target_extension: str
    converter: Converter
    description: str


_routes: dict[tuple[str, str], ConversionRoute] = {}


def register(
    source_extension: str,
    target_extension: str,
    converter: Converter,
    description: str,
) -> None:
    source_extension = source_extension.lower()
    target_extension = target_extension.lower()
    if not source_extension.startswith(".") or not target_extension.startswith("."):
        raise ValueError("Format extensions must start with a dot.")

    key = (source_extension, target_extension)
    if key in _routes:
        raise ValueError(f"Conversion route already registered: {key[0]} -> {key[1]}")
    _routes[key] = ConversionRoute(
        source_extension, target_extension, converter, description
    )


def get_route(source_extension: str, target_extension: str) -> ConversionRoute | None:
    return _routes.get((source_extension.lower(), target_extension.lower()))


def list_routes() -> tuple[ConversionRoute, ...]:
    return tuple(_routes[key] for key in sorted(_routes))
