"""
AI Engineer OS - Agent Interface
Base interface for all autonomous agents.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime


class IAgent(ABC):
    """
    Base interface for all AI agents in the system.
    
    This interface defines the contract that all agents must implement
    to participate in the multi-agent orchestration system.
    """
    
    @abstractmethod
    def get_id(self) -> str:
        """Return unique agent identifier."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return human-readable agent name."""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of agent capabilities."""
        pass
    
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize agent with configuration."""
        pass
    
    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process input data and return results."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shutdown agent."""
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return current agent status."""
        pass
    
    @abstractmethod
    def can_handle(self, task_type: str) -> bool:
        """Check if agent can handle specific task type."""
        pass


class AgentCapability:
    """Agent capability definition."""
    
    def __init__(self, name: str, description: str, priority: int = 0):
        self.name = name
        self.description = description
        self.priority = priority
        self.created_at = datetime.utcnow()


class AgentStatus:
    """Agent status enumeration."""
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class AgentMessage:
    """Standard message format for inter-agent communication."""
    
    def __init__(self, sender: str, receiver: str, message_type: str, payload: Dict[str, Any]):
        self.sender = sender
        self.receiver = receiver
        self.message_type = message_type
        self.payload = payload
        self.timestamp = datetime.utcnow()
        self.id = f"{sender}_{receiver}_{int(self.timestamp.timestamp())}"
