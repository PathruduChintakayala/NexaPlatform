from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("nexa_api", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(name="app.tasks.ping")
def ping_task() -> str:
    return "pong"
