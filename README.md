# Visual Decider

Local finite-choice image and video decisions for **Codex, Claude Code, Python, and the CLI**. Ask a question with 2–10 choices; get structured model preferences without generating and parsing prose. The included backend uses **Gemma 4 + MLX on Apple Silicon macOS**. The Python core and backend have no agent dependencies; agent integration lives in separate adapters and plugin manifests.

**Scores are normalized preferences, not calibrated probabilities.** Videos are sampled still frames, not motion-model judgments. High scores and consistent choice permutations can still be wrong.

## Install

Prerequisites: Apple Silicon macOS, Git, Python 3, and the CLI for the agent you use. Allow sufficient disk space and memory for the selected model; the default E4B backend measured approximately 17 GB peak MLX allocation on an M3 Max. The installer provisions Python 3.12 with uv if needed.

```bash
curl -fsSL https://raw.githubusercontent.com/tomyak/viz-dec/v0.2.0/install.sh | bash
```

This one command:

- Installs locked dependencies and the engine in `~/.local/share/visual-decider/versions/0.2.0`.
- Reuses complete cached Gemma weights or downloads missing weights from Hugging Face. Known models use pinned commit revisions.
- Registers the plugin with every detected supported agent, including MCP configuration and its skill. **No manual SKILL.md copying.**
- Uses your home directory as the default media access root. Opens no listening port and installs no login service.

