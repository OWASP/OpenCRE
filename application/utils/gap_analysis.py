import requests
import time
import logging
from rq import Queue, job, exceptions
from typing import List, Dict, Any, Callable, Tuple, Optional, Set, Generator
from application.utils import redis
from application.database import db
from flask import json as flask_json
import json
import functools
import gc
import threading
from collections import defaultdict
from application.defs import cre_defs as defs

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Constants - moved to top level for better performance
# Using tuple keys for relationship-direction combinations to avoid string operations
RELATIONSHIP_PENALTIES = {
    ("CONTAINS", "UP"): 2,
    ("CONTAINS", "DOWN"): 1,
    ("RELATED", None): 2,
    ("LINKED_TO", None): 0,
    ("AUTOMATICALLY_LINKED_TO", None): 0,
    ("SAME", None): 0,
}

# Legacy dictionary for backward compatibility
PENALTIES = {
    "RELATED": 2,
    "CONTAINS_UP": 2,
    "CONTAINS_DOWN": 1,
    "LINKED_TO": 0,
    "AUTOMATICALLY_LINKED_TO": 0,
    "SAME": 0,
}

# Constants for optimization
MAX_BATCH_SIZE = 100
MAX_EXTRA_PATHS_PER_NODE = 20
GAP_ANALYSIS_TIMEOUT = "129600s"  # 36 hours

# LRU cache for path score calculations - increased size for better hit rate
@functools.lru_cache(maxsize=20000)
def get_penalty(relationship: str, direction: Optional[str] = None) -> int:
    """Get penalty value for a relationship type and direction.
    Uses a lookup table for common combinations to avoid string operations."""
    if relationship == "CONTAINS":
        return RELATIONSHIP_PENALTIES.get((relationship, direction), 1)
    return RELATIONSHIP_PENALTIES.get((relationship, None), 1)

def make_resources_key(array: List[str]) -> str:
    """Create a unique cache key for a list of resources."""
    if not array:
        return ""
    return " >> ".join(array)

def make_subresources_key(standards: List[str], key: str) -> str:
    """Create a unique cache key for subresources."""
    return str(make_resources_key(standards)) + "->" + key

def get_relation_direction(step: Dict[str, Any], previous_id: str) -> str:
    """Determine relationship direction based on previous node ID."""
    if not step or not previous_id:
        return "UNKNOWN"
    return "UP" if step.get("start", {}).get("id") == previous_id else "DOWN"

def get_next_id(step: Dict[str, Any], previous_id: str) -> str:
    """Get the next node ID in the path."""
    if not step:
        return ""
    if step.get("start", {}).get("id") == previous_id:
        return step.get("end", {}).get("id", "")
    return step.get("start", {}).get("id", "")

# Optimized path score calculation
def get_path_score(path: Dict[str, Any]) -> int:
    """Calculate path score with optimized algorithm.
    
    Returns an integer score where lower is better.
    Uses memoization and optimized lookups for performance.
    """
    # Check if score is already calculated to avoid recomputation
    if "score" in path:
        return path["score"]
    
    score = 0
    # Get start ID or use empty string if missing
    previous_id = path.get("start", {}).get("id", "")
    
    # Fast path for empty paths
    path_steps = path.get("path", [])
    if not path_steps:
        path["score"] = score  # Cache result
        return score
    
    # Use a direct array access approach for better performance on large paths
    for step in path_steps:
        relationship = step.get("relationship", "")
        
        # CONTAINS needs special handling for direction
        if relationship == "CONTAINS":
            direction = get_relation_direction(step, previous_id)
            penalty = get_penalty(relationship, direction)
        else:
            # Use direct lookup for other relationships
            penalty = get_penalty(relationship)
            
        score += penalty
        step["score"] = penalty
        previous_id = get_next_id(step, previous_id)
    
    # Cache the score in the path object
    path["score"] = score
    return score

