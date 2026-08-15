import argparse
import asyncio
import sys

import uvicorn

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


async def _serve(host: str, port: int) -> None:
    config = uvicorn.Config("app.main:app", host=host, port=port, reload=False, access_log=False)
    server = uvicorn.Server(config)
    await server.serve()


if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Judicore FastAPI backend")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    try:
        asyncio.run(_serve(args.host, args.port), loop_factory=asyncio.SelectorEventLoop)
    except TypeError:
        asyncio.run(_serve(args.host, args.port))
