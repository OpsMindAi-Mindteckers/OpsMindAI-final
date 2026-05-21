"""
opsmindai/core/celery_app.py

Celery application factory for OpsMindAI agents.

Workers (one per agent queue, scaled independently):
    celery -A opsmindai.core.celery_app worker --loglevel=info -Q refactor -n refactor@%h
    celery -A opsmindai.core.celery_app worker --loglevel=info -Q sre      -n sre@%h
    celery -A opsmindai.core.celery_app worker --loglevel=info -Q testing  -n test@%h

Beat (periodic cleanup tasks):
    celery -A opsmindai.core.celery_app beat --loglevel=info
"""

import os

from celery import Celery

REDIS_URL  = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
RESULT_URL = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

celery_app = Celery(
    "opsmindai",
    broker=REDIS_URL,
    backend=RESULT_URL,
    include=[
        "opsmindai.tasks.refactor_tasks",
        "opsmindai.tasks.sre_tasks",
        # "opsmindai.tasks.testing_tasks",   # add when Phase P4 lands
    ],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Time
    timezone="UTC",
    enable_utc=True,

    # Result TTL (24h)
    result_expires=86_400,

    # Worker behaviour
    worker_prefetch_multiplier=1,        # one task at a time per worker process
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Default queue
    task_default_queue="default",

    # Per-agent queues
    task_queues={
        "refactor": {"exchange": "refactor", "routing_key": "refactor"},
        "sre":      {"exchange": "sre",      "routing_key": "sre"},
        "testing":  {"exchange": "testing",  "routing_key": "testing"},
        "default":  {"exchange": "default",  "routing_key": "default"},
    },

    # Priority support (Redis broker supports this natively)
    task_queue_max_priority=10,
    task_default_priority=5,

    # Time limits (seconds) — soft triggers SoftTimeLimitExceeded, hard = SIGKILL
    task_soft_time_limit=600,            # 10 min
    task_time_limit=660,                 # 11 min
)