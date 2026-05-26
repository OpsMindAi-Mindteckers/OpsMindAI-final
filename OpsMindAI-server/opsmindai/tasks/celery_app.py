"""
opsmindai/tasks/celery_app.py

Celery application factory for OpsMindAI agents.

Start all queues with one worker (recommended):
    celery -A opsmindai.tasks.celery_app worker --loglevel=info --concurrency=8 -n main@%h

Or per-queue workers:
    celery -A opsmindai.tasks.celery_app worker --loglevel=info -Q testing  -n test@%h
    celery -A opsmindai.tasks.celery_app worker --loglevel=info -Q pipeline -n pipeline@%h
    celery -A opsmindai.tasks.celery_app worker --loglevel=info -Q sre      -n sre@%h
    celery -A opsmindai.tasks.celery_app worker --loglevel=info -Q refactor -n refactor@%h
"""

import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "redis://default:UlZV4uuiRwNdx3uEAJJBTVqJN3e3CG8j@redis-17963.c261.us-east-1-4.ec2.cloud.redislabs.com:17963/0")
BROKER_URL = os.environ.get("CELERY_BROKER_URL") or REDIS_URL
RESULT_URL = os.environ.get("CELERY_RESULT_BACKEND") or REDIS_URL

celery_app = Celery(
    "opsmindai",
    broker=BROKER_URL,
    backend=RESULT_URL,
    include=[
        "opsmindai.tasks.refactor_tasks",
        "opsmindai.tasks.sre_tasks",
        "opsmindai.tasks.testing_tasks",
        "opsmindai.tasks.pipeline_tasks",
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
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Default queue
    task_default_queue="default",

    # Per-agent queues
    task_queues={
        "refactor": {"exchange": "refactor", "routing_key": "refactor"},
        "sre":      {"exchange": "sre",      "routing_key": "sre"},
        "testing":  {"exchange": "testing",  "routing_key": "testing"},
        "pipeline": {"exchange": "pipeline", "routing_key": "pipeline"},
        "default":  {"exchange": "default",  "routing_key": "default"},
    },

    # Auto-route tasks to correct queues
    task_routes={
        "refactor.*":  {"queue": "refactor"},
        "sre.*":       {"queue": "sre"},
        "testing.*":   {"queue": "testing"},
        "pipeline.*":  {"queue": "pipeline"},
    },

    # Priority
    task_queue_max_priority=10,
    task_default_priority=5,

    # Time limits
    task_soft_time_limit=240,
    task_time_limit=260,
)
