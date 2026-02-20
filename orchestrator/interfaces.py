"""
AI Engineer OS - Orchestrator Interface
Multi-agent coordination and lifecycle management.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime


class IOrchestrator(ABC):
    """
    Interface for multi-agent orchestration.
    
    This interface defines the contract for orchestrators that can
    coordinate multiple agents and manage their lifecycle.
    """
    
    @abstractmethod
    async def register_agent(self, agent_config: Dict[str, Any]) -> str:
        """Register a new agent with the orchestrator."""
        pass
    
    @abstractmethod
    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the orchestrator."""
        pass
    
    @abstractmethod
    async def assign_task(self, task: Dict[str, Any], agent_id: Optional[str] = None) -> str:
        """Assign a task to an appropriate agent."""
        pass
    
    @abstractmethod
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a specific task."""
        pass
    
    @abstractmethod
    async def coordinate_agents(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Coordinate multiple agents in a workflow."""
        pass
    
    @abstractmethod
    def get_available_agents(self) -> List[Dict[str, Any]]:
        """Return list of available agents."""
        pass
    
    @abstractmethod
    async def monitor_agents(self) -> Dict[str, Any]:
        """Monitor all registered agents."""
        pass
    
    @abstractmethod
    async def handle_agent_failure(self, agent_id: str, error: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent failure and recovery."""
        pass


class Task:
    """Task definition for agent execution."""
    
    def __init__(self, task_type: str, payload: Dict[str, Any], priority: int = 0, deadline: Optional[datetime] = None):
        self.task_type = task_type
        self.payload = payload
        self.priority = priority
        self.deadline = deadline
        self.created_at = datetime.utcnow()
        self.status = "pending"
        self.assigned_agent = None
        self.id = f"task_{int(self.created_at.timestamp())}"


class Workflow:
    """Workflow definition for multi-agent coordination."""
    
    def __init__(self, name: str, steps: List[Dict[str, Any]], dependencies: Dict[str, List[str]]):
        self.name = name
        self.steps = steps
        self.dependencies = dependencies
        self.created_at = datetime.utcnow()
        self.status = "pending"
        self.id = f"workflow_{int(self.created_at.timestamp())}"


class AgentRegistration:
    """Agent registration information."""
    
    def __init__(self, agent_id: str, agent_type: str, capabilities: List[str], config: Dict[str, Any]):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capabilities = capabilities
        self.config = config
        self.registered_at = datetime.utcnow()
        self.status = "active"
        self.last_heartbeat = datetime.utcnow()
