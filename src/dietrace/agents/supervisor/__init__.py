"""Autonomous supervisor: per-meal decisions + the champion-challenger retune.

The supervisor observes logged meals and, on a cadence, decides whether to bank
feedback, add a Phoenix dataset point, or retune — informed by Phoenix data read
over MCP, with the deterministic gate (``dietrace.web.gate``) making the actual
ship/reject call. See docs/agent-supervisor-design.md.
"""
