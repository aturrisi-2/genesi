"""
Shadow Orchestrator - Coordinates shadow mode operations.
"""

import asyncio
from typing import Dict, Any, List, Optional

from .feature_flags import ai_engineer_os_flags, FeatureFlag
from .integration_config import get_integration_config


class ShadowOrchestrator:
    """Orchestrates shadow mode operations."""
    
    def __init__(self):
        self.config = get_integration_config()
        self._running_tasks: List[asyncio.Task] = []
        self._max_concurrent_tasks = self.config.max_background_tasks
    
    async def start(self) -> None:
        """Start shadow orchestrator."""
        if not ai_engineer_os_flags.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED):
            print("AI Engineer OS disabled, shadow orchestrator not started")
            return
        
        print("Starting shadow orchestrator")
    
    async def stop(self) -> None:
        """Stop shadow orchestrator."""
        print("Stopping shadow orchestrator")
        
        # Cancel all running tasks
        for task in self._running_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
        
        self._running_tasks.clear()
        print("Shadow orchestrator stopped")
    
    async def submit_background_task(self, coro) -> asyncio.Task:
        """Submit background task with concurrency control."""
        # Wait for available slot
        while len(self._running_tasks) >= self._max_concurrent_tasks:
            # Remove completed tasks
            self._running_tasks = [task for task in self._running_tasks if not task.done()]
            
            if len(self._running_tasks) >= self._max_concurrent_tasks:
                await asyncio.sleep(1)
        
        # Create and track task
        task = asyncio.create_task(coro)
        self._running_tasks.append(task)
        
        # Remove task when completed
        def remove_task(task):
            if task in self._running_tasks:
                self._running_tasks.remove(task)
        
        task.add_done_callback(lambda t: remove_task(t))
        
        return task
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        return {
            "running_tasks": len(self._running_tasks),
            "max_concurrent_tasks": self._max_concurrent_tasks,
            "task_ids": [id(task) for task in self._running_tasks if not task.done()]
        }


# Global orchestrator instance
shadow_orchestrator = ShadowOrchestrator()


async def start_shadow_orchestrator() -> None:
    """Start shadow orchestrator."""
    await shadow_orchestrator.start()


async def stop_shadow_orchestrator() -> None:
    """Stop shadow orchestrator."""
    await shadow_orchestrator.stop()


def get_shadow_orchestrator_status() -> Dict[str, Any]:
    """Get shadow orchestrator status."""
    return shadow_orchestrator.get_status()
