# Architecture

The core (`classifier`, `scoring`, `cache`, `policy`, `batch`, `video`, `image`, `calibration`) imports no agent or transport SDK. `models/gemma.py` implements the MLX backend; `models/download.py` handles explicit provisioning. `adapters/` contains CLI, HTTP, MCP, wire schemas, and installation settings. Native plugin manifests share one skill and MCP launcher; they contain no inference implementation.

## Lifecycle and concurrency

`Analyzer` owns one backend, a visual-state LRU, and an inference lock. Direct Python callers may retain it for arbitrary tasks. `EngineWorker` lazily creates and operates it on one executor thread, with a bounded queue (eight pending/running requests). Work cancelled by a transport remains counted until it completes. Model initialization can retry after failure; failed initializations do not poison the worker.

The default stdio MCP and CLI adapters connect to `adapters/shared.py`. Discovery needs no model load. The first visual request starts one detached, lazy `EngineWorker` for the installation, shared through an owner-only Unix socket. A lifetime `flock` on a read-only installation-directory descriptor is inherited across process startup before model construction, so concurrent requests, stale sockets, and clients with different temporary directories cannot produce duplicate model owners. Existing pre-0.5.0 lock files are also locked read-only during upgrade; restart older sessions. Sockets/logs live in a private `$TMPDIR/vd-UID-HASH` directory. If an MCP host omits `TMPDIR`, macOS recovers the user temp directory through `getconf`; other platforms use the system temp directory. Short hashed names fit ordinary macOS temp paths; excessively long paths fail explicitly without falling back outside the sandbox. Read-only discovery probes the current temp root, the normal OS user temp root, and Claude’s standard `/tmp/claude-UID` root. An accessible existing engine is reused without creating files in another root. If it exits or an idle configuration is replaced, the next engine starts in the caller’s writable temp root. Arbitrary other custom roots are not enumerated; the lifetime lock still prevents duplicate models. Socket permission denials fail before submitting inference, and child startup errors include up to 4 KiB of the log. Permission failures do not trigger automatic alternate-transport or in-process retries. JSON requests/responses are bounded at 1 MiB/64 MiB; connections and the inference queue are bounded. No pickle is accepted.

The shared process exits after five idle minutes; active jobs prevent idle termination. Status does not load the model or extend its lifetime. Model/roots/version changes replace an idle process only after it exits; a busy process refuses replacement. Accepted inference is never automatically replayed after a disconnect. Existing older sessions must be restarted after upgrading; `--in-process`, direct Python, and manual HTTP are deliberate separate-model modes. Optional HTTP warms its worker at startup, serves startup metadata at `/health` without blocking behind jobs, and accepts CLI/MCP clients over loopback. There is no LaunchAgent, login service, remote inference, or provider fallback.

The installer uses physical memory for repeatable model selection, retains explicit choices, downloads only required files at pinned revisions, and records selection provenance separately from runtime configuration. Its own lock prevents overlapping installations. It starts no model unless the caller requests `--check-model`.

## Skills and model health

The installer supports native plugins, standalone skills, skills with direct MCP, and direct MCP alone. Integration choices live in installation metadata, outside the core. Personal skill folders link to a durable versioned copy with a local runtime binding. Its standard-library launcher forwards an argument list to stable, installation-bound shell launchers; it imports no inference engine. CLI, skill, and MCP all use the same shared lifecycle. Mode switches retire this package's previous user integration and refuse unrelated same-name registrations. Old environment versions remain for sessions to finish; stable launchers point new sessions at the selected release.

`Analyzer.model_health()` generates red and blue RGB inputs in memory, freshly encodes each, and checks expected winners and choice-rotation consistency. It bypasses visual caches, never reads user files, and remains independent of transports. MCP `model_health` and HTTP `POST /model_health` run it through their existing serialized worker. The standalone health adapter first validates settings and cached snapshot files, then verifies shared service startup and inference, reporting distinct error stages. `--no-inference` reports `preflight_ok`, skips model startup and cannot establish inference health. No health path downloads weights, certifies real-world accuracy, or starts a second private model.

## Scoring

| Method | Readout | Option presentation | Combination |
|---|---|---|---|
| `label` | exact A–J next-token logits | supplied order | restricted softmax |
| `label_permute` (default) | exact label logits | all cyclic rotations | arithmetic mean after semantic remapping |
| `label_logmean` | exact label logits | all cyclic rotations | mean log preference, then normalize |
| `candidate` | every candidate token plus end-of-turn | alternatives absent from prompt | normalized sequence likelihood |
| `candidate_permute` | complete candidate likelihoods | alternatives listed, cyclic rotations | arithmetic mean |

