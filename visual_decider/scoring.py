"""Pure scoring math. Scores are restricted preferences, not calibrated probabilities."""

import math


def logsumexp(values):
    values = list(values)
    if not values or any(math.isnan(x) or x == math.inf for x in values):
        raise ValueError("Expected nonempty logits without NaN/+infinity")
    m = max(values)
    return m if m == -math.inf else m + math.log(math.fsum(math.exp(x - m) for x in values))


def normalize(logits):
    logits = list(logits)
    z = logsumexp(logits)
    if not math.isfinite(z):
        raise ValueError("All candidates have impossible scores")
    return [math.exp(x - z) for x in logits]


def validate(question, choices):
    if not isinstance(question, str) or not question.strip() or len(question) > 4096:
        raise ValueError("Question must contain 1–4096 characters")
    if not isinstance(choices, (list, tuple)) or not 2 <= len(choices) <= 10:
        raise ValueError("Expected 2–10 choices")
    if any(not isinstance(x, str) or not x.strip() or len(x) > 512 for x in choices):
        raise ValueError("Choices must be nonempty strings of at most 512 characters")
    choices = [x.strip() for x in choices]
    if len(set(choices)) != len(choices):
        raise ValueError("Choices must be unique after trimming")
    return question.strip(), choices


def rotations(n):
    return [[(j + i) % n for j in range(n)] for i in range(n)]


def aggregate(raw, orders, combine="mean"):
    if not raw or len(raw) != len(orders):
        raise ValueError("Scores and mappings must align")
    n = len(raw[0])
    mapped = []
    for row, order in zip(raw, orders):
        if len(row) != n or sorted(order) != list(range(n)):
            raise ValueError("Invalid semantic option mapping")
        z = logsumexp(row)
        if not math.isfinite(z):
            raise ValueError("All candidates impossible")
        semantic = [0.0] * n
        for pos, original in enumerate(order):
            semantic[original] = row[pos] - z
        mapped.append(semantic)
    if combine == "mean":
        scores = [math.fsum(math.exp(row[i]) for row in mapped) / len(mapped) for i in range(n)]
    elif combine == "logmean":
        scores = normalize([math.fsum(row[i] for row in mapped) / len(mapped) for i in range(n)])
    else:
        raise ValueError("Unknown combination")
    winner = max(range(n), key=scores.__getitem__)
    agreement = sum(
        row[winner] == max(row) and sum(abs(x - max(row)) < 1e-12 for x in row) == 1
        for row in mapped
    ) / len(mapped)
    return scores, agreement


def continuation_ids(tokenizer, prompt, candidate):
    """Reject token-boundary merges; never guess a continuation's tokenization."""
    prefix = tokenizer.encode(prompt, add_special_tokens=False)
    full = tokenizer.encode(prompt + candidate, add_special_tokens=False)
    if full[: len(prefix)] != prefix or len(full) <= len(prefix):
        raise ValueError("Candidate changes the prompt token boundary")
    ids = full[len(prefix) :]
    if any(i in tokenizer.all_special_ids for i in ids):
        raise ValueError("Choices may not contain model control tokens")
    return ids


def label_ids(tokenizer, prompt, count):
    ids = [continuation_ids(tokenizer, prompt, chr(65 + i)) for i in range(count)]
    if any(len(x) != 1 for x in ids) or len({x[0] for x in ids}) != count:
        raise RuntimeError("Backend requires unique exact single-token labels")
    return [x[0] for x in ids]
