"""
AI Engineer OS - Research Engine Interface
External research integration and knowledge synthesis.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime


class IResearchEngine(ABC):
    """
    Interface for external research integration.
    
    This interface defines the contract for research engines that can
    fetch, process, and synthesize external knowledge sources.
    """
    
    @abstractmethod
    async def search(self, query: str, sources: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search for information across configured sources."""
        pass
    
    @abstractmethod
    async def fetch_content(self, source_id: str, content_id: str) -> Dict[str, Any]:
        """Fetch specific content from a source."""
        pass
    
    @abstractmethod
    async def synthesize(self, query: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synthesize research results into coherent knowledge."""
        pass
    
    @abstractmethod
    def get_available_sources(self) -> List[Dict[str, Any]]:
        """Return list of available research sources."""
        pass
    
    @abstractmethod
    async def validate_source(self, source_id: str) -> bool:
        """Validate that a research source is accessible."""
        pass


class ResearchSource:
    """Research source configuration."""
    
    def __init__(self, source_id: str, name: str, source_type: str, config: Dict[str, Any]):
        self.source_id = source_id
        self.name = name
        self.source_type = source_type
        self.config = config
        self.created_at = datetime.utcnow()
        self.last_validated = None
        self.is_active = True


class ResearchResult:
    """Standard research result format."""
    
    def __init__(self, source_id: str, content: str, metadata: Dict[str, Any], confidence: float = 0.0):
        self.source_id = source_id
        self.content = content
        self.metadata = metadata
        self.confidence = confidence
        self.timestamp = datetime.utcnow()
        self.id = f"research_{source_id}_{int(self.timestamp.timestamp())}"


class ResearchQuery:
    """Research query definition."""
    
    def __init__(self, query: str, query_type: str = "search", filters: Optional[Dict[str, Any]] = None):
        self.query = query
        self.query_type = query_type
        self.filters = filters or {}
        self.timestamp = datetime.utcnow()
        self.id = f"query_{int(self.timestamp.timestamp())}"
