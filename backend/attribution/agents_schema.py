"""
agents_schema.py

Loads backend/agents/schemas.py and re-exports SessionMetrics.

WHY BY FILE PATH RATHER THAN A NORMAL IMPORT
--------------------------------------------
backend/agents uses flat sibling imports (`from schemas import SessionMetrics`)
and is run from inside its own directory. Putting backend/agents on sys.path
so `import schemas` resolves would shadow this package's own schemas.py --
the same collision backend/cv and backend/calibration already hit. Loading the
file directly under a private module name avoids sys.path entirely.

WHY IMPORT IT AT ALL RATHER THAN REDECLARING THE DATACLASS
-----------------------------------------------------------
The brief says match backend/agents/schemas.py exactly and don't modify it.
Importing the real class makes that structurally true instead of true by
inspection: `isinstance(result, SessionMetrics)` holds for the agents' own
class, so orchestrator.run_pipeline() accepts our output directly, and a
future field added to SessionMetrics surfaces here as a TypeError at
construction rather than as a silently missing key.

If agents/schemas.py ever moves, this raises with a clear message rather than
falling back to a stale copy -- a stale copy is exactly the failure this file
exists to prevent.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

AGENTS_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "agents" / "schemas.py"
)

# Private name: must not collide with the real `schemas` module that
# backend/agents imports when it is run from its own directory.
_MODULE_NAME = "_gazelens_agents_schemas"


class AgentsSchemaUnavailable(ImportError):
    """backend/agents/schemas.py could not be loaded."""


def _load() -> ModuleType:
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached

    if not AGENTS_SCHEMA_PATH.exists():
        raise AgentsSchemaUnavailable(
            f"backend/agents/schemas.py not found at {AGENTS_SCHEMA_PATH}. "
            "attribution's whole purpose is to emit that module's "
            "SessionMetrics -- it cannot run without it."
        )

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, AGENTS_SCHEMA_PATH)
    if spec is None or spec.loader is None:
        raise AgentsSchemaUnavailable(f"could not load {AGENTS_SCHEMA_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_agents_schemas = _load()

# The contract. Re-exported so the rest of this package never has to know
# where it came from.
SessionMetrics = _agents_schemas.SessionMetrics

__all__ = ["SessionMetrics", "AGENTS_SCHEMA_PATH", "AgentsSchemaUnavailable"]
