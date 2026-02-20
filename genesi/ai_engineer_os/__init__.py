"""
AI Engineer OS - Integration Layer for Genesi
Shadow mode integration with zero runtime impact.
"""

__version__ = "1.0.0"
__author__ = "AI Engineer OS Team"

from .integration_adapter import AIEngineerOSAdapter
from .feature_flags import AIEngineerOSFlags
from .integration_config import IntegrationConfig

__all__ = [
    "AIEngineerOSAdapter",
    "AIEngineerOSFlags", 
    "IntegrationConfig"
]
