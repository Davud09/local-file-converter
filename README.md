# Fast Local File Converter

A local-first desktop and command-line tool for converting common file formats
on your computer. It focuses on fast conversions without sending files to a
conversion service. Format-specific modules and a central route registry make
it straightforward to add more routes without changing the app interface.

## Supported routes

| Input | Output | Notes |
|---|---|---|
| `.txt` | `.md` | Copies UTF-8 text |
| `.md` | `.txt` | Removes common Markdown styling; not a full Markdown renderer |
| `.md` | `.html` | Renders common Markdown blocks; raw HTML is escaped |
| `.txt` | `.html` | Creates a safe HTML page with text in a preformatted block |
| `.html` | `.txt` | Extracts readable text and ignores script/style contents |
| `.json` | `.json` | Pretty-prints by default; `--compact-json` minifies |
| `.csv` | `.json` | Streams rows in bounded batches to a JSON array; `--compact-json` reduces output size |
| `.json` | `.csv` | Requires an array of objects with the same keys |
| `.csv` | `.tsv` | Changes comma delimiters to tabs |
| `.tsv` | `.csv` | Changes tab delimiters to commas |
| `.xml` | `.json` | Preserves root, attributes, and repeated child elements |
| `.mp3` | `.wav` | Requires FFmpeg on `PATH` |
| `.jpeg`, `.jpg` | `.png` | Requires Pillow |
| `.docx` | `.pdf` | Requires LibreOffice (`soffice`) on `PATH` |
| `.pdf` | `.docx` | Requires LibreOffice; layout and formatting may change |
| `.epub` | `.pdf` | Requires Calibre (`ebook-convert`) on `PATH` |
| ZIP archive | Create/extract | Uses Python's standard library; extraction rejects unsafe paths |

These conversions are intentionally specific: arbitrary file formats cannot
all be converted meaningfully to one another.

CSV-to-JSON uses Python's fast CSV reader plus the Rust-backed `orjson` encoder,
buffered I/O, and 512-row serialization batches. It writes to a temporary file
and replaces the destination only after the conversion succeeds, so malformed
input does not leave a partial output.

## CSV-to-JSON speed benchmark

The table below compares the previous standard-library implementation
(`csv.DictReader` + `json.dumps`) with the optimized implementation
(`csv.reader` + `orjson`). It uses the same generated 1 GiB CSV, the same
machine, and equivalent pretty/compact JSON output. Timings are end-to-end file
conversion timings, including reading and writing the complete files.

| Output | Previous median | Optimized median | Speedup | Time saved | Output size |
|---|---:|---:|---:|---:|---:|
| Compact JSON | 18.99 s | 11.41 s | 1.66× | 39.9% | 1,224,736,762 bytes |
| Pretty JSON | 19.61 s | 11.41 s | 1.72× | 41.8% | 1,375,731,707 bytes |

Compact JSON is 150,994,945 bytes (11.0%) smaller than pretty JSON for this
input. Both implementations processed 1,073,741,824 input bytes and produced
the same respective output sizes.

### Measurement method

- Windows, Python 3.13.15, orjson 3.13.0.
- Synthetic 1 GiB CSV with two columns and 8,388,608 records. Rows are mostly
  128 bytes; the last row is shorter to make the input exactly 1 GiB.
- Three alternating runs per output mode using the same input; the table uses
  each implementation's median elapsed time. The files were read from the
  operating-system cache, so these are warm-cache results, not cold-disk
  benchmarks.
- Previous implementation: `csv.DictReader` and batched standard-library
  `json.dumps`. Optimized implementation: `csv.reader`, batched `orjson`, and
  1 MiB I/O buffers. Both retain atomic output replacement.
- Times are specific to this machine and generated data. CSV quoting,
  character encoding, storage speed, and output format can change results.

## Other conversion speed comparisons

These are end-to-end timings for additional representative workloads. Each
comparison uses the earlier implementation and the optimized implementation on
the same machine and input. Results are medians; files were warm in the
operating-system cache. Output equivalence was checked where applicable.

| Route | Workload | Previous | Optimized | Speedup | Time reduced | Output / tradeoff |
|---|---:|---:|---:|---:|---:|---|
| TXT → MD | 108 MiB | 0.227 s | 0.051 s | 4.44× | 77.5% | Byte-identical; direct file copy |
| JSON pretty-print | 11.6 MiB | 0.268 s | 0.096 s | 2.79× | 64.2% | Byte-identical |
| JSON → CSV | 11.6 MiB | 0.436 s | 0.417 s | 1.05× | 4.4% | CSV values match; small improvement |
| CSV → TSV | 22.6 MiB | 0.614 s | 0.597 s | 1.03× | 2.8% | Output identical; near-neutral |
| TXT → HTML | 112 MiB | 1.068 s | 0.907 s | 1.18× | 15.1% | Byte-identical; streams escaped text |
| ZIP creation | 30 MiB mixed files | 0.536 s | 0.058 s | 9.18× | 89.2% | 16.0 → 16.1 MiB; precompressed formats are stored without recompression |
| ZIP extraction | 64 MiB stored input | 0.068 s | 0.066 s | 1.03× | 2.9% | Near-neutral; larger copy buffer |
| JPEG → PNG | 2048 × 2048 pixels | 0.404 s | 0.257 s | 1.57× | 36.4% | Decoded pixels identical; 12.0 → 12.7 MiB with faster PNG compression |

