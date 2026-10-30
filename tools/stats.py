import config

SUMMARY_KEYS = [
    "requisicoes", "falhas", "timeouts", "erros", "media_ms",
    "mediana_ms", "p95_ms", "p99_ms", "max_ms", "req_s",
]


def percentile(histogram, total, fraction):
    target = int(total * fraction)
    seen = 0
    for value in sorted(histogram, reverse=True):
        seen += histogram[value]
        if total - seen <= target:
            return value
    return 0


def merge(parts):
    if len(parts) == 1:
        return {key: parts[0][key] for key in SUMMARY_KEYS}
    histogram = {}
    errors = {}
    for part in parts:
        for value, count in part["response_times"].items():
            histogram[int(value)] = histogram.get(int(value), 0) + count
        for kind, count in part["erros"].items():
            errors[kind] = errors.get(kind, 0) + count
    total = sum(part["requisicoes"] for part in parts)
    longest = max(part["max_ms"] for part in parts)
    return {
        "requisicoes": total,
        "falhas": sum(part["falhas"] for part in parts),
        "timeouts": errors.get("timeout", 0),
        "erros": errors,
        "media_ms": sum(part["total_response_time"] for part in parts) / total if total else 0,
        "mediana_ms": min(percentile(histogram, total, 0.5), longest),
        "p95_ms": percentile(histogram, total, 0.95),
        "p99_ms": percentile(histogram, total, 0.99),
        "max_ms": longest,
        "req_s": sum(part["req_s"] for part in parts),
    }


def failure_rate(data, users):
    expected = users * config.CALLS_PER_USER
    succeeded = data["requisicoes"] - data["falhas"]
    return (expected - succeeded) / expected * 100


def approved(data, users):
    return failure_rate(data, users) <= config.FAIL_LIMIT_PCT