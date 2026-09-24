---
name: visual-decider
description: Use local finite-choice image and sampled-video decisions for explicit visual questions, UI state checks, repeated screenshots, and regression triage. Use when the user requests visual-decider or a few explicit alternatives can answer the question.
---

Use the visual-decider MCP tools to score local visual evidence with Gemma.

1. Pass the actual absolute path from the attachment or screenshot. Files can be anywhere under the configured roots; the fixture folder has no special role. If an attachment lacks a local path, obtain it using the host's file tools. Never invent a path.
2. Preserve the user's exact question and supplied choices. For a yes/no question without choices, use `["Yes", "No"]`. Do not replace “Did the patient fall?” with a posture classification, or broaden/narrow the alternatives silently. If clarification is essential, ask before changing the task.
3. Call `classify_image` for one question or `inspect_image` for multiple questions on the same image; the latter reuses visual features. Supply 2–10 distinct choices. When designing an open-ended choice set, include an appropriate “Other” alternative and state your choices.
4. Use `analyze_video` for sampled frames. Preserve the question even if it describes an event. This engine has no motion model: sampled still images alone cannot establish all temporal events. Choose an interval suitable for the event, inspect every relevant sample, and report `truncated` and `analyzed_until`. Events are sample-and-hold estimates; do not claim exact start/end times. Fast actions between samples may be missed.
5. For folders/file lists, use `analyze_batch` with shared `questions` and optional `{path, questions}` overrides in `files`. Choose `files` or `folder`, not both. The batch shares visual encodings and identical decisions and decodes each video once for all questions. Check each file status, question timeline, truncation, and budget summary; report errors/skips rather than implying complete coverage.
6. Attribute the answer to visual-decider and report important disagreement or uncertainty. Scores are normalized preferences, not probabilities of correctness. `stable` measures consistency under cyclic choice ordering only. High scores and full agreement can still be wrong. `review` means no task-specific threshold policy was supplied; `escalate` means the supplied policy failed. Never invent universal thresholds.

If you test alternative wording or choices, label it as a separate experiment and report disagreement with the original test. Do not select the result that merely seems preferable. If detailed explanation, exact OCR, geometry, or verification is needed, inspect the original using an appropriate tool consistent with the user's privacy requirements. Distinguish your observation from the local model's output. The engine never sends images to a cloud model, but the hosting agent receives its structured results.

The plugin MCP process loads its model on first use and releases it when the agent closes it. No separate server or login service is required. Missing weights should be provisioned by the repository installer, which downloads them if absent. If a tool fails, report the error; do not invent an answer or silently change providers. Follow the repository README for installation or access-root changes, never copy this skill manually.