The comparison is route-specific: some conversions are already dominated by
file I/O or a third-party codec, so a code change may offer little benefit.
ZIP creation trades a small increase in archive size for much less CPU work on
formats that are already compressed. JPEG-to-PNG trades a larger PNG file for
faster encoding without changing decoded pixels.

These measurements do **not** establish that every supported route is faster
or limited only by hardware. Markdown/HTML parsing, TSV-to-CSV, XML-to-JSON,
and several other supported routes do not have a before/after benchmark here.
MP3-to-WAV, DOCX/PDF, and EPUB/PDF were not benchmarked because FFmpeg,
LibreOffice, and Calibre were unavailable in the test environment. Their
performance depends on those external conversion engines and their settings.

### Benchmark ledger and interpretation

The tables above are the completed benchmark results. Additional runs and
experiments recorded during optimization are included here so their results are
not mistaken for the final table:

| Route / experiment | Earlier run | Later or final run | Interpretation |
|---|---:|---:|---|
| JSON → CSV, 11.6 MiB | 0.446 s → 0.473 s | 0.456 s → 0.468 s; later 0.436 s → 0.417 s | Early runs were slightly slower; the latest five-run median comparison is the 0.436 s → 0.417 s result in the table. The gain is small and run-dependent. |
| TXT → HTML, 112 MiB | 1.056 s → 0.900 s | Final implementation: 1.068 s → 0.907 s | Streaming was faster in both measurements; the table uses the final implementation's result. |
| Markdown → plain text regex experiment | Not adopted | Output differed on repeated content | Rejected for correctness; it is not part of the converter or a performance claim. |

JSON → CSV comparison timings varied between runs, so they should not be read as
a guaranteed speedup. Likewise, ZIP results depend on the input mix and on
whether files are already compressed.

The UI startup measurement was 9.75 ms median across five runs; this measures
window initialization, not conversion throughput. Earlier development also
measured a reduction in traced memory for streaming CSV conversion, but a
comparable numeric before/after memory result is not available in the retained
benchmark record, so no memory improvement is claimed here.

### Reproducing and comparing results

The benchmark figures are measurements of earlier and optimized implementations
on this machine, not universal performance guarantees. Except for the 1 GiB
CSV benchmark's documented three alternating runs, the retained results do
not consistently record run counts, exact hardware specifications, or every
input-generation detail. The 1 GiB data is synthetic and warm-cache; real
files, cold storage, CPU, filesystem, output format, and external converter
versions can change results substantially. A large file conversion also
includes parsing and encoding work, so it cannot be assumed to run only at the
speed of the SSD or RAM.

## Setup

Use Python 3.10 or newer. Install the Python dependencies:

- Pillow for JPEG-to-PNG conversion.
- orjson for accelerated JSON formatting and data conversions.

```powershell
python -m pip install -r requirements.txt
```

FFmpeg, LibreOffice, and Calibre are separate applications and must be installed
and available on `PATH` for their respective routes.

## Start the desktop app (Windows)

1. Install Python 3.10 or newer if it is not already installed.
2. Double-click `start_app.bat` in the project folder.
3. Choose a conversion, select your file, choose where to save it, and click
   **Convert file**. Use **ZIP tools** to create or extract archives.

You can also open PowerShell in this folder and run:

```powershell
python run_app.py
```

## Command-line usage

Run commands from the project folder:

```powershell
python -m file_converter list
python -m file_converter convert .\notes.txt .\notes.md
python -m file_converter convert .\document.json .\document.min.json --compact-json
python -m file_converter convert .\data.csv .\data.json --compact-json
python -m file_converter convert .\photo.jpeg .\photo.png
python -m file_converter zip-create .\bundle.zip .\documents .\notes.txt
python -m file_converter zip-extract .\bundle.zip .\extracted
```

## Adding a conversion

1. Add a converter function in the relevant module under `file_converter/formats/`.
   Converter functions receive source and destination `Path` objects plus
   `ConversionOptions`.
2. Register the source and destination extensions with `register()` in that
   module's `register_routes()`.
3. Import the module and call its `register_routes()` from
   `file_converter/formats/__init__.py`.
4. Add a focused test in `tests/`.
