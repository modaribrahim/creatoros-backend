from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from celery import Celery

from app.core.config import settings


def _tls_redis_url(url: str) -> str:
    """Celery/kombu reject ``rediss://`` URLs without ``ssl_cert_reqs``.

    TLS-schemed provider URLs (Upstash, Redis Cloud) require the query
    parameter ``ssl_cert_reqs=CERT_REQUIRED``; otherwise the worker raises
    ``ValueError`` at startup and analysis jobs never run. Injected here so
    the same URL works everywhere else in the app unchanged.
    """
    if not (url or "").startswith("rediss://"):
        return url
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["ssl_cert_reqs"] = "CERT_REQUIRED"
    return urlunsplit(parts._replace(query=urlencode(params)))


_broker_url = _tls_redis_url(settings.redis_url)

celery_app = Celery(
    "creatoros",
    broker=_broker_url,
    backend=_broker_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Fault tolerance: with acks_late the worker only acks a task after it
    # finishes, so if the process dies mid-run the broker resends the task
    # (instead of it being "acked" and lost forever). reject_on_worker_lost
    # requeues work in flight when a worker is killed, so cold-starts/restarts
    # become a pause rather than a permanently stuck job.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 600},
)