Label spellings must be unique single tokens at the actual prompt boundary. Candidate scoring checks that appending an answer preserves the tokenized prefix and scores the terminator. It prefills the question once and deep-copies KV state per candidate; a full-forward equivalence regression checks branch scores. Sequence likelihood retains a preference for shorter/common phrases; it is not length-normalized. Arithmetic rotation pooling is invariant to cyclic shifts, not all arbitrary orderings. `stable` measures unique winner agreement in the evaluated rotations only; tied rotations do not count as agreement. A one-pass method returns null stability.

`allowed_token_mass` exposes when restricted normalization hides preferences for tokens outside the answer set. Neither it nor the normalized score establishes correctness. Task policies can require score, margin, or rotation consistency; no policy yields `review`. Optional held-out temperature fitting binds to model snapshot, prompt version, question, method, and choice set. It produces separate adjusted scores, not an automatic policy change. Validate on an independent split before using probability interpretations.

## Efficient media batches

`analyze_batch` first validates the entire question plan and expands a folder or explicit file list. Shared questions can be overridden per file. Files execute in deterministic input order under one resident engine; per-file failures are isolated. Folder discovery is bounded and does not follow directory symlinks. The response includes per-file status and budget statistics.

`BatchScorer` hashes decoded RGB dimensions/pixels, so differently encoded copies can share work. It obtains visual features once for all questions on each distinct frame. A request-scoped LRU of at most 2,048 decisions avoids repeated language passes for identical content/question/ordered-choice keys. Method, policy, and model stay fixed for that memo's lifetime. Cached decisions are copied before returning and flagged `decision_reused`; they do not retain GPU tensors.

Each video opens one decoder and makes one sequential pass for all questions. The sampler retains at most two decoder frames, selects the frame at/before each requested timestamp, converts sampled frames to RGB, and scores all questions against shared visual state. Different questions get separate event timelines. Videos and still images share the same batch memo. This saves model loads, image encodes, decoder work, and repeated decision passes; it is more than invoking the single-file CLI repeatedly.

GPU tensor batching and cross-question language-prefix KV reuse are deliberately absent. Gemma's rotating caches, shared KVs, and bidirectional image masking need dedicated equivalence tests before sharing partial language prefixes. Each distinct question still prefills the language model. Serial GPU work also prevents concurrent large allocations. Sequential video decoding can be slower than keyframe seeking for very sparse sampling; bounded memory and multi-question reuse are the current tradeoff.

## Caches and budgets

The visual LRU defaults to four entries and 256 MiB, storing preprocessed pixels and projected features. The upstream processor's token expansion is checked on new encodes. Cached states are model/processor-specific. Single-image sessions re-read and hash file bytes, preventing stale screenshot reuse; batches and video use decoded RGB hashes. Sessions retain paths, not evicted tensors. MLX allocator retention means cache bytes are not a process-RSS bound.

Batch limits cover files, samples per video, total video samples, and requested decisions. Duplicate requests still count against output budgets even when scoring is reused. Failed videos conservatively spend the reserved budget, preventing repeated partial failures from exceeding a work cap. Inputs beyond exhausted budgets get explicit `skipped` status. A bounded batch result still can be large; select questions/limits appropriate to the agent's context budget.

## Video meaning and access

Every sample remains in the output, including uncertain decisions. Consecutive winners/actions form sample-and-hold intervals; boundaries are estimates, not observed transition times. `frame_time_s` exposes decoded timestamps, while `time_s` is the requested sampling position. Truncation and analyzed extent are explicit. Optional RGB thumbnail filtering is lossy and off by default. Exact-content decision reuse is separate and preserves deterministic scores. No temporary frame files are written.

Path resolution enforces configured roots and input limits: images 25 MiB/20 million pixels, videos 512 MiB/20 million pixels per frame. Decoder protocol/format options are per-container; secondary resource opens are rejected. No process-wide OpenCV setting is changed. Inference is offline with remote model code disabled. Snapshot provisioning separately checks architecture, tokenizer, all indexed shards, and safetensors byte ranges; weights are not bundled.

HTTP is a trusted local-user interface, not a multi-tenant security boundary. It rejects browser origins/unknown hosts, disables proxy use/redirects in clients, and caps bodies at 64 KiB. The default plugin uses stdio and a private Unix socket, with no TCP listener. Local analysis does not alter the hosting agent's attachment or tool-result retention policies.
