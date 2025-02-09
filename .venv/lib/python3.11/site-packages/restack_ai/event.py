from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class AgentEvent:
    name: str
    input: Optional[Dict[str, Any]] = None


@dataclass
class SendAgentEvent:
    event: AgentEvent
    workflow: Optional[str] = None
