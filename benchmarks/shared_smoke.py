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
            responses = [result.structured_content for result in results]
            assert sum(not result["model_cached"] for result in responses) == 1
            for result in responses:
                timing = result["timing"]
                assert timing["round_trip_ms"] >= timing["total_ms"]
                assert (
                    timing["model_load_ms"] == 0
                    if result["model_cached"]
                    else timing["model_load_ms"] > 0
                )
            print(
                json.dumps(
                    [{"model_cached": r["model_cached"], "timing": r["timing"]} for r in responses]
                ),
                flush=True,
            )
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
            assert json.loads(output)["model_cached"]
            assert json.loads(output)["timing"]["model_load_ms"] == 0
            assert client.status()["pid"] == pid
            print("Installed skill CLI reused the same model PID and visual cache", flush=True)
            batch = await sessions[0].call_tool(
                "analyze_batch",
                {
                    "files": [payload["path"], str(Path("tests/fixtures/sequence.avi").resolve())],
                    "questions": [
                        {"question": "Is a person visible?", "choices": ["Yes", "No"]},
                        {"question": "Is the image bright?", "choices": ["Yes", "No"]},
                    ],
                    "max_frames": 2,
                },
            )
            assert not batch.is_error, batch
            value = batch.structured_content
            assert value["summary"]["succeeded"] == 2 and value["model_cached"]
            assert value["timing"]["model_load_ms"] == 0
            assert value["timing"]["execution_ms"] >= sum(
                entry["timing"]["execution_ms"] for entry in value["results"]
            )
            print(
                "Mixed image/video batch returned whole-job and per-file execution times",
                flush=True,
            )
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
