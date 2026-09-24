import asyncio

from visual_decider.adapters.mcp_server import create_server


class Client:
    def call(self, tool, **kwargs):
        return {"winner": "Yes", "tool": tool, "payload": kwargs}


def test_mcp_schema_and_dispatch():
    async def run():
        server = create_server(Client())
        tools = await server.list_tools()
        assert {x.name for x in tools} == {
            "classify_image",
            "inspect_image",
            "analyze_video",
            "analyze_batch",
        }
        result = await server.call_tool(
            "classify_image", {"path": "x.png", "question": "Visible?", "choices": ["Yes", "No"]}
        )
        assert result.structured_content["winner"] == "Yes"
        assert not result.is_error
        assert all(x.output_schema for x in tools)

    asyncio.run(run())


def test_mcp_batch_overrides_reach_core_contract():
    async def run():
        server = create_server(Client())
        result = await server.call_tool(
            "analyze_batch",
            {
                "files": [
                    "a.png",
                    {"path": "b.mp4", "questions": [{"question": "B?", "choices": ["Yes", "No"]}]},
                ],
                "questions": [{"question": "A?", "choices": ["One", "Two"]}],
            },
        )
        assert not result.is_error, result
        payload = result.structured_content["payload"]
        assert payload["files"][1]["questions"][0]["question"] == "B?"
        assert payload["questions"][0]["question"] == "A?"

    asyncio.run(run())