def batch_get_scores(paths: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """Process paths in batches and group by score for efficient filtering."""
    score_groups = defaultdict(list)
    
    for path in paths:
        score = get_path_score(path)
        score_groups[score].append(path)
    
    return score_groups

def prune_paths(paths: List[Dict[str, Any]], max_paths: int = 50) -> List[Dict[str, Any]]:
    """Efficiently prune paths to keep only the best ones.
    
    Args:
        paths: List of paths to prune
        max_paths: Maximum number of paths to keep
        
    Returns:
        Pruned list of paths, sorted by score
    """
    # Early exit for empty or small lists
    if not paths or len(paths) <= max_paths:
        return sorted(paths, key=lambda x: x.get("score", float("inf")))
    
    # Group paths by score for efficient filtering
    score_groups = batch_get_scores(paths)
    
    # Get scores in ascending order (lower is better)
    scores = sorted(score_groups.keys())
    
    # Build result list keeping the best paths
    result = []
    remaining = max_paths
    
    for score in scores:
        paths_for_score = score_groups[score]
        to_add = min(len(paths_for_score), remaining)
        result.extend(paths_for_score[:to_add])
        remaining -= to_add
        
        if remaining <= 0:
            break
            
    return result

def store_results_batch(database, cache_key: str, results: Dict[str, Any], 
                       subresource_keys: Dict[str, Dict[str, Any]]) -> None:
    """Store multiple results in the database with batching.
    
    Args:
        database: Database connection
        cache_key: Main cache key
        results: Main results to store
        subresource_keys: Dict of subresource keys and their results
    """
    # Store main results
    database.add_gap_analysis_result(
        cache_key=cache_key, 
        ga_object=flask_json.dumps(results)
    )
    
    # Store subresource results in batches
    batch_count = 0
    batch_size = 0
    batch = {}
    
    for key, value in subresource_keys.items():
        batch[key] = value
        batch_size += 1
        
        # Process batch when it reaches max size
        if batch_size >= MAX_BATCH_SIZE:
            for k, v in batch.items():
                database.add_gap_analysis_result(
                    cache_key=k, 
                    ga_object=flask_json.dumps({"result": v})
                )
            batch = {}
            batch_size = 0
            batch_count += 1
            
    # Process remaining items
    for k, v in batch.items():
        database.add_gap_analysis_result(
            cache_key=k, 
            ga_object=flask_json.dumps({"result": v})
        )

# database is of type Node_collection, cannot annotate due to circular import
def schedule(standards: List[str], database):
    """Schedule a gap analysis between two standards, with optimized caching.
    
    Args:
        standards: List of standard names to analyze connections between
        database: Node_collection instance for database access
    
    Returns:
        Dictionary with either result or job_id
    """
    # Generate a unique cache key for this standards pair
    standards_hash = make_resources_key(standards)
    
    # Early exit for same standard comparisons
    if len(standards) == 2 and standards[0] == standards[1]:
        logger.info(f"Gap analysis requested between same standard {standards[0]}, returning empty result")
        empty_result = {"result": {}}
        return empty_result
    
    # Try to get result from database cache first (most efficient)
    if database.gap_analysis_exists(standards_hash):
        result = database.get_gap_analysis_result(standards_hash)
        if result:
            logger.info(f"Gap analysis result for {standards_hash} found in database cache")
            return flask_json.loads(result)
        
    # If not in database cache, check Redis for job status
    logger.info(f"Gap analysis result for {standards_hash} not found in database cache, checking Redis")
    
    # Get Redis connection
    try:
        conn = redis.connect()
        if not conn:
            logger.error("Failed to connect to Redis")
            return {"error": "Redis connection failed"}
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        return {"error": "Redis connection error"}
    
    # Check if an existing job is already processing this request
    try:
        gap_analysis_results = conn.get(standards_hash)
        
        if gap_analysis_results:
            gap_analysis_dict = json.loads(gap_analysis_results)
            
            # If there's a job ID in Redis, check its status
            if gap_analysis_dict.get("job_id"):
                try:
                    res = job.Job.fetch(id=gap_analysis_dict.get("job_id"), connection=conn)
                    
                    # If job is still running, return job_id
                    if (res.get_status() not in [job.JobStatus.FAILED, 
                                               job.JobStatus.STOPPED,
                                               job.JobStatus.CANCELED,
                                               job.JobStatus.FINISHED]):
                        logger.info(
                            f'Active gap analysis job id {gap_analysis_dict.get("job_id")} '
                            f'for standards: {standards[0]}>>{standards[1]} already exists, returning early'
                        )
                        return {"job_id": gap_analysis_dict.get("job_id")}
                        
                    # If job has finished but result isn't in database yet, wait for completion
                    elif res.get_status() == job.JobStatus.FINISHED:
                        # Try to get result from database again
                        if database.gap_analysis_exists(standards_hash):
                            result = database.get_gap_analysis_result(standards_hash)
                            if result:
                                return flask_json.loads(result)
                        # If still not in database, job may have failed to save results
                        logger.warning(f"Job finished but result not in database, scheduling new job")
                            
                except exceptions.NoSuchJobError:
                    logger.warning(f"Job {gap_analysis_dict.get('job_id')} no longer exists, scheduling new job")
    except Exception as e:
        logger.error(f"Error checking existing gap analysis job: {e}")
    
    # Create a new job with appropriate timeout and priority
    try:
        # Create a queue with appropriate priority
        q = Queue(connection=conn)
        
        # Set appropriate timeout - large timeout for complex standard pairs
        timeout = GAP_ANALYSIS_TIMEOUT
        
        # Enqueue the job with parameters
        gap_analysis_job = q.enqueue_call(
            db.gap_analysis,
            kwargs={
                "neo_db": database.neo_db,
                "node_names": standards,
                "cache_key": standards_hash,
            },
            timeout=timeout,
            result_ttl=86400,  # Cache job result for 24 hours
            ttl=36000,         # Job can stay in queue for 10 hours
            failure_ttl=3600,  # Keep failed jobs for 1 hour
        )
        
        # Store job ID in Redis
        conn.set(
            standards_hash, 
            json.dumps({"job_id": gap_analysis_job.id, "result": ""}),
            ex=36000  # Auto-expire after 10 hours in case of orphaned jobs
        )
        
        logger.info(f"Scheduled new gap analysis job {gap_analysis_job.id} for {standards_hash}")
        return {"job_id": gap_analysis_job.id}
        
    except Exception as e:
        logger.error(f"Failed to schedule gap analysis job: {e}")
        return {"error": f"Failed to schedule job: {str(e)}"}

def preload(target_url: str):
    """Preload gap analysis results for all standard pairs.
    
    This is an administrative function that should be run during system setup
    or maintenance to populate the cache.
    """
    waiting = []
    standards_request = requests.get(f"{target_url}/rest/v1/standards")
    standards = standards_request.json()

    def calculate_a_to_b(sa: str, sb: str) -> bool:
        try:
            res = requests.get(
                f"{target_url}/rest/v1/map_analysis?standard={sa}&standard={sb}",
                timeout=30  # Add timeout to prevent hanging requests
            )
            if res.status_code != 200:
                print(f"{sa}->{sb} returned {res.status_code}")
                return False

            tojson = res.json()
            if tojson.get("result"):
                return True
            if tojson.get("job_id"):
                print(f"{sa}->{sb} waiting")
                return False
            print(f"{sa}->{sb} returned 200 but has no 'result' or 'job_id' key")
            return False
        except Exception as e:
            print(f"Error calculating {sa}->{sb}: {e}")
            return False

    # Build list of standard pairs to analyze
    for sa in standards:
        for sb in standards:
            if sa == sb:
                continue
            waiting.append(f"{sa}->{sb}")
            
    # Process in batches for better performance
    batch_size = 5  # Number of concurrent requests
    
    while waiting:
        # Process a batch of standards
        batch = waiting[:batch_size]
        completed = []
        
        for pair in batch:
            sa, sb = pair.split("->")
            if calculate_a_to_b(sa, sb):
                completed.append(pair)
                
        # Remove completed pairs from waiting list
        for pair in completed:
            waiting.remove(pair)
            
        # Report progress
        print(f"Completed {len(completed)} gap analyses, {len(waiting)} remaining")
        
        # Only sleep if we still have work to do
        if waiting:
            time.sleep(30)
            
    print("Map analysis preloaded successfully")
