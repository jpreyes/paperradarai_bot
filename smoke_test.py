# Simple import test to ensure package wiring is OK
import importlib
mods = [
    "paperradar.config",
    "paperradar.storage.paths",
    "paperradar.core.filters",
    "paperradar.core.ranking",
    "paperradar.core.llm",
    "paperradar.fetchers.merge",
    "paperradar.services.pipeline",
    "paperradar.bot.main",
    "paperradar.web.api",
]
for m in mods:
    importlib.import_module(m)
print("OK: imports loaded.")
