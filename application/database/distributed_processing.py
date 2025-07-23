"""
Distributed processing for gap analysis using Dask.
This module provides a distributed computation framework for processing
large-scale gap analysis tasks in parallel.
"""

import logging
import time
from typing import Dict, List, Any, Tuple, Optional, Set
from datetime import datetime
import asyncio
import json
import os

# Optional imports for distributed processing
try:
    import dask
    from dask.distributed import Client, as_completed, get_worker
    from dask.delayed import delayed
    DASK_AVAILABLE = True
except ImportError:
    DASK_AVAILABLE = False
    
try:
    from celery import Celery, group, chain, chord
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

# Local imports
from application.database.neo4j_optimized import ProgressiveQueryExecutor
from application.utils.gap_analysis import get_path_score, make_resources_key, make_subresources_key

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_CHUNK_SIZE = 5  # Number of paths to process in each task
MAX_PARALLEL_TASKS = 8  # Maximum tasks to run in parallel
WORKER_MEMORY_LIMIT = "2GB"  # Memory limit per worker
RESULT_TTL = 86400  # Cache results for 24 hours (seconds)

class DistributedGapAnalysis:
    """
    Distributed computation framework for gap analysis.
    Scales horizontally across multiple workers using Dask or Celery.
    """
    
    def __init__(self, neo4j_driver, cache_manager=None, use_dask=True, scheduler_address=None):
        """
        Initialize distributed processing framework.
        
        Args:
            neo4j_driver: Neo4j driver instance
            cache_manager: Optional cache manager instance
            use_dask: Whether to use Dask (True) or Celery (False)
            scheduler_address: Address of Dask scheduler or Celery broker
        """
        self.neo4j_driver = neo4j_driver
        self.cache_manager = cache_manager
        self.use_dask = use_dask and DASK_AVAILABLE
        
        # Initialize distributed client
        self.client = None
        if self.use_dask:
            try:
                if scheduler_address:
                    self.client = Client(scheduler_address)
                else:
                    self.client = Client()
                logger.info(f"Connected to Dask scheduler: {self.client.dashboard_link}")
            except Exception as e:
                logger.error(f"Failed to connect to Dask scheduler: {e}")
                self.use_dask = False
        elif CELERY_AVAILABLE:
            # Setup Celery
            broker_url = scheduler_address or os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
            backend_url = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
            self.celery = Celery('gap_analysis', broker=broker_url, backend=backend_url)
            self.celery.conf.update(
                task_serializer='json',
                accept_content=['json'],
                result_serializer='json',
                task_time_limit=600,  # 10 minutes max per task
                worker_max_memory_per_child=250000,  # 250MB per worker
                result_expires=RESULT_TTL
            )
        
        # Initialize local executor as fallback
        self.query_executor = ProgressiveQueryExecutor(neo4j_driver)
        
    async def process_gap_analysis(self, 
                           standard1: str, 
                           standard2: str,
                           cache_key: str = None) -> Dict[str, Any]:
        """
        Process gap analysis using distributed computation.
        
        Args:
            standard1: Name of first standard
            standard2: Name of second standard
            cache_key: Optional cache key for results
            
        Returns:
            Dictionary with gap analysis results
        """
        start_time = time.time()
        
        if not cache_key:
            cache_key = make_resources_key([standard1, standard2])
            
        # Check cache first if available
        if self.cache_manager and await self.cache_manager.exists(cache_key):
            logger.info(f"Cache hit for {standard1}-{standard2}")
            return await self.cache_manager.get(cache_key)
            
        # First get paths using optimized query executor
        paths = await self.query_executor.execute_bounded_traversal(standard1, standard2)
        
        if not paths:
            logger.info(f"No paths found between {standard1} and {standard2}")
            return {"result": {}}
            
        # Process paths in distributed fashion
        if self.use_dask and self.client:
            result = await self._process_with_dask(standard1, standard2, paths, cache_key)
        elif CELERY_AVAILABLE:
            result = await self._process_with_celery(standard1, standard2, paths, cache_key)
        else:
            # Fallback to local processing
            result = self._process_locally(standard1, standard2, paths)
            
        # Cache result if cache manager available
        if self.cache_manager:
            await self.cache_manager.set(cache_key, result, ttl=RESULT_TTL)
            
        execution_time = time.time() - start_time
        logger.info(f"Distributed gap analysis completed in {execution_time:.2f}s")
        
        return result
    
    async def _process_with_dask(self, 
                          standard1: str, 
                          standard2: str, 
                          paths: List[Dict], 
                          cache_key: str) -> Dict[str, Any]:
        """Process paths using Dask distributed computing."""
        # Split paths into chunks for parallel processing
        chunks = [paths[i:i+DEFAULT_CHUNK_SIZE] 
                 for i in range(0, len(paths), DEFAULT_CHUNK_SIZE)]
        
        # Create stage 1: Score calculation tasks
        scoring_tasks = []
        for i, chunk in enumerate(chunks):
            # Submit task to cluster
            task = self.client.submit(
                self._score_paths_chunk,
                chunk,
                key=f"score-{standard1}-{standard2}-{i}"
            )
            scoring_tasks.append(task)
            
        # Wait for all scoring tasks to complete
        scored_chunks = []
        for future in as_completed(scoring_tasks):
            try:
                chunk_result = future.result()
                scored_chunks.extend(chunk_result)
            except Exception as e:
                logger.error(f"Error in path scoring task: {e}")
                
        # Create stage 2: Path grouping and organization
        # This is less parallelizable, so we use fewer workers
        grouped_task = self.client.submit(
            self._group_paths,
            scored_chunks,
            key=f"group-{standard1}-{standard2}"
        )
        
        # Wait for grouping to complete
        try:
            grouped_paths, extra_paths = grouped_task.result()
        except Exception as e:
            logger.error(f"Error in path grouping task: {e}")
            # Fallback to local processing
            grouped_paths, extra_paths = self._group_paths(scored_chunks)
            
        # Create final result
        result = {
            "result": grouped_paths,
            "extra_paths": extra_paths,
            "metadata": {
                "standard1": standard1,
                "standard2": standard2,
                "path_count": len(paths),
                "execution_time": time.time(),
                "distributed": True
            }
        }
        
        return result
    
    async def _process_with_celery(self, 
                            standard1: str, 
                            standard2: str, 
                            paths: List[Dict], 
                            cache_key: str) -> Dict[str, Any]:
        """Process paths using Celery distributed computing."""
        # Split paths into chunks for parallel processing
        chunks = [paths[i:i+DEFAULT_CHUNK_SIZE] 
                 for i in range(0, len(paths), DEFAULT_CHUNK_SIZE)]
        
        # Register tasks with Celery
        @self.celery.task(name='gap_analysis.score_paths')
        def score_paths_task(paths_chunk):
            return self._score_paths_chunk(paths_chunk)
            
        @self.celery.task(name='gap_analysis.group_paths')
        def group_paths_task(scored_paths):
            return self._group_paths(scored_paths)
            
        # Create workflow: score chunks in parallel, then group results
        score_tasks = group(score_paths_task.s(chunk) for chunk in chunks)
        workflow = chord(score_tasks)(group_paths_task.s())
        
        # Execute workflow
        async_result = workflow.apply_async()
        
        # Wait for result (with timeout)
        try:
            # Wait up to 5 minutes
            grouped_paths, extra_paths = async_result.get(timeout=300)
        except Exception as e:
            logger.error(f"Error in Celery workflow: {e}")
            # Fallback to local processing
            scored_chunks = []
            for chunk in chunks:
                scored_chunks.extend(self._score_paths_chunk(chunk))
            grouped_paths, extra_paths = self._group_paths(scored_chunks)
        
        # Create final result
        result = {
            "result": grouped_paths,
            "extra_paths": extra_paths,
            "metadata": {
                "standard1": standard1,
                "standard2": standard2,
                "path_count": len(paths),
                "execution_time": time.time(),
                "distributed": True
            }
        }
        
        return result
    
    def _process_locally(self, 
                        standard1: str, 
                        standard2: str, 
                        paths: List[Dict]) -> Dict[str, Any]:
        """Process paths using local computation (fallback)."""
        # Score all paths
        scored_paths = self._score_paths_chunk(paths)
        
        # Group paths
        grouped_paths, extra_paths = self._group_paths(scored_paths)
        
        # Create result
        result = {
            "result": grouped_paths,
            "extra_paths": extra_paths,
            "metadata": {
                "standard1": standard1,
                "standard2": standard2,
                "path_count": len(paths),
                "execution_time": time.time(),
                "distributed": False
            }
        }
        
        return result
        
    def _score_paths_chunk(self, paths_chunk: List[Dict]) -> List[Dict]:
        """Score a chunk of paths (designed for distributed execution)."""
        scored_paths = []
        
        for path in paths_chunk:
            try:
                # Add path score if not already present
                if "score" not in path:
                    path["score"] = get_path_score(path)
                scored_paths.append(path)
            except Exception as e:
                logger.error(f"Error scoring path: {e}")
                
        return scored_paths
        
    def _group_paths(self, 
                    scored_paths: List[Dict], 
                    strong_threshold: int = 2) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
        """
        Group paths by start node and separate into strong and weak paths.
        
        Args:
            scored_paths: List of paths with scores
            strong_threshold: Maximum score for strong paths
            
        Returns:
            Tuple of (grouped_paths, extra_paths)
        """
        grouped_paths = {}
        extra_paths_dict = {}
        
        # Sort paths by score (ascending - lower is better)
        sorted_paths = sorted(scored_paths, key=lambda p: p.get("score", float("inf")))
        
        # Group by start node ID
        for path in sorted_paths:
            key = path.get("start", {}).get("id", "")
            end_key = path.get("end", {}).get("id", "")
            
            if not key or not end_key:
                continue
                
            # Initialize dictionaries if needed
            if key not in grouped_paths:
                grouped_paths[key] = {"paths": {}, "extra": 0}
                extra_paths_dict[key] = {"paths": {}}
                
            score = path.get("score", float("inf"))
            
            # Create a copy without the start node to save memory
            path_copy = path.copy()
            if "start" in path_copy:
                del path_copy["start"]
                
            # Strong paths go into main results
            if score <= strong_threshold:
                # If this end node was previously in extra paths, remove it
                if end_key in extra_paths_dict[key]["paths"]:
                    del extra_paths_dict[key]["paths"][end_key]
                    grouped_paths[key]["extra"] -= 1
                    
                # Add or update in main results
                grouped_paths[key]["paths"][end_key] = path_copy
            else:
                # Skip if already have a strong path to this end node
                if end_key in grouped_paths[key]["paths"]:
                    continue
                    
                # Add to extra paths
                if end_key not in extra_paths_dict[key]["paths"]:
                    extra_paths_dict[key]["paths"][end_key] = path_copy
                    grouped_paths[key]["extra"] += 1
                elif extra_paths_dict[key]["paths"][end_key].get("score", float("inf")) > score:
                    # Update if this path is better
                    extra_paths_dict[key]["paths"][end_key] = path_copy
        
        return grouped_paths, extra_paths_dict 