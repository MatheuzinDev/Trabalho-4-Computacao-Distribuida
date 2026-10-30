import json
import os
import random
import uuid

from locust import FastHttpUser, constant, events, task
from locust.exception import StopUser

from urls import URLS

CACHE = os.environ.get("CACHE", "on")
TOTAL_USERS = int(os.environ.get("USERS", "1"))
TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "10"))
finished = 0


@events.quitting.add_listener
def save_stats(environment, **kwargs):
    path = os.environ.get("STATS_FILE")
    if not path:
        return
    total = environment.stats.total
    errors = {}
    for error in environment.stats.errors.values():
        kind = str(error.error).split(" ", 1)[0]
        errors[kind] = errors.get(kind, 0) + error.occurrences
    data = {
        "requisicoes": total.num_requests,
        "falhas": total.num_failures,
        "timeouts": errors.get("timeout", 0),
        "erros": errors,
        "media_ms": total.avg_response_time,
        "mediana_ms": total.median_response_time,
        "p95_ms": total.get_response_time_percentile(0.95),
        "p99_ms": total.get_response_time_percentile(0.99),
        "max_ms": total.max_response_time,
        "req_s": total.total_rps,
        "total_response_time": total.total_response_time,
        "response_times": dict(total.response_times),
    }
    with open(path, "w") as handle:
        json.dump(data, handle)


def error_kind(response):
    error = str(getattr(response, "error", "") or "").lower()
    return "timeout" if "time" in error else "conexao"


class LinkExtractorUser(FastHttpUser):
    wait_time = constant(0)
    connection_timeout = TIMEOUT
    network_timeout = TIMEOUT

    @task
    def sequence(self):
        global finished
        for url in random.sample(URLS, len(URLS)):
            target = url if CACHE == "on" else f"{url}?nc={uuid.uuid4().hex}"
            with self.client.get(f"/api/{target}", name="/api/[url]", catch_response=True) as response:
                if response.status_code == 0:
                    response.failure(f"{error_kind(response)} {url}")
                elif response.status_code != 200:
                    response.failure(f"http{response.status_code} {url}")
                elif response.content[:1] == b"[" and len(response.content) > 4:
                    response.success()
                else:
                    response.failure(f"vazia {url}")
        finished += 1
        if finished >= TOTAL_USERS:
            self.environment.runner.quit()
        raise StopUser()