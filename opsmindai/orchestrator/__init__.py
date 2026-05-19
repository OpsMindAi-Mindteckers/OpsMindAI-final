"""
opsmindai/orchestrator

Task routing, event normalisation, and Celery agent dispatch.

Modules:
  event_handler    — normalise raw webhook payloads from all sources
  task_router      — map events to agent tasks with priority
  agent_dispatcher — send tasks to Celery queues
"""
