"""
AI Engineer OS Integration Adapter
Main integration point for AI Engineer OS with Genesi.
"""

import asyncio
from typing import Dict, Any, Optional

from .feature_flags import ai_engineer_os_flags, FeatureFlag
from .integration_config import get_integration_config
from .proactor_observer import proactor_observer, observe_proactor_handle


class AIEngineerOSAdapter:
    """Main adapter for AI Engineer OS integration."""
    
    def __init__(self):
        self.config = get_integration_config()
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize AI Engineer OS integration."""
        try:
            # Validate configuration
            issues = self.config.validate()
            if issues:
                print(f"AI Engineer OS configuration validation failed: {issues}")
                return False
            
            # Check if AI Engineer OS is enabled
            if not ai_engineer_os_flags.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED):
                print("AI Engineer OS is disabled")
                return False
            
            self._initialized = True
            print("AI Engineer OS integration initialized successfully")
            return True
            
        except Exception as e:
            print(f"Failed to initialize AI Engineer OS: {str(e)}")
            return False
    
    def integrate_proactor(self, proactor_instance: Any) -> Any:
        """
        Integrate with proactor instance.
        
        This method wraps the proactor.handle() method with observation
        without modifying the original behavior.
        """
        if not self._initialized:
            print("AI Engineer OS not initialized, skipping integration")
            return proactor_instance
        
        if not ai_engineer_os_flags.is_enabled(FeatureFlag.SHADOW_OBSERVATION):
            print("Shadow observation disabled, skipping proactor integration")
            return proactor_instance
        
        # Wrap proactor.handle() with observation
        if hasattr(proactor_instance, 'handle'):
            original_handle = proactor_instance.handle
            proactor_instance.handle = observe_proactor_handle(original_handle)
            
            print("Proactor.handle() wrapped with shadow observation")
        else:
            print("Warning: Proactor instance does not have handle() method")
        
        return proactor_instance
    
    async def shutdown(self) -> None:
        """Shutdown AI Engineer OS integration."""
        try:
            if self._initialized:
                self._initialized = False
                print("AI Engineer OS integration shutdown successfully")
        
        except Exception as e:
            print(f"Failed to shutdown AI Engineer OS: {str(e)}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get integration status."""
        return {
            "initialized": self._initialized,
            "enabled": ai_engineer_os_flags.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED),
            "features": {
                "shadow_observation": ai_engineer_os_flags.is_enabled(FeatureFlag.SHADOW_OBSERVATION),
                "reasoning_pipeline": ai_engineer_os_flags.is_enabled(FeatureFlag.REASONING_PIPELINE),
                "memory_integration": ai_engineer_os_flags.is_enabled(FeatureFlag.MEMORY_INTEGRATION),
                "logging": ai_engineer_os_flags.is_enabled(FeatureFlag.LOGGING_ENABLED)
            },
            "config": {
                "shadow_mode_only": self.config.shadow_mode_only,
                "read_only_mode": self.config.read_only_mode,
                "error_isolation": self.config.error_isolation
            },
            "observation_stats": proactor_observer.get_observation_stats()
        }


# Global adapter instance
ai_engineer_os_adapter = AIEngineerOSAdapter()


async def initialize_ai_engineer_os() -> bool:
    """Initialize AI Engineer OS integration."""
    return await ai_engineer_os_adapter.initialize()


def integrate_with_proactor(proactor_instance: Any) -> Any:
    """Integrate AI Engineer OS with proactor instance."""
    return ai_engineer_os_adapter.integrate_proactor(proactor_instance)


async def shutdown_ai_engineer_os() -> None:
    """Shutdown AI Engineer OS integration."""
    await ai_engineer_os_adapter.shutdown()


def get_ai_engineer_os_status() -> Dict[str, Any]:
    """Get AI Engineer OS status."""
    return ai_engineer_os_adapter.get_status()
