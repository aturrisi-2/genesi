"""
Proactor Observer - Shadow mode observation of Proactor calls.
Wraps proactor.handle() without modifying original behavior.
"""

import asyncio
import time
import uuid
import json
from typing import Dict, Any, Optional, Callable
from functools import wraps
from pathlib import Path

from .feature_flags import ai_engineer_os_flags, FeatureFlag
from .integration_config import get_integration_config


class ProactorObserver:
    """Observer for Proactor calls in shadow mode."""
    
    def __init__(self):
        self.config = get_integration_config()
        self._observation_count = 0
        self._total_observation_time = 0.0
        self.logs_dir = Path("genesi/ai_engineer_os/logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def observe_handle(self, original_handle: Callable) -> Callable:
        """
        Decorator to observe proactor.handle() calls.
        
        This decorator wraps the original proactor.handle() method
        to capture inputs and outputs without modifying behavior.
        """
        @wraps(original_handle)
        async def wrapped_handle(message: str, intent: str, user_id: str, **kwargs) -> str:
            # Skip observation if AI Engineer OS is disabled
            if not ai_engineer_os_flags.is_enabled(FeatureFlag.SHADOW_OBSERVATION):
                return await original_handle(message, intent, user_id, **kwargs)
            
            # Generate observation ID
            observation_id = str(uuid.uuid4())
            start_time = time.time()
            
            # Log observation start
            await self._log_observation_start(
                observation_id=observation_id,
                message=message,
                intent=intent,
                user_id=user_id,
                kwargs=kwargs
            )
            
            try:
                # Call original proactor.handle()
                result = await original_handle(message, intent, user_id, **kwargs)
                
                # Calculate observation time
                observation_time = time.time() - start_time
                self._observation_count += 1
                self._total_observation_time += observation_time
                
                # Log observation completion
                await self._log_observation_complete(
                    observation_id=observation_id,
                    result=result,
                    observation_time=observation_time,
                    success=True
                )
                
                return result
                
            except Exception as e:
                # Log observation error
                observation_time = time.time() - start_time
                await self._log_observation_error(
                    observation_id=observation_id,
                    error=str(e),
                    observation_time=observation_time
                )
                
                # Re-raise the original exception
                raise
        
        return wrapped_handle
    
    async def _log_observation_start(
        self, 
        observation_id: str,
        message: str,
        intent: str,
        user_id: str,
        kwargs: Dict[str, Any]
    ) -> None:
        """Log observation start."""
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "observation_start",
            "message": message[:200],  # Truncate for log size
            "intent": intent,
            "user_id": user_id,
            "kwargs_keys": list(kwargs.keys())
        }
        
        log_file = self.logs_dir / f"observations_{time.strftime('%Y-%m-%d')}.json"
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass  # Silently fail to avoid affecting proactor
    
    async def _log_observation_complete(
        self, 
        observation_id: str,
        result: str,
        observation_time: float,
        success: bool
    ) -> None:
        """Log observation completion."""
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "observation_complete",
            "result_length": len(result),
            "observation_time": observation_time,
            "success": success
        }
        
        log_file = self.logs_dir / f"observations_{time.strftime('%Y-%m-%d')}.json"
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass  # Silently fail to avoid affecting proactor
    
    async def _log_observation_error(
        self, 
        observation_id: str,
        error: str,
        observation_time: float
    ) -> None:
        """Log observation error."""
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "observation_error",
            "error": error,
            "observation_time": observation_time
        }
        
        log_file = self.logs_dir / f"observations_{time.strftime('%Y-%m-%d')}.json"
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass  # Silently fail to avoid affecting proactor
    
    def get_observation_stats(self) -> Dict[str, Any]:
        """Get observation statistics."""
        avg_time = self._total_observation_time / max(self._observation_count, 1)
        
        return {
            "total_observations": self._observation_count,
            "total_observation_time": self._total_observation_time,
            "average_observation_time": avg_time,
            "observations_per_second": self._observation_count / max(self._total_observation_time, 1)
        }


# Global observer instance
proactor_observer = ProactorObserver()


def observe_proactor_handle(original_handle: Callable) -> Callable:
    """
    Convenience function to observe proactor.handle().
    
    Usage:
        from ai_engineer_os.proactor_observer import observe_proactor_handle
        
        # In proactor.py or wherever proactor is defined
        proactor.handle = observe_proactor_handle(proactor.handle)
    """
    return proactor_observer.observe_handle(original_handle)
