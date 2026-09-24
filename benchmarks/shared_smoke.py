"""Prove two installed MCP clients and a CLI command share the same real Gemma process."""

import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from visual_decider.adapters.shared import SharedClient


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--home", type=Path, required=True, help="Isolated installed test environment"
    )
    args = parser.parse_args()
    home = args.home.resolve()
    launcher = json.loads((home / "marketplace/plugins/visual-decider/.mcp.json").read_text())[
        "mcpServers"
    ]["visual-decider"]
    client = SharedClient(home=home)
    payload = {
        "path": str(Path("tests/fixtures/error.png").resolve()),
        "question": "What state is the UI in?",
        "choices": ["Error dialog", "Dashboard"],
    }
    try:
        async with AsyncExitStack() as stack:
            sessions = []
            for _ in range(2):
                streams = await stack.enter_async_context(
                    stdio_client(StdioServerParameters(**launcher))
                )
                session = await stack.enter_async_context(ClientSession(*streams[:2]))
                await session.initialize()
                sessions.append(session)
            results = await asyncio.gather(
                *[session.call_tool("classify_image", payload) for session in sessions]
            )
            for result in results:
                assert not result.is_error, result
                assert result.structured_content["winner"] == "Error dialog"
            assert any(result.structured_content["cache_hit"] for result in results)
            pid = client.status()["pid"]
            print(
                f"Two concurrent installed MCP clients share model PID {pid} and visual cache",
                flush=True,
            )
            helper = (
                home / "marketplace/plugins/visual-decider/skills/visual-decider/scripts/run.py"
            )
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(helper),
                "image",
                payload["path"],
                payload["question"],
                *payload["choices"],
                env={**os.environ, "VISUAL_DECIDER_HOME": str(home)},
                stdout=asyncio.subprocess.PIPE,
            )
            output, _ = await process.communicate()
            assert process.returncode == 0
            assert json.loads(output)["cache_hit"]
            assert client.status()["pid"] == pid
            print("Installed skill CLI reused the same model PID and visual cache", flush=True)
            health = await sessions[0].call_tool("model_health", {})
            assert not health.is_error, health
            assert health.structured_content["status"] == "ok"
            process = await asyncio.create_subprocess_exec(
                str(home / "bin/visual-decider-health"),
                stdout=asyncio.subprocess.PIPE,
            )
            output, _ = await process.communicate()
            assert process.returncode == 0
            report = json.loads(output)
            assert report["status"] == "ok" and report["service"]["pid"] == pid
            assert (
                report["checks"][-1]["model"]["vision_encodes"]
                == health.structured_content["model"]["vision_encodes"] + 2
            )
            print("MCP and CLI health freshly encoded images on the same model PID", flush=True)
        assert client.status()["pid"] == pid
        print("Agent disconnects retained the single shared engine until idle shutdown", flush=True)
    finally:
        client.stop()


asyncio.run(main())
