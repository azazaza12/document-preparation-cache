import subprocess
from pathlib import Path

from app.config import UnoConverterSettings
from app.infrastructure.extraction.conversion_target import ConversionTarget
from app.infrastructure.extraction.exceptions import DocumentConversionError


def unoconvert(
    settings: UnoConverterSettings,
    data: bytes,
    target: ConversionTarget,
    *,
    file_name: str | None = None,
) -> bytes:
    converter_bin = settings.UNO_BINARY
    host = settings.UNO_HOST
    port = settings.UNO_PORT
    timeout = settings.CONVERT_TIMEOUT_SEC
    base_cmd = [
        converter_bin,
        "--host",
        host,
        "--port",
        str(port),
        "--protocol",
        "http",
        "--convert-to",
        target.value,
        "-",
        "-",  # infile = stdin, outfile = stdout
    ]

    suffix = ""
    if file_name:
        suffix = Path(file_name).suffix.lower().lstrip(".")

    errors: list[str] = []
    cmds: list[list[str]] = [list(base_cmd)]
    if suffix:
        cmds.append([*base_cmd, "--input-filter", suffix])

    for attempt, cmd in enumerate(cmds, start=1):
        try:
            proc = subprocess.run(  # noqa: S603
                cmd, input=data, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            errors.append(
                "\n".join(
                    [
                        f"attempt {attempt}: timed out after {timeout}s",
                        f"cmd: {cmd!r}",
                        f"host={host}, port={port}",
                    ]
                )
            )
            continue

        if proc.returncode != 0:
            errors.append(
                "\n".join(
                    [
                        f"attempt {attempt}: failed (exit {proc.returncode})",
                        f"cmd: {cmd!r}",
                        f"host={host}, port={port}",
                        f"stdout: {proc.stdout!r}",
                        f"stderr: {proc.stderr!r}",
                    ]
                )
            )
            continue

        return proc.stdout

    msg = "UNO conversion failed\n" + "\n\n".join(errors)
    raise DocumentConversionError(msg)
