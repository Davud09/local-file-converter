import shutil
import subprocess
from pathlib import Path

from ..errors import FileConverterError
from ..models import ConversionOptions
from ..registry import register


def mp3_to_wav(
    source: Path, destination: Path, options: ConversionOptions
) -> None:
    del options
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileConverterError(
            "MP3 to WAV conversion requires FFmpeg. Install FFmpeg and add it to PATH."
        )

    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(source), str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip().splitlines()
        message = detail[-1] if detail else "FFmpeg reported an error."
        raise FileConverterError(f"FFmpeg could not convert the file: {message}")


def register_routes() -> None:
    register(".mp3", ".wav", mp3_to_wav, "Convert MP3 audio to WAV using FFmpeg")
