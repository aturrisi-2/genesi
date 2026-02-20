"""
AI Engineer OS - Meta-Reasoning Interface
Self-reflection, strategy evolution, and performance monitoring.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime


class IMetaReasoner(ABC):
    """
    Interface for meta-reasoning and self-reflection.
    
    This interface defines the contract for meta-reasoning components
    that can analyze system performance and suggest improvements.
    """
    
    @abstractmethod
    async def analyze_performance(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze system performance metrics."""
        pass
    
    @abstractmethod
    async def reflect_on_decision(self, decision_context: Dict[str, Any]) -> Dict[str, Any]:
        """Reflect on a past decision to extract insights."""
        pass
    
    @abstractmethod
    async def suggest_improvements(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Suggest system improvements based on analysis."""
        pass
    
    @abstractmethod
    async def evaluate_strategy(self, strategy: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a strategy's effectiveness in given context."""
        pass
    
    @abstractmethod
    def get_learning_patterns(self) -> Dict[str, Any]:
        """Return discovered learning patterns."""
        pass
    
    @abstractmethod
    async def update_model(self, feedback: Dict[str, Any]) -> bool:
        """Update meta-reasoning model with feedback."""
        pass


class PerformanceMetric:
    """Performance metric definition."""
    
    def __init__(self, name: str, value: float, unit: str, context: Dict[str, Any]):
        self.name = name
        self.value = value
        self.unit = unit
        self.context = context
        self.timestamp = datetime.utcnow()


class Reflection:
    """System reflection result."""
    
    def __init__(self, decision_id: str, insights: List[str], confidence: float, recommendations: List[str]):
        self.decision_id = decision_id
        self.insights = insights
        self.confidence = confidence
        self.recommendations = recommendations
        self.timestamp = datetime.utcnow()


class Strategy:
    """Strategy definition."""
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], success_rate: float = 0.0):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.success_rate = success_rate
        self.created_at = datetime.utcnow()
        self.last_updated = datetime.utcnow()
        self.usage_count = 0
