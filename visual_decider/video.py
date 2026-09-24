"""Bounded local sampling with one decode stream and shared multi-question inference."""

import math

import av
import numpy as np

from .image import MAX_PIXELS, local_path


def aggregate_events(samples, end):
    events = []
    for i, row in enumerate(samples):
        start = row["time_s"]
        stop = samples[i + 1]["time_s"] if i + 1 < len(samples) else end
        if stop < start:
            raise ValueError("Sample timestamps must increase")
        decision = row["decision"]
        if (
            events
            and events[-1]["choice"] == decision["winner"]
            and events[-1]["recommended_action"] == decision["recommended_action"]
        ):
            events[-1]["end"] = stop
            events[-1]["peak_score"] = max(events[-1]["peak_score"], decision["score"])
            events[-1]["samples"] += 1
        else:
            events.append(
                dict(
                    start=start,
                    end=stop,
                    choice=decision["winner"],
                    peak_score=decision["score"],
                    samples=1,
                    recommended_action=decision["recommended_action"],
                )
            )
    return events


def _deny_external_io(*args):
    raise ValueError("Videos may not reference external resources")


def _sample_frames(container, stream, origin, duration, interval, maximum):
    """Decode once, holding only two frames, and select the frame at/before each time."""
    previous, index, previous_time = None, 0, -math.inf
    for frame in container.decode(stream):
        if frame.time is None:
            raise ValueError("Video frame lacks a presentation timestamp")
        if frame.width * frame.height > MAX_PIXELS:
            raise ValueError("Video frame exceeds pixel limit")
        current_time = float(frame.time) - origin
        if not math.isfinite(current_time) or current_time < previous_time:
            raise ValueError("Video presentation timestamps must increase")
        previous_time = current_time
        while index < maximum and index * interval < min(current_time - 1e-8, duration):
            yield index * interval, previous if previous is not None else frame
            index += 1
        if index >= maximum or index * interval >= duration:
            return
        previous = frame
    if previous is None:
        raise ValueError("Video decoding failed: no frames")
    # Metadata must not create a long imaginary tail after truncated/corrupt decoding.
    rate = float(stream.average_rate or 0)
    tolerance = max(0.1, 2 / rate) if math.isfinite(rate) and rate > 0 else 0.1
    if duration - previous_time > tolerance:
        raise ValueError("Video ended before its declared duration")
    while index < maximum and index * interval < duration:
        yield index * interval, previous
        index += 1


def validate_video_options(sample_interval, max_frames, suppress_duplicates, similarity_threshold):
    if (
        isinstance(sample_interval, bool)
        or not isinstance(sample_interval, (int, float))
        or not math.isfinite(sample_interval)
        or sample_interval <= 0
    ):
        raise ValueError("Sample interval must be finite and positive")
    if (
        not isinstance(max_frames, int)
        or isinstance(max_frames, bool)
        or not 1 <= max_frames <= 1000
    ):
        raise ValueError("max_frames must be 1–1000")
    if (
        isinstance(similarity_threshold, bool)
        or not isinstance(similarity_threshold, (int, float))
        or not math.isfinite(similarity_threshold)
        or not 0 <= similarity_threshold <= 1
    ):
        raise ValueError("Similarity threshold must be 0–1")
    if not isinstance(suppress_duplicates, bool):
        raise ValueError("suppress_duplicates must be a boolean")


def analyze_video_questions(
    analyzer,
    path,
    questions,
    sample_interval=1.0,
    *,
    max_frames=300,
    suppress_duplicates=False,
    similarity_threshold=0.0,
    scorer=None,
    method="label_permute",
    policy=None,
):
    from .batch import BatchScorer, check_questions

    questions = check_questions(questions)
    validate_video_options(sample_interval, max_frames, suppress_duplicates, similarity_threshold)
    scorer = scorer or BatchScorer(analyzer, method, policy)
    path = local_path(path, max_bytes=512 * 1024 * 1024, roots=analyzer.roots)
    if path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}:
        raise ValueError("Unsupported video extension")
    try:
        with (
            path.open("rb") as source,
            av.open(
                source,
                mode="r",
                io_open=_deny_external_io,
                options={"protocol_whitelist": "file", "format_whitelist": "mov,matroska,webm,avi"},
            ) as container,
        ):
            if not container.streams.video:
                raise ValueError("Video contains no video stream")
            stream = container.streams.video[0]
            if stream.codec_context.width * stream.codec_context.height > MAX_PIXELS:
                raise ValueError("Video frame exceeds pixel limit")
            duration = (
                float(stream.duration * stream.time_base)
                if stream.duration is not None
                else float(container.duration or 0) / av.time_base
            )
            if not math.isfinite(duration) or duration <= 0 or not stream.time_base:
                raise ValueError("Video has no reliable duration metadata")
            origin = float((stream.start_time or 0) * stream.time_base)
            samples, last_small, last_decisions, classified = [], None, None, 0
            for t, frame in _sample_frames(
                container, stream, origin, duration, sample_interval, max_frames
            ):
                rgb = frame.to_image().convert("RGB")
                small = (
                    np.asarray(rgb.resize((64, 64)), dtype=np.float32) / 255
                    if suppress_duplicates
                    else None
                )
                reused = (
                    suppress_duplicates
                    and last_small is not None
                    and float(np.abs(small - last_small).mean()) <= similarity_threshold
                )
                if not reused:
                    last_decisions = scorer.inspect(rgb, questions)
                    last_small = small
                    classified += 1
                samples.append(
                    dict(
                        time_s=t,
                        frame_time_s=float(frame.time) - origin,
                        decisions=last_decisions,
                        reused=bool(reused),
                    )
                )
            end = min(duration, len(samples) * sample_interval)
            events = [
                dict(
                    question=item["question"],
                    choices=item["choices"],
                    events=aggregate_events(
                        [
                            {"time_s": row["time_s"], "decision": row["decisions"][i]}
                            for row in samples
                        ],
                        end,
                    ),
                )
                for i, item in enumerate(questions)
            ]
            return dict(
                duration=duration,
                analyzed_until=end,
                truncated=end < duration,
                sample_interval=sample_interval,
                frames_classified=classified,
                samples=samples,
                questions=events,
                temporal_resolution_note="Sample-and-hold estimates, not observed event durations. "
                "frame_time_s records the decoded frame; transitions between samples can be missed.",
            )
    except av.FFmpegError as exc:
        raise ValueError(f"Unsupported or corrupt video: {exc}") from exc


def analyze_video(analyzer, path, question, choices, sample_interval=1.0, **kwargs):
    """Compatibility shape for one question; execution uses the multi-question pipeline."""
    result = analyze_video_questions(
        analyzer, path, [{"question": question, "choices": choices}], sample_interval, **kwargs
    )
    result["events"] = result.pop("questions")[0]["events"]
    for sample in result["samples"]:
        sample["decision"] = sample.pop("decisions")[0]
    return result
