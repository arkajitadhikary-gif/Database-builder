from __future__ import annotations

import asyncio
import json

from app.db.session import check_database
from app.services.embeddings import check_embedding_provider, get_embedding_provider
from app.services.pdf import ocr_available


async def main() -> None:
    database_ok, database_detail = await check_database()
    ocr_ok, ocr_detail = ocr_available()
    embedding_ok, embedding_detail = check_embedding_provider()
    embedding_dimension = None
    if embedding_ok:
        provider = get_embedding_provider()
        embedding_dimension = len(provider.embed(["runtime dimension verification"])[0])
    print(json.dumps({
        "postgresql": {"ready": database_ok, "detail": database_detail},
        "ocr": {"ready": ocr_ok, "detail": ocr_detail},
        "embedding": {
            "ready": embedding_ok,
            "detail": embedding_detail,
            "vector_dimension": embedding_dimension,
        },
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
