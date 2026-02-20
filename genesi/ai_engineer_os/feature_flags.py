"""
AI Engineer OS Feature Flags
All features are DISABLED by default for safety.
"""

import os
from typing import Dict, Any, Optional
from enum import Enum


class FeatureFlag(Enum):
    """AI Engineer OS feature flags."""
    
    # Master switch
    AI_ENGINEER_OS_ENABLED = "AI_ENGINEER_OS_ENABLED"
    
    # Component flags
    SHADOW_OBSERVATION = "AI_OS_SHADOW_OBSERVATION"
    REASONING_PIPELINE = "AI_OS_REASONING_PIPELINE"
    SUGGESTION_GENERATION = "AI_OS_SUGGESTION_GENERATION"
    MEMORY_INTEGRATION = "AI_OS_MEMORY_INTEGRATION"
    LOGGING_ENABLED = "AI_OS_LOGGING_ENABLED"
    
    # Safety flags
    READ_ONLY_MODE = "AI_OS_READ_ONLY_MODE"
    NO_RUNTIME_MODIFICATION = "AI_OS_NO_RUNTIME_MODIFICATION"
    ERROR_ISOLATION = "AI_OS_ERROR_ISOLATION"


class AIEngineerOSFlags:
    """Feature flags manager for AI Engineer OS."""
    
    def __init__(self):
        self._flags = self._load_default_flags()
        self._load_environment_flags()
        self._validate_safety()
    
    def _load_default_flags(self) -> Dict[str, bool]:
        """Load default flags (all disabled)."""
        return {flag.value: False for flag in FeatureFlag}
    
    def _load_environment_flags(self) -> None:
        """Load flags from environment variables."""
        for flag in FeatureFlag:
            env_value = os.environ.get(flag.value, "").lower()
            if env_value in ("true", "1", "yes", "on"):
                self._flags[flag.value] = True
            elif env_value in ("false", "0", "no", "off"):
                self._flags[flag.value] = False
    
    def _validate_safety(self) -> None:
        """Validate safety constraints."""
        # If master switch is disabled, all other flags must be disabled
        if not self.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED):
            for flag in FeatureFlag:
                if flag != FeatureFlag.AI_ENGINEER_OS_ENABLED:
                    self._flags[flag.value] = False
        
        # Enforce read-only mode
        if self.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED):
            self._flags[FeatureFlag.READ_ONLY_MODE.value] = True
            self._flags[FeatureFlag.NO_RUNTIME_MODIFICATION.value] = True
            self._flags[FeatureFlag.ERROR_ISOLATION.value] = True
    
    def is_enabled(self, flag: FeatureFlag) -> bool:
        """Check if a feature flag is enabled."""
        return self._flags.get(flag.value, False)
    
    def enable_feature(self, flag: FeatureFlag) -> None:
        """Enable a feature flag."""
        if flag == FeatureFlag.AI_ENGINEER_OS_ENABLED:
            self._flags[flag.value] = True
            # Enable safety flags automatically
            self._flags[FeatureFlag.READ_ONLY_MODE.value] = True
            self._flags[FeatureFlag.NO_RUNTIME_MODIFICATION.value] = True
            self._flags[FeatureFlag.ERROR_ISOLATION.value] = True
        else:
            # Can only enable if master switch is enabled
            if self.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED):
                self._flags[flag.value] = True
    
    def disable_feature(self, flag: FeatureFlag) -> None:
        """Disable a feature flag."""
        self._flags[flag.value] = False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current feature flag status."""
        return {
            "master_enabled": self.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED),
            "flags": {flag.value: enabled for flag, enabled in self._flags.items()},
            "safety_mode": self.is_enabled(FeatureFlag.READ_ONLY_MODE)
        }


# Global feature flags instance
ai_engineer_os_flags = AIEngineerOSFlags()


def is_ai_engineer_os_enabled() -> bool:
    """Check if AI Engineer OS is enabled."""
    return ai_engineer_os_flags.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED)


def is_shadow_observation_enabled() -> bool:
    """Check if shadow observation is enabled."""
    return ai_engineer_os_flags.is_enabled(FeatureFlag.SHADOW_OBSERVATION)


def is_reasoning_pipeline_enabled() -> bool:
    """Check if reasoning pipeline is enabled."""
    return ai_engineer_os_flags.is_enabled(FeatureFlag.REASONING_PIPELINE)


def is_read_only_mode() -> bool:
    """Check if read-only mode is enabled."""
    return ai_engineer_os_flags.is_enabled(FeatureFlag.READ_ONLY_MODE)
