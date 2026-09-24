# Using Visual Decider

[← Quick start: Claude Code or Codex](../README.md)

## Ask your agent

Drag an image/video onto your agent and ask:

> Use visual-decider on this file. Is there one person or two people?

The agent passes the attachment's absolute local path. Files do not need to be in the repository or fixtures folder; they must be readable under a configured root. The shared skill preserves the exact user question and supplied choices, attributes the model's answer, and reports disagreement between prompt variants.

| MCP tool | Purpose |
|---|---|
| `classify_image` | One question and choices on an image |
| `inspect_image` | Multiple questions, one image encoding |
| `analyze_video` | One question across sampled video frames |
| `analyze_batch` | Folder or file list; shared or per-file question batches |
| `model_health` | Fresh synthetic vision/scoring test on the same model |

## Reading the results

Scores are normalized model preferences, not calibrated probabilities. High scores
and consistent choice permutations can still be wrong. Videos are sampled still
frames, not motion-model judgments; brief events between samples may be missed.
See [scoring and video semantics](../ARCHITECTURE.md) for the full interpretation.

### Timing and cache status

Image, inspect, video, batch, and model-health results include these fields automatically:

```json
{
  "model_cached": true,
  "timing": {
    "queue_ms": 0.2,
    "model_load_ms": 0.0,
    "execution_ms": 420.0,
    "total_ms": 420.2,
    "round_trip_ms": 425.0
  }
}
```

The values above are illustrative. All times are elapsed milliseconds.

- `model_cached`: the model was already loaded **in memory when execution began**. A cold request returns `false`; a request queued behind that load returns `true`. This does not describe weights downloaded to disk or the image-feature `cache_hit` field.
- `model_load_ms`: initialization charged to this request, including local model validation/loading. It is exactly zero for a resident model.
- `execution_ms`: decoding, visual encoding, and scoring for the complete operation, after loading. For a batch, each entry also has `timing.execution_ms`, including failed files; skipped files have zero.
- `queue_ms`: time waiting for the single engine worker, including other requests' model loading.
- `total_ms`: queue + model load + execution, measured inside the engine.
- `round_trip_ms`: added by the shared-service and HTTP clients; includes connection/request/response overhead, and shared-process discovery/startup. Direct Python and `--in-process` results omit it. It does not include starting the CLI/agent itself.

Existing decision `latency_ms` still measures question scoring. Do not sum it to estimate complete batch/video execution, because decisions can be reused. Direct `Analyzer` calls start after construction, so they report `model_cached: true` and zero load time; historical backend loading remains in `analyzer.info()`. HTTP loads at server startup, so its subsequent requests also reuse the model. CLI health reports contain these fields in the `inference` check.

## Efficient batches

The batch engine shares visual encodings, memoizes identical content/question decisions within the job, and decodes each video **once for all its questions**. Identical decoded pixels can reuse work even across image formats. It holds a bounded visual LRU and a bounded decision LRU; GPU scoring stays serialized. It does not claim simultaneous tensor batching or cross-question language-KV reuse. See [architecture](../ARCHITECTURE.md).

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
export PATH="$HOME/.local/share/visual-decider/bin:$PATH"
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

For applications that need an HTTP endpoint instead of the default shared Unix socket, start this manually in a separate terminal:

```bash
visual-decider-http --root /path/to/media
visual-decide --url http://127.0.0.1:8765 image /path/to/screen.png 'Is an error visible?' Yes No
visual-decider-mcp --url http://127.0.0.1:8765
```

The last command is the alternative MCP launch command for a custom agent configuration. Disable the bundled plugin's MCP server before adding a duplicate custom registration. HTTP exposes `/classify_image`, `/inspect_image`, `/analyze_video`, `/analyze_batch`, and `/health`. It binds to loopback, rejects browser origins and remote hosts, and limits request bodies to 64 KiB. For large batches prefer folders or stdio MCP. `GET /health` returns startup metadata without waiting behind inference; `POST /model_health` with `{}` performs the synthetic test on that HTTP worker through its inference queue.

This is a trusted local-user service. Another local process with access to the port can request files in the allowed roots. The engine sends no image/video bytes to remote inference. Agent hosts receive paths, questions, and structured results and follow their own data-handling policies. Provisioning contacts package/model hosts. Inference only opens validated local weights; remote code loading is disabled.
