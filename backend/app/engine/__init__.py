# backend/app/engine/__init__.py
"""
Simulation engine: templates, simulator, observation model, solver, consistency engine, reveal sampler,
dataset generator. Import from the specific module (e.g. `app.engine.simulator`); this package file stays
empty on purpose, because eager re-exports here created an import cycle with `app.features`.
"""
