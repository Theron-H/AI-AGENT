from __future__ import annotations

import os

from celery import Celery

from .emailer import send_email

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_BACKEND_URL = os.getenv("CELERY_BACKEND_URL", "redis://redis:6379/1")

celery_app = Celery("ai_data_assistant", broker=CELERY_BROKER_URL, backend=CELERY_BACKEND_URL)


@celery_app.task
def send_report_email(subject: str, body: str) -> None:
    send_email(subject, body)
