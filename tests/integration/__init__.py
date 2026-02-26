"""Integration tests for LlamaTrade.

These tests run against real PostgreSQL and Redis instances (via testcontainers)
rather than mocks. They verify actual database operations, tenant isolation,
and multi-service workflows.
"""
