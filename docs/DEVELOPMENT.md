# Development

[← Quick start](../README.md)

Run these commands from a cloned repository:

```bash
uv sync --frozen --all-extras
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
RUN_MODEL_TESTS=1 uv run pytest tests/model -q  # Apple Silicon + cached weights
uv run python benchmarks/mcp_smoke.py         # Real stdio MCP and Gemma
uv run python scripts/release.py --check
uv build
```

[Release instructions](RELEASING.md), [private corporate distribution](CORPORATE.md), [review findings](REVIEW.md), [validation](VALIDATION.md), and [historical model benchmarks](../benchmarks/REPORT.md).
