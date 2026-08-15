from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

import fitz
from app.services.pdf import extract_pdf


def create_fixture(path: Path, pages: int) -> None:
    document = fitz.open()
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"Test-only stress fixture page {index + 1}. This is not production legal data.")
    document.save(path)
    document.close()


async def process(path: Path, semaphore: asyncio.Semaphore) -> int:
    async with semaphore:
        result = await asyncio.to_thread(extract_pdf, path)
        return result.page_count


async def main(count: int, pages: int, workers: int) -> None:
    with tempfile.TemporaryDirectory(prefix="judicore-stress-") as directory:
        root = Path(directory)
        paths = []
        for index in range(count):
            path = root / f"fixture-{index:04d}.pdf"
            create_fixture(path, pages)
            paths.append(path)
        semaphore = asyncio.Semaphore(workers)
        tracemalloc.start()
        start = time.perf_counter()
        page_counts = await asyncio.gather(*(process(path, semaphore) for path in paths))
        elapsed = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(json.dumps({
            "fixture_count": count,
            "pages_per_fixture": pages,
            "configured_workers": workers,
            "processed_pages": sum(page_counts),
            "elapsed_seconds": round(elapsed, 4),
            "peak_python_memory_bytes": peak,
            "bounded_concurrency": workers >= 1,
        }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(main(args.count, args.pages, args.workers))
