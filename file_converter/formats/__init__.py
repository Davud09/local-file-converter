from . import archive, audio, data, documents, image, json_format, text

for format_module in (text, json_format, data, audio, image, documents):
    format_module.register_routes()

__all__ = ["archive"]
