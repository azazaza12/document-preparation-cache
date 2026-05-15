import subprocess
from typing import Literal

from app.config import UnoConverterSettings
from app.infrastructure.extraction.exceptions import DocumentConversionError


def unoconvert_sync(
    settings: UnoConverterSettings, data: bytes, target: Literal["docx", "xlsx"]
) -> bytes:
    converter_bin = settings.UNO_BINARY
    host = settings.UNO_HOST
    port = settings.UNO_PORT
    timeout = settings.CONVERT_TIMEOUT_SEC
    cmd = [
        converter_bin,
        "--host",
        host,
        "--port",
        str(port),
        "--protocol",
        "http",
        "--convert-to",
        target,
        "-",
        "-",  # infile = stdin, outfile = stdout
    ]
    try:
        proc = subprocess.run(  # noqa: S603
            cmd, input=data, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"UNO conversion timed out after {timeout}s (host={host}, port={port})"
        raise DocumentConversionError(msg) from exc

    if proc.returncode != 0:
        err_parts = [
            f"UNO conversion failed (exit {proc.returncode})",
            f"host={host}, port={port}",
            f"stdout: {proc.stdout!r}",
            f"stderr: {proc.stderr!r}",
        ]
        raise DocumentConversionError("\n".join(err_parts))
    return proc.stdout