For gated Google weights, accept access on the [model page](https://huggingface.co/google/gemma-4-E4B-it) and authenticate with `hf auth login` or `HF_TOKEN` before installing. The installer reports an actionable error if access is unavailable. The MIT code license does not license the model weights.

Select agents, a model, or access roots:

```bash
# From a cloned checkout:
bash install.sh --agents both --allow-root /path/to/media
bash install.sh --agents codex --model mlx-community/gemma-4-26B-A4B-it-4bit
bash install.sh --agents claude --allow-root /  # all media readable by your account
bash install.sh --agents none                # engine and CLI only
```

Roots can be repeated. Existing settings are retained unless explicitly overridden. Configuration is in `~/.local/share/visual-decider/config.json`; it stores a local model path and allowed roots, never credentials. Set `VISUAL_DECIDER_HOME` consistently in the installer and agent environment to relocate it.

Start a fresh Codex or Claude Code session after installation. The stdio MCP process initializes quickly, loads Gemma on the first tool call, and retains it for that process's lifetime. Closing the agent releases its process. Separate agents may load separate model instances; optional shared HTTP mode is documented below.

## Use from an agent

Drag an image/video onto your agent and ask:

> Use visual-decider on this file. Is there one person or two people?

The agent passes the attachment's absolute local path. Files do not need to be in the repository or fixtures folder; they must be readable under a configured root. The shared skill preserves the exact user question and supplied choices, attributes the model's answer, and reports disagreement between prompt variants.

| MCP tool | Purpose |
|---|---|
| `classify_image` | One question and choices on an image |
| `inspect_image` | Multiple questions, one image encoding |
| `analyze_video` | One question across sampled video frames |
| `analyze_batch` | Folder or file list; shared or per-file question batches |

## Efficient batches

The batch engine shares visual encodings, memoizes identical content/question decisions within the job, and decodes each video **once for all its questions**. Identical decoded pixels can reuse work even across image formats. It holds a bounded visual LRU and a bounded decision LRU; GPU scoring stays serialized. It does not claim simultaneous tensor batching or cross-question language-KV reuse. See [architecture](ARCHITECTURE.md).

Folder request through MCP or HTTP:

```json
{
  "folder": "/absolute/path/to/media",
  "recursive": true,
  "questions": [
    {"question": "Is a person visible?", "choices": ["Yes", "No"]},
    {"question": "How many people are visible?", "choices": ["None", "One", "Two", "More than two"]}
  ],
  "sample_interval": 1.0,
  "max_total_frames": 1000
}
```

A file list can mix images/videos and override questions for individual files:

```json
{
  "files": [
    "/absolute/path/to/photo.jpg",
    {"path": "/absolute/path/to/clip.mp4", "questions": [
      {"question": "Is the patient in the room?", "choices": ["Yes", "No"]},
      {"question": "Did the patient fall?", "choices": ["Yes", "No"]}
    ]}
  ],
  "questions": [{"question": "Is a person visible?", "choices": ["Yes", "No"]}]
}
```

Supply exactly one of `folder` or `files`. Folder discovery sorts names, skips hidden entries, filters supported media extensions, and does not traverse directory symlinks. Every resolved file must still pass the access-root check. Empty folders and over-limit folders fail explicitly. File lists retain input order and return `ok`, `error`, or `skipped` per entry. Questions are validated before media inference begins.

Defaults: 128 files (maximum 512), 32 questions per file, 300 samples per video (maximum 1,000), 1,000 samples across the batch (maximum 10,000), and 4,096 requested decisions (maximum 16,384). Use `max_files`, `max_frames`, `max_total_frames`, and `max_decisions` to adjust these. Failed videos conservatively consume their reserved budget; later files are skipped when budgets are exhausted. Every video result reports `truncated` and `analyzed_until`. The summary reports budget use, vision encodes, cache hits, scoring passes, and reused decisions.

For multiple video questions, each sample contains a `decisions` array; `questions` contains a separate event timeline for each question. Event intervals are sample-and-hold estimates. `frame_time_s` records the actual decoded frame timestamp. Short events between samples can be missed.

## CLI and Python

The installer prints the executable location; it does not modify shell startup files. For convenience:

```bash
export PATH="$HOME/.local/share/visual-decider/versions/0.2.0/bin:$PATH"
visual-decide image /path/to/screen.png 'Is an error visible?' Yes No
visual-decide video /path/to/clip.mp4 'Is a person visible?' Yes No --sample-interval 1
visual-decide batch --folder /path/to/media --questions-file questions.json --recursive
visual-decide batch --files /path/to/a.jpg /path/to/b.mp4 --questions-file questions.json
visual-decide batch --manifest batch.json
```

`questions.json` contains an array of question/choices objects. `batch.json` contains a complete request like the examples above. CLI output is JSON; inspect per-file statuses even when the command completes successfully.

```python
from visual_decider import Analyzer

analyzer = Analyzer()  # Load once, reuse. Inference requires cached weights.
result = analyzer.analyze_batch(
    folder="/path/to/media",
    questions=[{"question": "Is a person visible?", "choices": ["Yes", "No"]}],
    recursive=True,
)
print(result["summary"])
```

The core package can be imported and tested without MLX or an agent SDK. The included MLX backend requires Apple Silicon; platform independence here means independence from **agent platforms**, not universal accelerator support. An alternate backend can implement `encode`, `score`, and `info` and be passed as `Analyzer(backend=...)`.

## Optional shared HTTP service

To share one model across agent processes, start this manually in a separate terminal:

```bash
visual-decider-http --root /path/to/media
visual-decide --url http://127.0.0.1:8765 image /path/to/screen.png 'Is an error visible?' Yes No
visual-decider-mcp --url http://127.0.0.1:8765
```

The last command is the alternative MCP launch command for a custom agent configuration. Disable the bundled plugin's MCP server before adding a duplicate custom registration. HTTP exposes `/classify_image`, `/inspect_image`, `/analyze_video`, `/analyze_batch`, and `/health`. It binds to loopback, rejects browser origins and remote hosts, and limits request bodies to 64 KiB. For large batches prefer folders or stdio MCP. Health returns startup metadata without waiting behind inference.

This is a trusted local-user service. Another local process with access to the port can request files in the allowed roots. The engine sends no image/video bytes to remote inference. Agent hosts receive paths, questions, and structured results and follow their own data-handling policies. Provisioning contacts package/model hosts. Inference only opens validated local weights; remote code loading is disabled.

## Development and releases

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

[Release instructions](docs/RELEASING.md), [private corporate distribution](docs/CORPORATE.md), [review findings](docs/REVIEW.md), [validation](docs/VALIDATION.md), and [historical model benchmarks](benchmarks/REPORT.md).

License: [MIT](LICENSE). The repository contains original synthetic test fixtures. Personal photos/videos, cached models, virtual environments, and local settings are excluded from distribution.
