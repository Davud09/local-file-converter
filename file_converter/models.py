from dataclasses import dataclass


@dataclass(frozen=True)
class ConversionOptions:
    compact_json: bool = False
