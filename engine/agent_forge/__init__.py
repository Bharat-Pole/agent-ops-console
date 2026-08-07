"""agent_forge — deterministic spec→code generator.

Reads a Brightspeed agent-ops-console canonical AgentRecord export and emits a
runnable LangGraph Python project. The mirror of `agent_onboard` (code→spec):
no LLM is used to generate code — templates only. The *generated* agent uses the
LLM (Gemini) at runtime.
"""

__version__ = "0.1.0"

from .loader import load_agent  # noqa: E402
from .dispatch import Topology, dispatch  # noqa: E402
from .generate import generate  # noqa: E402

__all__ = ["load_agent", "dispatch", "Topology", "generate", "__version__"]
