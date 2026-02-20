"""
AI Engineer OS Configuration
Configuration scaffolding for Self-Evolving AI Engineer OS.
All features are DISABLED by default for safety.
"""

import os
from typing import Dict, Any, Optional, List
from pathlib import Path


class AIEngineerOSConfig:
    """
    Configuration manager for AI Engineer OS features.
    
    All features are disabled by default and must be explicitly enabled.
    This ensures no runtime behavior changes without explicit configuration.
    """
    
    def __init__(self):
        self.config_file = Path("config/ai_engineer_os_config.json")
        self._config = self._load_default_config()
        self._load_user_config()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration with all features disabled."""
        return {
            "version": "1.0.0",
            "enabled": False,  # Master switch - entire system disabled by default
            "features": {
                "multi_agent_system": {
                    "enabled": False,
                    "max_agents": 10,
                    "heartbeat_interval": 30,
                    "failure_retry_attempts": 3
                },
                "research_engine": {
                    "enabled": False,
                    "max_concurrent_searches": 5,
                    "cache_ttl": 3600,
                    "timeout": 30,
                    "sources": []
                },
                "meta_reasoning": {
                    "enabled": False,
                    "reflection_interval": 300,
                    "max_insights": 100,
                    "confidence_threshold": 0.7
                },
                "evolution_engine": {
                    "enabled": False,
                    "auto_apply_patches": False,
                    "max_patch_size": 1024,
                    "validation_required": True,
                    "rollback_enabled": True
                },
                "orchestrator": {
                    "enabled": False,
                    "max_concurrent_workflows": 5,
                    "task_timeout": 300,
                    "coordination_strategy": "round_robin"
                }
            },
            "safety": {
                "require_explicit_enable": True,
                "feature_flags_required": True,
                "no_runtime_changes": True,
                "rollback_on_error": True
            },
            "logging": {
                "enabled": False,
                "level": "INFO",
                "separate_file": True,
                "max_file_size": "10MB"
            }
        }
    
    def _load_user_config(self) -> None:
        """Load user configuration if exists."""
        if self.config_file.exists():
            try:
                import json
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                self._merge_config(user_config)
            except Exception as e:
                print(f"Warning: Failed to load AI Engineer OS config: {e}")
    
    def _merge_config(self, user_config: Dict[str, Any]) -> None:
        """Merge user configuration with defaults."""
        def merge_dict(default: Dict, user: Dict) -> Dict:
            for key, value in user.items():
                if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                    default[key] = merge_dict(default[key], value)
                else:
                    default[key] = value
            return default
        
        self._config = merge_dict(self._config, user_config)
    
    def is_enabled(self) -> bool:
        """Check if AI Engineer OS is enabled."""
        return self._config.get("enabled", False)
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a specific feature is enabled."""
        if not self.is_enabled():
            return False
        return self._config.get("features", {}).get(feature, {}).get("enabled", False)
    
    def get_feature_config(self, feature: str) -> Dict[str, Any]:
        """Get configuration for a specific feature."""
        return self._config.get("features", {}).get(feature, {})
    
    def get_config(self) -> Dict[str, Any]:
        """Get full configuration."""
        return self._config.copy()
    
    def validate_safety(self) -> List[str]:
        """Validate safety constraints."""
        issues = []
        
        # Master switch must be enabled
        if not self.is_enabled():
            issues.append("AI Engineer OS is disabled")
        
        # All features must be explicitly enabled
        for feature in self._config.get("features", {}):
            if not self.is_feature_enabled(feature):
                issues.append(f"Feature '{feature}' is disabled")
        
        return issues


# Global configuration instance
ai_engineer_os_config = AIEngineerOSConfig()


# Feature flags for safe development
FEATURE_FLAGS = {
    "MULTI_AGENT_SYSTEM": os.environ.get("AI_OS_MULTI_AGENT", "false").lower() == "true",
    "RESEARCH_ENGINE": os.environ.get("AI_OS_RESEARCH", "false").lower() == "true",
    "META_REASONING": os.environ.get("AI_OS_META", "false").lower() == "true",
    "EVOLUTION_ENGINE": os.environ.get("AI_OS_EVOLUTION", "false").lower() == "true",
    "ORCHESTRATOR": os.environ.get("AI_OS_ORCHESTRATOR", "false").lower() == "true",
    "MASTER_SWITCH": os.environ.get("AI_OS_ENABLED", "false").lower() == "true"
}


def is_system_enabled() -> bool:
    """Check if AI Engineer OS system is enabled."""
    return FEATURE_FLAGS["MASTER_SWITCH"] and ai_engineer_os_config.is_enabled()


def is_feature_flag_enabled(feature: str) -> bool:
    """Check if feature is enabled via flag."""
    return FEATURE_FLAGS.get(feature.upper(), False)


def get_system_status() -> Dict[str, Any]:
    """Get current system status."""
    return {
        "enabled": is_system_enabled(),
        "config_loaded": ai_engineer_os_config.config_file.exists(),
        "feature_flags": FEATURE_FLAGS,
        "safety_issues": ai_engineer_os_config.validate_safety() if is_system_enabled() else ["System disabled"]
    }


# Safety check - ensure no accidental activation
if __name__ == "__main__":
    status = get_system_status()
    print("AI Engineer OS Status:")
    print(f"  Enabled: {status['enabled']}")
    print(f"  Config Loaded: {status['config_loaded']}")
    print(f"  Safety Issues: {len(status['safety_issues'])}")
    
    if status['safety_issues']:
        print("  Issues:")
        for issue in status['safety_issues']:
            print(f"    - {issue}")
    else:
        print("  All safety checks passed")
