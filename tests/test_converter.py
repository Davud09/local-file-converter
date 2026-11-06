import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageChops

from file_converter.errors import FileConverterError
from file_converter.formats.archive import extract_zip
from file_converter.gui import default_output_path
from file_converter.service import (
    available_routes,
    convert_file,
    create_zip,
    extract_zip as extract_zip_file,
)


class ConverterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_text_to_markdown_preserves_utf8_content(self) -> None:
        source = self.root / "note.txt"
        destination = self.root / "note.md"
        source.write_text("Hello, world!\n", encoding="utf-8")

        convert_file(source, destination)

        self.assertEqual(destination.read_text(encoding="utf-8"), "Hello, world!\n")

    def test_markdown_to_text_removes_common_formatting(self) -> None:
        source = self.root / "note.md"
        destination = self.root / "note.txt"
        source.write_text("# **Hello** [world](https://example.com)\n", encoding="utf-8")

        convert_file(source, destination)

        self.assertEqual(destination.read_text(encoding="utf-8"), "Hello world\n")

    def test_json_is_pretty_printed_or_compacted(self) -> None:
        source = self.root / "data.json"
        pretty = self.root / "pretty.json"
        compact = self.root / "compact.json"
        source.write_text('{"name":"Ada","active":true}', encoding="utf-8")

        convert_file(source, pretty)
        convert_file(source, compact, compact_json=True)

        self.assertEqual(json.loads(pretty.read_text(encoding="utf-8")), {
            "name": "Ada",
            "active": True,
        })
        self.assertEqual(
            compact.read_text(encoding="utf-8"), '{"name":"Ada","active":true}\n'
        )

    def test_json_formatter_preserves_large_integers_and_legacy_nan(self) -> None:
        source = self.root / "special.json"
        destination = self.root / "formatted.json"
        source.write_text('{"large":123456789012345678901234567890,"value":NaN}', encoding="utf-8")

        convert_file(source, destination)

        output = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(output["large"], 123456789012345678901234567890)
        self.assertTrue(output["value"] != output["value"])

    def test_routes_include_the_confirmed_file_conversions(self) -> None:
        routes = {
            (route.source_extension, route.target_extension)
            for route in available_routes()
        }

        self.assertEqual(
            routes,
            {
                (".txt", ".md"),
                (".md", ".txt"),
                (".json", ".json"),
                (".csv", ".json"),
                (".json", ".csv"),
                (".tsv", ".csv"),
                (".csv", ".tsv"),
                (".xml", ".json"),
                (".html", ".txt"),
                (".txt", ".html"),
                (".md", ".html"),
                (".mp3", ".wav"),
                (".jpeg", ".png"),
                (".jpg", ".png"),
                (".docx", ".pdf"),
                (".pdf", ".docx"),
                (".epub", ".pdf"),
            },
        )

    def test_csv_and_json_convert_in_both_directions(self) -> None:
        csv_source = self.root / "people.csv"
        json_output = self.root / "people.json"
        csv_output = self.root / "roundtrip.csv"
        csv_source.write_text(
            'name,city\n"Ada Lovelace","London, UK"\n',
            encoding="utf-8",
        )

        convert_file(csv_source, json_output)
        convert_file(json_output, csv_output)

        self.assertEqual(
            json.loads(json_output.read_text(encoding="utf-8")),
            [{"name": "Ada Lovelace", "city": "London, UK"}],
        )
        with csv_output.open(encoding="utf-8", newline="") as output_file:
            self.assertEqual(
                output_file.read(),
                'name,city\r\nAda Lovelace,"London, UK"\r\n',
            )

    def test_csv_to_json_can_write_compact_output(self) -> None:
        source = self.root / "people.csv"
        destination = self.root / "people.json"
        source.write_text("name,count\nAda,3\n", encoding="utf-8")

        convert_file(source, destination, compact_json=True)

        output = destination.read_text(encoding="utf-8")
        self.assertEqual(output, '[{"name":"Ada","count":"3"}]\n')
        self.assertEqual(json.loads(output), [{"name": "Ada", "count": "3"}])

    def test_csv_to_json_preserves_blank_and_short_row_behavior(self) -> None:
        source = self.root / "sparse.csv"
        destination = self.root / "sparse.json"
        source.write_text(
            "name,city\nAda\n\nGrace,London\n",
            encoding="utf-8",
        )

        convert_file(source, destination)

        self.assertEqual(
            json.loads(destination.read_text(encoding="utf-8")),
            [
                {"name": "Ada", "city": None},
                {"name": "Grace", "city": "London"},
            ],
        )

    def test_compact_json_option_rejects_non_json_output(self) -> None:
        source = self.root / "note.txt"
        destination = self.root / "note.md"
        source.write_text("hello", encoding="utf-8")

        with self.assertRaisesRegex(FileConverterError, "output format is JSON"):
            convert_file(source, destination, compact_json=True)

    def test_csv_to_json_failure_keeps_existing_output_intact(self) -> None:
        source = self.root / "malformed.csv"
        destination = self.root / "existing.json"
        source.write_text('name,value\n"unfinished,1\n', encoding="utf-8")
        destination.write_text("keep this output", encoding="utf-8")

        with self.assertRaises(FileConverterError):
            convert_file(source, destination)

        self.assertEqual(
            destination.read_text(encoding="utf-8"), "keep this output"
        )
        self.assertEqual(list(self.root.glob(".existing.json.*.tmp")), [])

    def test_csv_to_json_formats_rows_across_streaming_batches(self) -> None:
        source = self.root / "large.csv"
        destination = self.root / "large.json"
        with source.open("w", encoding="utf-8", newline="") as output_file:
            output_file.write("id,label\n")
            for index in range(520):
                output_file.write(f"{index},row-{index}\n")

        convert_file(source, destination)

        rows = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 520)
        self.assertEqual(rows[0], {"id": "0", "label": "row-0"})
        self.assertEqual(rows[-1], {"id": "519", "label": "row-519"})
        expected = json.dumps(
            [{"id": str(index), "label": f"row-{index}"} for index in range(520)],
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        self.assertEqual(destination.read_text(encoding="utf-8"), expected)

    def test_compact_csv_to_json_preserves_rows_across_batches(self) -> None:
        source = self.root / "large.csv"
        destination = self.root / "large.compact.json"
        with source.open("w", encoding="utf-8", newline="") as output_file:
            output_file.write("id,label\n")
            for index in range(520):
                output_file.write(f"{index},row-{index}\n")

        convert_file(source, destination, compact_json=True)

        output = destination.read_text(encoding="utf-8")
        self.assertNotIn("\n ", output)
        rows = json.loads(output)
        self.assertEqual(len(rows), 520)
        self.assertEqual(rows[0], {"id": "0", "label": "row-0"})
        self.assertEqual(rows[-1], {"id": "519", "label": "row-519"})
        expected = json.dumps(
            [{"id": str(index), "label": f"row-{index}"} for index in range(520)],
            ensure_ascii=False,
            separators=(",", ":"),
        ) + "\n"
        self.assertEqual(output, expected)

    def test_json_to_csv_rejects_rows_with_different_keys(self) -> None:
        source = self.root / "inconsistent.json"
        destination = self.root / "output.csv"
        source.write_text('[{"a":1},{"b":2}]', encoding="utf-8")

        with self.assertRaisesRegex(FileConverterError, "same object keys"):
            convert_file(source, destination)

        self.assertFalse(destination.exists())

    def test_csv_and_tsv_conversion_preserves_quoted_delimiters(self) -> None:
        source = self.root / "table.csv"
        tsv_output = self.root / "table.tsv"
        csv_output = self.root / "roundtrip.csv"
        source.write_text(
            'name,description\nAda,"writes, and computes"\n', encoding="utf-8"
        )

        convert_file(source, tsv_output)
        convert_file(tsv_output, csv_output)

        with tsv_output.open(encoding="utf-8", newline="") as output_file:
            self.assertEqual(
                output_file.read(),
                'name\tdescription\r\nAda\twrites, and computes\r\n',
            )
        with csv_output.open(encoding="utf-8", newline="") as output_file:
            self.assertEqual(
                output_file.read(),
                'name,description\r\nAda,"writes, and computes"\r\n',
            )

    def test_xml_conversion_keeps_attributes_and_repeated_elements(self) -> None:
        source = self.root / "catalog.xml"
        destination = self.root / "catalog.json"
        source.write_text(
            '<catalog version="1"><item>A</item><item>B</item></catalog>',
            encoding="utf-8",
        )

        convert_file(source, destination)

        self.assertEqual(
            json.loads(destination.read_text(encoding="utf-8")),
            {"catalog": {"@version": "1", "item": ["A", "B"]}},
        )

    def test_xml_to_json_honors_compact_json_option(self) -> None:
        source = self.root / "simple.xml"
        destination = self.root / "simple.json"
        source.write_text("<root><item>value</item></root>", encoding="utf-8")

        convert_file(source, destination, compact_json=True)

        output = destination.read_text(encoding="utf-8")
        self.assertEqual(output, '{"root":{"item":"value"}}\n')

    def test_html_to_text_ignores_scripts_and_decodes_entities(self) -> None:
        source = self.root / "page.html"
        destination = self.root / "page.txt"
        source.write_text(
            "<h1>Hello &amp; welcome</h1><script>do not show</script><p>Text</p>",
            encoding="utf-8",
        )

        convert_file(source, destination)

        self.assertEqual(
            destination.read_text(encoding="utf-8"), "Hello & welcome\n\nText\n"
        )

    def test_text_to_html_escapes_markup(self) -> None:
        source = self.root / "note.txt"
        destination = self.root / "note.html"
        source.write_text("<script>not markup</script>", encoding="utf-8")

        convert_file(source, destination)

        output = destination.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", output)
        self.assertNotIn("<script>", output)

    def test_markdown_to_html_renders_common_blocks_and_safe_links(self) -> None:
        source = self.root / "note.md"
        destination = self.root / "note.html"
        source.write_text(
            "# Hello\n\n**bold** and [site](https://example.com)\n\n"
            "[unsafe](javascript:alert(1))",
            encoding="utf-8",
        )

        convert_file(source, destination)

        output = destination.read_text(encoding="utf-8")
        self.assertIn("<h1>Hello</h1>", output)
        self.assertIn("<strong>bold</strong>", output)
        self.assertIn('href="https://example.com"', output)
        self.assertNotIn('href="javascript:', output)

    def test_json_default_output_does_not_overwrite_source(self) -> None:
        route = next(
            route
            for route in available_routes()
            if (route.source_extension, route.target_extension) == (".json", ".json")
        )
        source = Path("data.json")

        self.assertEqual(
            default_output_path(source, route), Path("data.formatted.json")
        )
        self.assertEqual(
            default_output_path(source, route, compact_json=True),
            Path("data.min.json"),
        )

    def test_zip_extraction_rejects_parent_directory_traversal(self) -> None:
        archive_path = self.root / "malicious.zip"
        output_directory = self.root / "out"
        escaped_path = self.root / "outside.txt"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("../outside.txt", "unexpected")

        with self.assertRaises(FileConverterError):
            extract_zip(archive_path, output_directory)

        self.assertFalse(escaped_path.exists())

    def test_zip_can_be_created_and_extracted(self) -> None:
        source = self.root / "documents"
        source.mkdir()
        (source / "note.txt").write_text("archive me", encoding="utf-8")
        archive_path = self.root / "bundle.zip"
        output_directory = self.root / "extracted"

        create_zip(archive_path, [source])
        extract_zip_file(archive_path, output_directory)

        self.assertEqual(
            (output_directory / "documents" / "note.txt").read_text(
                encoding="utf-8"
            ),
            "archive me",
        )

    def test_zip_uses_fast_compression_and_stores_precompressed_files(self) -> None:
        text = self.root / "notes.txt"
        image = self.root / "photo.jpg"
        archive_path = self.root / "bundle.zip"
        text.write_text("a short note", encoding="utf-8")
        image.write_bytes(b"already-compressed")

        create_zip(archive_path, [text, image])

        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(
                archive.getinfo("notes.txt").compress_type, zipfile.ZIP_DEFLATED
            )
            self.assertEqual(
                archive.getinfo("photo.jpg").compress_type, zipfile.ZIP_STORED
            )

    def test_jpeg_to_png_preserves_pixels(self) -> None:
        source = self.root / "photo.jpeg"
        destination = self.root / "photo.png"
        original = Image.new("RGB", (4, 4), (32, 96, 160))
        original.save(source, format="JPEG", quality=100, subsampling=0)

        convert_file(source, destination)

        with Image.open(source) as jpeg, Image.open(destination) as png:
            self.assertEqual(png.format, "PNG")
            self.assertIsNone(ImageChops.difference(jpeg, png).getbbox())


if __name__ == "__main__":
    unittest.main()
