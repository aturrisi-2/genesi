"""
AI Engineer OS - Feature Flags
Centralized feature flag management for safe development.
All features are DISABLED by default.
"""

import os
from typing import Dict, Any, Optional
from datetime import datetime


class FeatureFlags:
    """
    Feature flags management for AI Engineer OS.
    
    This class provides centralized control over all AI Engineer OS features.
    All features are disabled by default and must be explicitly enabled.
    """
    
    # Feature definitions with safety levels
    FEATURES = {
        "MULTI_AGENT_SYSTEM": {
            "description": "Enable multi-agent framework",
            "safety_level": "HIGH",
            "dependencies": [],
            "default": False
        },
        "RESEARCH_ENGINE": {
            "description": "Enable external research integration",
            "safety_level": "MEDIUM",
            "dependencies": [],
            "default": False
        },
        "META_REASONING": {
            "description": "Enable meta-reasoning and self-reflection",
            "safety_level": "HIGH",
            "dependencies": [],
            "default": False
        },
        "EVOLUTION_ENGINE": {
            "description": "Enable code generation and system evolution",
            "safety_level": "CRITICAL",
            "dependencies": ["META_REASONING"],
            "default": False
        },
        "ORCHESTRATOR": {
            "description": "Enable multi-agent orchestration",
            "safety_level": "HIGH",
            "dependencies": ["MULTI_AGENT_SYSTEM"],
            "default": False
        },
        "AUTO_PATCHING": {
            "description": "Enable automatic patch application",
            "safety_level": "CRITICAL",
            "dependencies": ["EVOLUTION_ENGINE"],
            "default": False
        },
        "EXTERNAL_APIS": {
            "description": "Enable external API integrations",
            "safety_level": "MEDIUM",
            "dependencies": [],
            "default": False
        },
        "PERSISTENT_LEARNING": {
            "description": "Enable persistent learning storage",
            "safety_level": "MEDIUM",
            "dependencies": ["META_REASONING"],
            "default": False
        }
    }
    
    def __init__(self):
        self._flags = self._load_default_flags()
        self._load_environment_flags()
        self._validate_safety()
    
    def _load_default_flags(self) -> Dict[str, bool]:
        """Load default feature flags (all disabled)."""
        return {name: config["default"] for name, config in self.FEATURES.items()}
    
    def _load_environment_flags(self) -> None:
        """Load feature flags from environment variables."""
        env_prefix = "AI_OS_"
        
        for feature_name in self.FEATURES:
            env_var = f"{env_prefix}{feature_name.upper()}"
            env_value = os.environ.get(env_var, "").lower()
            
            if env_value in ("true", "1", "yes", "on"):
                self._flags[feature_name] = True
            elif env_value in ("false", "0", "no", "off"):
                self._flags[feature_name] = False
    
    def _validate_safety(self) -> None:
        """Validate safety constraints."""
        # Check critical features
        critical_features = ["EVOLUTION_ENGINE", "AUTO_PATCHING"]
        for feature in critical_features:
            if self._flags.get(feature, False):
                print(f"WARNING: Critical feature '{feature}' is enabled - ensure safety measures")
        
        # Check dependencies
        for feature_name, flag_value in self._flags.items():
            if flag_value:
                dependencies = self.FEATURES[feature_name]["dependencies"]
                for dep in dependencies:
                    if not self._flags.get(dep, False):
                        print(f"WARNING: Feature '{feature_name}' requires dependency '{dep}'")
    
    def is_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled."""
        return self._flags.get(feature, False)
    
    def enable_feature(self, feature: str) -> bool:
        """Enable a feature (if safe)."""
        if feature not in self.FEATURES:
            print(f"ERROR: Unknown feature '{feature}'")
            return False
        
        # Check dependencies
        dependencies = self.FEATURES[feature]["dependencies"]
        for dep in dependencies:
            if not self._flags.get(dep, False):
                print(f"ERROR: Cannot enable '{feature}' - dependency '{dep}' not enabled")
                return False
        
        self._flags[feature] = True
        print(f"Feature '{feature}' enabled")
        return True
    
    def disable_feature(self, feature: str) -> bool:
        """Disable a feature."""
        if feature not in self.FEATURES:
            print(f"ERROR: Unknown feature '{feature}'")
            return False
        
        self._flags[feature] = False
        print(f"Feature '{feature}' disabled")
        return True
    
    def get_enabled_features(self) -> list:
        """Get list of enabled features."""
        return [name for name, enabled in self._flags.items() if enabled]
    
    def get_feature_info(self, feature: str) -> Optional[Dict[str, Any]]:
        """Get feature information."""
        if feature not in self.FEATURES:
            return None
        
        return {
            "name": feature,
            "enabled": self._flags[feature],
            "description": self.FEATURES[feature]["description"],
            "safety_level": self.FEATURES[feature]["safety_level"],
            "dependencies": self.FEATURES[feature]["dependencies"]
        }
    
    def get_all_features(self) -> Dict[str, Dict[str, Any]]:
        """Get all feature information."""
        return {
            name: self.get_feature_info(name)
            for name in self.FEATURES
        }
    
    def get_safety_report(self) -> Dict[str, Any]:
        """Generate safety report."""
        enabled_critical = [
            name for name, config in self.FEATURES.items()
            if self._flags.get(name, False) and config["safety_level"] == "CRITICAL"
        ]
        
        dependency_issues = []
        for feature_name, flag_value in self._flags.items():
            if flag_value:
                dependencies = self.FEATURES[feature_name]["dependencies"]
                for dep in dependencies:
                    if not self._flags.get(dep, False):
                        dependency_issues.append(f"{feature_name} -> {dep}")
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_features": len(self.FEATURES),
            "enabled_features": len(self.get_enabled_features()),
            "critical_enabled": enabled_critical,
            "dependency_issues": dependency_issues,
            "safety_status": "WARNING" if enabled_critical or dependency_issues else "SAFE"
        }


# Global feature flags instance
feature_flags = FeatureFlags()


# Convenience functions
def is_feature_enabled(feature: str) -> bool:
    """Check if a feature is enabled."""
    return feature_flags.is_enabled(feature)


def get_safety_status() -> Dict[str, Any]:
    """Get current safety status."""
    return feature_flags.get_safety_report()


# Safety check on import
if __name__ == "__main__":
    report = get_safety_status()
    print("AI Engineer OS - Feature Flags Safety Report")
    print(f"Total Features: {report['total_features']}")
    print(f"Enabled Features: {report['enabled_features']}")
    print(f"Safety Status: {report['safety_status']}")
    
    if report['critical_enabled']:
        print(f"Critical Features Enabled: {report['critical_enabled']}")
    
    if report['dependency_issues']:
        print("Dependency Issues:")
        for issue in report['dependency_issues']:
            print(f"  - {issue}")
    else:
        print("No dependency issues detected")
