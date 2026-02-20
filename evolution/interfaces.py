"""
AI Engineer OS - Evolution Engine Interface
Code generation, architecture evolution, and patch management.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime


class IEvolutionEngine(ABC):
    """
    Interface for system evolution and self-improvement.
    
    This interface defines the contract for evolution engines that can
    generate code, modify architecture, and manage system patches.
    """
    
    @abstractmethod
    async def generate_code(self, specification: Dict[str, Any]) -> Dict[str, Any]:
        """Generate code based on specification."""
        pass
    
    @abstractmethod
    async def analyze_architecture(self, system_state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze current system architecture."""
        pass
    
    @abstractmethod
    async def propose_evolution(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Propose architectural improvements."""
        pass
    
    @abstractmethod
    async def create_patch(self, change_request: Dict[str, Any]) -> Dict[str, Any]:
        """Create a system patch."""
        pass
    
    @abstractmethod
    async def validate_patch(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Validate patch safety and compatibility."""
        pass
    
    @abstractmethod
    async def apply_patch(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Apply validated patch to system."""
        pass
    
    @abstractmethod
    async def rollback_patch(self, patch_id: str) -> Dict[str, Any]:
        """Rollback a previously applied patch."""
        pass
    
    @abstractmethod
    def get_evolution_history(self) -> List[Dict[str, Any]]:
        """Return history of applied evolutions."""
        pass


class CodeSpecification:
    """Code generation specification."""
    
    def __init__(self, description: str, requirements: List[str], constraints: List[str]):
        self.description = description
        self.requirements = requirements
        self.constraints = constraints
        self.created_at = datetime.utcnow()


class Patch:
    """System patch definition."""
    
    def __init__(self, patch_id: str, description: str, changes: List[Dict[str, Any]], dependencies: List[str]):
        self.patch_id = patch_id
        self.description = description
        self.changes = changes
        self.dependencies = dependencies
        self.created_at = datetime.utcnow()
        self.status = "pending"
        self.applied_at = None


class ArchitectureAnalysis:
    """Architecture analysis result."""
    
    def __init__(self, components: List[Dict[str, Any]], relationships: List[Dict[str, Any]], issues: List[str]):
        self.components = components
        self.relationships = relationships
        self.issues = issues
        self.timestamp = datetime.utcnow()
        self.id = f"arch_analysis_{int(self.timestamp.timestamp())}"
