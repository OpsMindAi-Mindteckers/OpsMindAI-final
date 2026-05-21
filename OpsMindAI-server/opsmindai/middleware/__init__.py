"""
opsmindai/middleware

Request-level middleware stack.

  auth          — Bearer / API-key token presence check (SRS §5.3)
  rate_limiter  — Redis token-bucket 100 req/min per key (SRS FR-06)
  logging       — Structured JSON request log with X-Request-ID (SRS FR-04)
"""
