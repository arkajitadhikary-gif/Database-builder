from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable, Iterator
from pathlib import Path

PDF_MAGIC = b"%PDF-"


def discover_paths(
    requested_paths: Iterable[str], recursive: bool, max_files: int | None = None
) -> list[Path]:
    discovered: dict[str, Path] = {}

    def add(path: Path) -> None:
        resolved = path.resolve()
        discovered[str(resolved)] = resolved
        if max_files is not None and len(discovered) > max_files:
            raise ValueError(f"discovery limit exceeded: more than {max_files} files")
    for raw in requested_paths:
        path = Path(raw).expanduser()
        if path.is_file():
            add(path)
            continue
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            for candidate in path.glob(pattern):
                if candidate.is_file():
                    add(candidate)
    return sorted(discovered.values(), key=lambda item: str(item).casefold())


def iter_file_chunks(path: Path, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            yield chunk


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    for chunk in iter_file_chunks(path):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_pdf(path: Path, max_bytes: int | None = None) -> tuple[bool, str]:
    if not path.exists():
        return False, "source path does not exist"
    if not path.is_file():
        return False, "source path is not a regular file"
    if path.suffix.lower() != ".pdf":
        return False, "unsupported extension"
    if max_bytes is not None:
        try:
            if path.stat().st_size > max_bytes:
                return False, f"file exceeds configured size limit of {max_bytes} bytes"
        except OSError as exc:
            return False, f"unable to stat source: {exc}"
    try:
        with path.open("rb") as handle:
            header = handle.read(len(PDF_MAGIC))
    except OSError as exc:
        return False, f"unable to read source: {exc}"
    if header != PDF_MAGIC:
        return False, "file does not have a PDF header"
    return True, "valid PDF header"


def safe_source_path(path: Path, allowed_roots: Iterable[Path]) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    roots = [root.expanduser().resolve(strict=False) for root in allowed_roots]
    if not any(os.path.commonpath((resolved, root)) == str(root) for root in roots):
        raise ValueError("source path is outside configured ingestion roots")
    return resolved
