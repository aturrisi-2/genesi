"""
AI Engineer OS Integration Configuration
Safe configuration with conservative defaults.
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass


@dataclass
class IntegrationConfig:
    """Configuration for AI Engineer OS integration."""
    
    # Master settings
    enabled: bool = False
    shadow_mode_only: bool = True
    read_only_mode: bool = True
    
    # Performance settings
    max_background_tasks: int = 2
    task_timeout_seconds: int = 300
    max_memory_mb: int = 512
    
    # Observation settings
    observe_proactor_calls: bool = True
    observe_memory_operations: bool = False
    observe_llm_calls: bool = True
    
    # Reasoning pipeline settings
    enable_reasoning_pipeline: bool = False
    reasoning_timeout_seconds: int = 120
    max_reasoning_depth: int = 5
    
    # Suggestion settings
    generate_suggestions: bool = False
    store_suggestions: bool = True
    suggestion_retention_days: int = 30
    
    # Logging settings
    enable_logging: bool = True
    log_level: str = "INFO"
    separate_log_file: bool = True
    max_log_file_size_mb: int = 100
    
    # Memory settings
    separate_memory_store: bool = True
    memory_retention_days: int = 90
    max_memory_entries: int = 10000
    
    # Safety settings
    error_isolation: bool = True
    no_runtime_modification: bool = True
    require_explicit_enable: bool = True
    
    @classmethod
    def from_environment(cls) -> "IntegrationConfig":
        """Create configuration from environment variables."""
        return cls(
            enabled=os.environ.get("AI_ENGINEER_OS_ENABLED", "false").lower() == "true",
            shadow_mode_only=os.environ.get("AI_OS_SHADOW_MODE_ONLY", "true").lower() == "true",
            read_only_mode=os.environ.get("AI_OS_READ_ONLY_MODE", "true").lower() == "true",
            
            max_background_tasks=int(os.environ.get("AI_OS_MAX_BACKGROUND_TASKS", "2")),
            task_timeout_seconds=int(os.environ.get("AI_OS_TASK_TIMEOUT", "300")),
            max_memory_mb=int(os.environ.get("AI_OS_MAX_MEMORY_MB", "512")),
            
            observe_proactor_calls=os.environ.get("AI_OS_OBSERVE_PROACTOR", "true").lower() == "true",
            observe_memory_operations=os.environ.get("AI_OS_OBSERVE_MEMORY", "false").lower() == "true",
            observe_llm_calls=os.environ.get("AI_OS_OBSERVE_LLM", "true").lower() == "true",
            
            enable_reasoning_pipeline=os.environ.get("AI_OS_REASONING_PIPELINE", "false").lower() == "true",
            reasoning_timeout_seconds=int(os.environ.get("AI_OS_REASONING_TIMEOUT", "120")),
            max_reasoning_depth=int(os.environ.get("AI_OS_MAX_REASONING_DEPTH", "5")),
            
            generate_suggestions=os.environ.get("AI_OS_GENERATE_SUGGESTIONS", "false").lower() == "true",
            store_suggestions=os.environ.get("AI_OS_STORE_SUGGESTIONS", "true").lower() == "true",
            suggestion_retention_days=int(os.environ.get("AI_OS_SUGGESTION_RETENTION_DAYS", "30")),
            
            enable_logging=os.environ.get("AI_OS_LOGGING_ENABLED", "true").lower() == "true",
            log_level=os.environ.get("AI_OS_LOG_LEVEL", "INFO"),
            separate_log_file=os.environ.get("AI_OS_SEPARATE_LOG", "true").lower() == "true",
            max_log_file_size_mb=int(os.environ.get("AI_OS_MAX_LOG_SIZE_MB", "100")),
            
            separate_memory_store=os.environ.get("AI_OS_SEPARATE_MEMORY", "true").lower() == "true",
            memory_retention_days=int(os.environ.get("AI_OS_MEMORY_RETENTION_DAYS", "90")),
            max_memory_entries=int(os.environ.get("AI_OS_MAX_MEMORY_ENTRIES", "10000")),
            
            error_isolation=os.environ.get("AI_OS_ERROR_ISOLATION", "true").lower() == "true",
            no_runtime_modification=os.environ.get("AI_OS_NO_RUNTIME_MODIFICATION", "true").lower() == "true",
            require_explicit_enable=os.environ.get("AI_OS_REQUIRE_EXPLICIT", "true").lower() == "true",
        )
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of issues."""
        issues = []
        
        # Safety validations
        if self.enabled and not self.shadow_mode_only:
            issues.append("AI Engineer OS cannot be enabled without shadow_mode_only=true")
        
        if self.enabled and not self.read_only_mode:
            issues.append("AI Engineer OS cannot be enabled without read_only_mode=true")
        
        if self.enabled and not self.no_runtime_modification:
            issues.append("AI Engineer OS cannot be enabled without no_runtime_modification=true")
        
        # Performance validations
        if self.max_background_tasks > 5:
            issues.append("max_background_tasks should not exceed 5 for safety")
        
        if self.task_timeout_seconds > 600:
            issues.append("task_timeout_seconds should not exceed 600 seconds")
        
        if self.max_memory_mb > 1024:
            issues.append("max_memory_mb should not exceed 1024MB")
        
        # Feature dependency validations
        if self.generate_suggestions and not self.enable_reasoning_pipeline:
            issues.append("generate_suggestions requires enable_reasoning_pipeline=true")
        
        if self.store_suggestions and not self.separate_memory_store:
            issues.append("store_suggestions requires separate_memory_store=true")
        
        return issues
    
    def is_safe(self) -> bool:
        """Check if configuration is safe."""
        return len(self.validate()) == 0


# Global configuration instance
integration_config = IntegrationConfig.from_environment()


def get_integration_config() -> IntegrationConfig:
    """Get global integration configuration."""
    return integration_config


def validate_integration_config() -> list[str]:
    """Validate integration configuration."""
    return integration_config.validate()
