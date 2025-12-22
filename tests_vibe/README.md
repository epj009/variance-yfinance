# Vibe Test Suite

This suite targets "AI vibe coding" failure modes: silent fallbacks, brittle parsing,
logic precedence drift, and fragile assumptions about missing data. Tests are
offline and deterministic by default.

Run:
  ./venv/bin/python3 -m pytest -q tests_vibe
