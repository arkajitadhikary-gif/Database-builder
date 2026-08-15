import argparse
import asyncio

import uvicorn

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


async def _serve(host: str, port: int) -> None:
    config = uvicorn.Config("app.main:app", host=host, port=port, reload=False, access_log=False)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Judicore FastAPI backend")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    try:
        asyncio.run(_serve(args.host, args.port), loop_factory=asyncio.SelectorEventLoop)
    except KeyboardInterrupt:
        pass
