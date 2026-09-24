import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin", type=Path, help="Use the exact installed .mcp.json launcher")
    args = parser.parse_args()
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "visual_decider.adapters.mcp_server"]
    )
    if args.plugin:
        launcher = json.loads((args.plugin / ".mcp.json").read_text())["mcpServers"][
            "visual-decider"
        ]
        params = StdioServerParameters(**launcher)
    async with stdio_client(params) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools", [t.name for t in tools.tools], flush=True)
            for name, payload in [
                (
                    "classify_image",
                    dict(
                        path=str(Path("tests/fixtures/error.png").resolve()),
                        question="What state is the UI in?",
                        choices=["Error dialog", "Dashboard"],
                    ),
                ),
                (
                    "analyze_video",
                    dict(
                        path=str(Path("tests/fixtures/sequence.avi").resolve()),
                        question="What is depicted?",
                        choices=["Dog", "Person", "Empty room"],
                        sample_interval=2.0,
                    ),
                ),
                (
                    "inspect_image",
                    dict(
                        path=str(Path("tests/fixtures/login.png").resolve()),
                        questions=[
                            dict(
                                question="What state is the UI in?",
                                choices=["Login page", "Dashboard"],
                            )
                        ],
                    ),
                ),
            ]:
                result = await session.call_tool(name, payload)
                assert not result.is_error, result
                assert result.structured_content, result
                if name == "classify_image":
                    assert result.structured_content["winner"] == "Error dialog"
                if name == "inspect_image":
                    assert result.structured_content["decisions"][0]["winner"] == "Login page"
                if name == "analyze_video":
                    assert len(result.structured_content["events"]) == 4
                print(name, "structured result verified", flush=True)
            batch = await session.call_tool(
                "analyze_batch",
                {
                    "files": [
                        str(Path("tests/fixtures/login.png").resolve()),
                        str(Path("tests/fixtures/login.png").resolve()),
                        {
                            "path": str(Path("tests/fixtures/sequence.avi").resolve()),
                            "questions": [
                                {
                                    "question": "What is depicted?",
                                    "choices": ["Dog", "Person", "Empty room"],
                                },
                                {"question": "Is a person visible?", "choices": ["Yes", "No"]},
                            ],
                        },
                    ],
                    "questions": [
                        {
                            "question": "What state is the UI in?",
                            "choices": ["Login page", "Dashboard"],
                        }
                    ],
                    "sample_interval": 2.0,
                },
            )
            assert not batch.is_error, batch
            result = batch.structured_content
            assert result["summary"]["succeeded"] == 3, result
            assert result["summary"]["decisions_reused"] >= 1
            assert result["results"][0]["result"]["decisions"][0]["winner"] == "Login page"
            assert len(result["results"][2]["result"]["questions"]) == 2
            assert len(result["results"][2]["result"]["questions"][0]["events"]) == 4
            print(
                "analyze_batch shared questions, overrides, memo and video verified",
                result["summary"],
                flush=True,
            )
            invalid = await session.call_tool(
                "classify_image", dict(path="/nonexistent", question="x", choices=["a", "b"])
            )
            assert invalid.is_error


asyncio.run(main())
