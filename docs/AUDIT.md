# Prototype and upstream audit — 2026-09-24

Historical source review performed during the initial prototype evaluation. Superseded packaging and lifecycle details are covered in REVIEW.md. The prototype archive and research checkouts were removed during cleanup.

## Prototype findings

- Only one log-sum-exp test. Its README explicitly disclaims a real Metal run.
- Generation wrapper reads a single token's logprobs, but performs image preparation and vision encoding for each permutation. It neither shares visual state nor measures cache behavior.
- Label spellings are pooled without proving that they are valid continuations at the actual template boundary. The new backend checks exact token boundaries and distinct single-token labels.
- Choice validation silently coerces arbitrary objects to strings.
- Arithmetic cyclic averaging is a useful baseline, but only exactly invariant to cyclic rotations, not all orderings. Nonlinear context/order effects remain.
- Video drops low-scoring samples before aggregation, can bridge missing evidence, counts retained samples as classified frames, and assigns zero-length single-sample events. The new pipeline retains all sampled decisions and uses explicit sample-and-hold intervals.
- Server loads on import and executes GPU work in an async route without an inference queue. The new server owns one worker and one resident model; adapters share it.

## Source-level inspection

Inspected source checkouts and commit IDs are recorded in `upstream-lock.json`. These are research dependencies, not runtime imports; the temporary source checkouts were removed after inspection.

- [MLX-VLM](https://github.com/Blaizzy/mlx-vlm): `models/gemma4/gemma4.py` exposes `encode_image`, `cached_image_features`, and raw language-model logits. `processing_gemma4.py` expands image tokens and generates multimodal token types. `language.py` has rotating/full KV caches and shared-KV layers. Retain multimodal token types for bidirectional vision masking. `generate/dispatch.py` has both vision caching and automatic prefix caching, but the decision backend calls the model directly. Installed release 0.7.2 and current main both expose the required interfaces.
- [SemIf](https://github.com/TheoLeeCJ/SemIf): `src/semif_phase1/direct.py` validates round-trip single-token slots and boundaries, reads last-position vocabulary logits, and reports allowed token mass. `serial.py` validates a common prefix and copies KV cache per isolated question suffix. It does not replace labels with full semantic continuation likelihoods.
- [Visual-Jev](https://github.com/jiangxiluning/Visual-Jev): source includes the SemIf-style direct, serial, and shared paths. The serial scorer copies a multimodal state-prefix cache. Its Qwen/PyTorch shared scoring does not directly transfer to Gemma's MLX cache layout.
- [AnyJev](https://github.com/nokia-applied-research/AnyJev): `anyjev/readout.py`, `decider.py`, and `calibrate/permute.py` use label-token readouts, cyclic shifts, and arithmetic or geometric pooling. Geometric pooling cancels additive label-position bias under that mathematical model; actual model interactions need measurement. Contextual priors and held-out temperature scaling are separate operations. Its newer learned-head/L2 machinery is outside this project's zero-training scope.
- [Djev](https://github.com/Davipar/djev-dev): `djev/engine.py` compiles answer slots into a fixed diffusion canvas and reads allowed labels; `runtime/vision.py` and `vision_patch.py` support multimodal runtime integration. CUDA/vLLM/diffusion are not dependencies of this implementation.
- [local-vision-mcp](https://github.com/tmchao7/local-vision-mcp): `src/ollama-client.mjs` calls Ollama chat with schema-constrained generated text, timeouts, and persistent-model settings. `skills/vision/SKILL.md` teaches routing. Useful adapter patterns, but no direct candidate scoring.
- [mcp-vision-bridge](https://github.com/ujiahka/mcp-vision-bridge): `src/privacy.js` gates remote endpoints; provider adapters generate descriptions. Our client instead only permits loopback HTTP and cannot select a remote provider.
- [vlm-mcp-server](https://github.com/syntx-ai/vlm-mcp-server): `src/providers/chat-completions.ts` and provider routing support multiple generated-answer APIs. These are not raw-logit decision APIs.
- [Local-MMCP](https://github.com/rorojiao/local-mmcp): `local_mmcp/clients/omlx_client.py` uses local chat completions and model lifetime management; FFmpeg/image adapters support broader media workflows. Our first video path stays sampled-image-only.
- [ollama-vision-mcp](https://github.com/masterLazy/ollama-vision-mcp): local-image normalization and chat-completion bridge. Another similarly named search result (`wzul/ollama-vision-mcp`) could not be cloned; no claims about its uninspected implementation.

[Official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [OpenAI skill guidance](https://developers.openai.com/plugins/build/skills), and [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp) were checked for adapter configuration. Installed MCP Python SDK is **2.2.0**: `MCPServer` replaces the old `FastMCP` import. No obsolete SDK import is used.

## Verified local environment

The system Python had MLX-VLM 0.4.4, MLX 0.31.1, and Transformers 5.5.0. A project-local virtual environment was created without modifying those installations. Tested pins are MLX-VLM 0.7.2, MLX 0.32.2, Transformers 5.17.0, and MCP 2.2.0; the complete installed set is recorded in `uv.lock`.

The original model probe verified raw logits before the new adapters were written. Real Metal execution requires escaping the app's filesystem/network sandbox; the initial sandboxed import explicitly reported no Metal device. No CPU or remote-inference fallback was introduced.
