import warnings
warnings.filterwarnings("ignore", message=".*Event loop is closed.*", category=RuntimeWarning)


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
        "opsmindai.tasks.testing_tasks",
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
    task_soft_time_limit=240,            # 10 min
    task_time_limit=240,                 # 11 min
)


# ── Suppress harmless "Event loop is closed" errors during worker shutdown ────
# When Celery workers run async code, background cleanup tasks may fail if the
# event loop closes before they complete (common in multiprocessing context).
# This is harmless but produces noisy error logs. Install handlers to suppress.
import asyncio
import logging

logger = logging.getLogger(__name__)

# Filter RuntimeError warnings about event loop


# Install custom exception handler for background tasks
_original_exception_handler = None


def _suppress_event_loop_closed_handler(loop, context):
    """Suppress 'Event loop is closed' errors from httpx/anyio cleanup in tasks."""
    exc = context.get("exception")
    msg = context.get("message", "")
    
    # Check if this is the harmless "Event loop is closed" error
    if isinstance(exc, RuntimeError) and "Event loop is closed" in str(exc):
        logger.debug("Suppressed: Event loop is closed in background task")
        return
    if "Event loop is closed" in str(msg):
        logger.debug("Suppressed: Event loop is closed (%s)", msg)
        return
    
    # For real errors, use original handler if available
    if _original_exception_handler:
        _original_exception_handler(loop, context)
    else:
        logger.error("Unhandled error in callback: %s", context)


def _install_asyncio_handler():
    """Install our handler to suppress harmless cleanup errors."""
    try:
        global _original_exception_handler
        if hasattr(asyncio, 'get_exception_handler'):
            _original_exception_handler = asyncio.get_exception_handler()
    except Exception:
        pass
    
    try:
        if hasattr(asyncio, 'set_exception_handler'):
            asyncio.set_exception_handler(_suppress_event_loop_closed_handler)
            logger.debug("Installed asyncio exception handler for cleanup errors")
    except Exception as e:
        logger.debug("Could not install asyncio handler: %s", e)


_install_asyncio_handler()