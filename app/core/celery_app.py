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
)
