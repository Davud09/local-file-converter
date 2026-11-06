import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from ..errors import FileConverterError

PRECOMPRESSED_EXTENSIONS = {
    ".7z",
    ".avif",
    ".bz2",
    ".docx",
    ".epub",
    ".gz",
    ".heic",
    ".jpeg",
    ".jpg",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".rar",
    ".webp",
    ".xz",
    ".zip",
    ".zst",
}


def _write_file(archive: zipfile.ZipFile, path: Path, arcname: str | Path) -> None:
    compression = (
        zipfile.ZIP_STORED
        if path.suffix.lower() in PRECOMPRESSED_EXTENSIONS
        else zipfile.ZIP_DEFLATED
    )
    archive.write(path, arcname=arcname, compress_type=compression)


def create_zip(archive_path: Path, inputs: list[Path]) -> None:
    if not inputs:
        raise FileConverterError("Provide at least one file or folder to archive.")

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1,
    ) as archive:
        for item in inputs:
            if not item.exists():
                raise FileConverterError(f"Input path does not exist: {item}")
            if item.is_file():
                _write_file(archive, item, item.name)
            elif item.is_dir():
                for child in item.rglob("*"):
                    if child.is_file():
                        _write_file(
                            archive, child, child.relative_to(item.parent)
                        )
            else:
                raise FileConverterError(f"Unsupported input path: {item}")


def _safe_destination(root: Path, member_name: str) -> Path:
    normalized_name = member_name.replace("\\", "/")
    posix_name = PurePosixPath(normalized_name)
    windows_name = PureWindowsPath(normalized_name)
    if (
        posix_name.is_absolute()
        or windows_name.is_absolute()
        or ".." in posix_name.parts
    ):
        raise FileConverterError(
            f"Unsafe path in ZIP archive: {member_name!r}"
        )

    destination = (root / Path(*posix_name.parts)).resolve()
    if not destination.is_relative_to(root.resolve()):
        raise FileConverterError(f"Unsafe path in ZIP archive: {member_name!r}")
    return destination


def extract_zip(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = _safe_destination(root, member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise FileConverterError(
                        f"Symbolic links are not extracted from ZIP files: "
                        f"{member.filename}"
                    )

                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
    except zipfile.BadZipFile as error:
        raise FileConverterError(f"Invalid ZIP archive: {archive_path}") from error
