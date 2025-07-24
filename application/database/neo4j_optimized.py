"""
Optimized Neo4j query execution for large-scale gap analysis.
This module provides advanced traversal techniques for efficient path finding
in extremely large graph databases.
"""

import logging
import time
import neo4j
import asyncio
from typing import Dict, List, Tuple, Optional, Any, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Constants for query optimization
MAX_INITIAL_DEPTH = 3
MAX_FINAL_DEPTH = 5
MIN_PATHS_REQUIRED = 10
BASE_TIMEOUT = 30  # seconds
MAX_TIMEOUT = 180  # seconds
MAX_PATHS_PER_QUERY = 50
RELATIONSHIP_PRIORITIES = {
    "LINKED_TO": 1,
    "AUTOMATICALLY_LINKED_TO": 2,
    "CONTAINS": 3, 
    "RELATED": 4
}

class ProgressiveQueryExecutor:
    """
    Execute Neo4j queries with progressive depth and timeout management.
    Automatically adapts query patterns based on graph complexity and results.
    """
    
    def __init__(self, neo4j_driver, max_paths=30):
        """Initialize with Neo4j driver connection."""
        self.driver = neo4j_driver
        self.max_paths = max_paths
        self.path_count = 0
        self.execution_stats = {}
        self.last_execution_time = 0
        
    async def execute_bounded_traversal(self, 
                                 standard1: str, 
                                 standard2: str, 
                                 denylist: List[str] = None) -> List[Dict]:
        """
        Execute progressive bounded traversals with strict termination guarantees.
        
        Args:
            standard1: Name of first standard
            standard2: Name of second standard
            denylist: List of node names to exclude from paths
            
        Returns:
            List of path records found between standards
        """
        if denylist is None:
            denylist = ["Cross-cutting concerns"]
            
        start_time = time.time()
        self.path_count = 0
        self.execution_stats = {
            "queries_executed": 0,
            "paths_found": 0,
            "max_depth_reached": 0
        }
        
        # First check if standards exist
        if not await self._check_standards_exist(standard1, standard2):
            logger.info(f"One or both standards don't exist: {standard1}, {standard2}")
            return []
        
        # Try direct connections first (highest quality, lowest cost)
        direct_paths = await self._find_direct_connections(standard1, standard2, denylist)
        self.path_count += len(direct_paths)
        self.execution_stats["paths_found"] += len(direct_paths)
        
        # If we found enough direct paths, we're done
        if self.path_count >= self.max_paths:
            logger.info(f"Found sufficient direct paths: {self.path_count}")
            self.last_execution_time = time.time() - start_time
            return direct_paths[:self.max_paths]
        
        # Progressive depth traversal strategy
        remaining_slots = self.max_paths - self.path_count
        
        # Try specific relationship types first at increasing depths
        # This is more efficient than immediately going for all relationship types
        for rel_type, priority in sorted(RELATIONSHIP_PRIORITIES.items(), key=lambda x: x[1]):
            # Only continue if we need more paths
            if self.path_count >= self.max_paths:
                break
                
            remaining_slots = self.max_paths - self.path_count
            
            # Try progressively deeper traversals with this relationship type
            for depth in range(2, MAX_INITIAL_DEPTH + 1):
                # Skip deeper traversals if we already have enough paths
                if self.path_count >= self.max_paths:
                    break
                    
                relationship_paths = await self._find_paths_by_relationship(
                    standard1, standard2, rel_type, depth, denylist, limit=remaining_slots
                )
                
                self.path_count += len(relationship_paths)
                direct_paths.extend(relationship_paths)
                self.execution_stats["paths_found"] += len(relationship_paths)
                self.execution_stats["max_depth_reached"] = max(
                    self.execution_stats["max_depth_reached"], depth
                )
                
                # Update remaining slots
                remaining_slots = self.max_paths - self.path_count
                
                # If this depth gave us results, don't immediately go deeper
                if len(relationship_paths) > 0:
                    break
        
        # If we still need more paths, try a more general approach
        # but with strict limits on depth and result count
        if self.path_count < MIN_PATHS_REQUIRED:
            remaining_slots = self.max_paths - self.path_count
            
            general_paths = await self._find_general_paths(
                standard1, standard2, denylist, 
                max_depth=MAX_FINAL_DEPTH,
                limit=remaining_slots
            )
            
            self.path_count += len(general_paths)
            direct_paths.extend(general_paths)
            self.execution_stats["paths_found"] += len(general_paths)
        
        # Return all paths found, limited to max_paths
        self.last_execution_time = time.time() - start_time
        logger.info(f"Gap analysis completed in {self.last_execution_time:.2f}s, "
                  f"found {self.path_count} paths with {self.execution_stats['queries_executed']} queries")
        
        return direct_paths[:self.max_paths]
    
    async def _check_standards_exist(self, standard1: str, standard2: str) -> bool:
        """Check if both standards exist in the database."""
        try:
            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH (s1:NeoStandard {name: $name1})
                    MATCH (s2:NeoStandard {name: $name2})
                    RETURN count(s1) > 0 AND count(s2) > 0 as exists
                    """,
                    {"name1": standard1, "name2": standard2}
                )
                
                self.execution_stats["queries_executed"] += 1
                record = result.single()
                if record and record["exists"]:
                    return True
                return False
        except Exception as e:
            logger.error(f"Error checking standards existence: {e}")
            return False
    
    async def _find_direct_connections(self, 
                               standard1: str, 
                               standard2: str, 
                               denylist: List[str]) -> List[Dict]:
        """Find direct connections between standards through CREs."""
        try:
            with self.driver.session() as session:
                result = session.run(
                    """
                    // Find standards
                    MATCH (base:NeoStandard {name: $name1})
                    MATCH (compare:NeoStandard {name: $name2})
                    
                    // Direct connections through shared CREs (2 hops)
                    MATCH p = (base)-[:LINKED_TO|AUTOMATICALLY_LINKED_TO]-(cre:NeoCRE)
                              -[:LINKED_TO|AUTOMATICALLY_LINKED_TO]-(compare)
                    WHERE NOT cre.name IN $denylist
                    
                    // Calculate path length for sorting
                    WITH p, length(p) as path_length
                    ORDER BY path_length ASC
                    
                    // Return limited results
                    RETURN p
                    LIMIT $limit
                    """,
                    {
                        "name1": standard1, 
                        "name2": standard2, 
                        "denylist": denylist,
                        "limit": MAX_PATHS_PER_QUERY
                    }
                )
                
                self.execution_stats["queries_executed"] += 1
                return [record["p"] for record in result]
        except Exception as e:
            logger.error(f"Error finding direct connections: {e}")
            return []
    
    async def _find_paths_by_relationship(self,
                                  standard1: str,
                                  standard2: str,
                                  relationship_type: str,
                                  depth: int,
                                  denylist: List[str],
                                  limit: int) -> List[Dict]:
        """Find paths using a specific relationship type with bounded depth."""
        if limit <= 0:
            return []
            
        # Calculate adaptive timeout based on depth
        timeout = min(BASE_TIMEOUT * depth, MAX_TIMEOUT)
        
        try:
            with self.driver.session(default_access_mode=neo4j.READ_ACCESS) as session:
                # Use explicit timeout management
                result = session.run(
                    f"""
                    // Find standards
                    MATCH (base:NeoStandard {{name: $name1}})
                    MATCH (compare:NeoStandard {{name: $name2}})
                    
                    // Find paths with specific relationship type
                    MATCH p = shortestPath((base)-[:{relationship_type}*..{depth}]-(compare))
                    WHERE ALL(n IN nodes(p) WHERE (n:NeoCRE OR n = base OR n = compare) 
                          AND NOT n.name IN $denylist)
                    
                    // Return limited results
                    WITH p, length(p) AS path_length
                    WHERE path_length > 1
                    RETURN p
                    ORDER BY path_length ASC
                    LIMIT $limit
                    """,
                    {
                        "name1": standard1, 
                        "name2": standard2, 
                        "denylist": denylist,
                        "limit": limit
                    }
                )
                
                self.execution_stats["queries_executed"] += 1
                
                # Use timeout to avoid hanging
                start = time.time()
                paths = []
                while time.time() - start < timeout:
                    if not result.has_next():
                        break
                    paths.append(result.next()["p"])
                    
                return paths
        except Exception as e:
            logger.error(f"Error finding paths by relationship {relationship_type}: {e}")
            return []
    
    async def _find_general_paths(self,
                          standard1: str,
                          standard2: str,
                          denylist: List[str],
                          max_depth: int,
                          limit: int) -> List[Dict]:
        """Find paths with any relationship type as a fallback."""
        if limit <= 0:
            return []
            
        try:
            with self.driver.session() as session:
                result = session.run(
                    f"""
                    // Find standards
                    MATCH (base:NeoStandard {{name: $name1}})
                    MATCH (compare:NeoStandard {{name: $name2}})
                    
                    // Find any paths within depth limit
                    MATCH p = allShortestPaths((base)-[*..{max_depth}]-(compare))
                    WHERE ALL(n IN nodes(p) WHERE (n:NeoCRE OR n = base OR n = compare)
                          AND NOT n.name IN $denylist)
                    
                    // Return limited results 
                    WITH p, length(p) as path_length
                    WHERE path_length > 1 AND path_length <= {max_depth}
                    RETURN p
                    ORDER BY path_length ASC
                    LIMIT $limit
                    """,
                    {
                        "name1": standard1, 
                        "name2": standard2, 
                        "denylist": denylist,
                        "limit": limit
                    }
                )
                
                self.execution_stats["queries_executed"] += 1
                return [record["p"] for record in result]
        except Exception as e:
            logger.error(f"Error finding general paths: {e}")
            return []
            
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get statistics about the last execution."""
        return {
            **self.execution_stats,
            "execution_time": self.last_execution_time,
            "paths_found": self.path_count
        }


class ParallelQueryExecutor:
    """
    Execute multiple Neo4j queries in parallel for faster results.
    Uses async/await pattern with proper connection handling.
    """
    
    def __init__(self, neo4j_driver, max_workers=4):
        """Initialize with Neo4j driver and worker pool."""
        self.driver = neo4j_driver
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.progressive_executor = ProgressiveQueryExecutor(neo4j_driver)
    
    async def find_all_paths(self, 
                     standard1: str, 
                     standard2: str,
                     denylist: List[str] = None) -> List[Dict]:
        """Find all paths between standards using multiple parallel strategies."""
        if denylist is None:
            denylist = ["Cross-cutting concerns"]
        
        # Create tasks for parallel execution
        tasks = [
            # Direct connections (highest priority)
            self._create_task(self.progressive_executor._find_direct_connections, 
                             standard1, standard2, denylist),
            
            # Type-specific paths in parallel
            self._create_task(self.progressive_executor._find_paths_by_relationship,
                             standard1, standard2, "LINKED_TO", 3, denylist, 20),
                             
            self._create_task(self.progressive_executor._find_paths_by_relationship,
                             standard1, standard2, "AUTOMATICALLY_LINKED_TO", 3, denylist, 15),
                             
            self._create_task(self.progressive_executor._find_paths_by_relationship,
                             standard1, standard2, "CONTAINS", 3, denylist, 15),
        ]
        
        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine and filter results
        all_paths = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error in parallel execution: {result}")
                continue
            all_paths.extend(result)
            
        # Deduplicate paths (Neo4j can return the same path in different queries)
        # Using a simple set for path IDs
        unique_paths = []
        seen_ids = set()
        
        for path in all_paths:
            # Create a simple hash of the path to identify duplicates
            path_id = self._get_path_identifier(path)
            if path_id not in seen_ids:
                seen_ids.add(path_id)
                unique_paths.append(path)
        
        return unique_paths[:self.progressive_executor.max_paths]
    
    async def _create_task(self, func, *args):
        """Create an async task that executes in the thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)
    
    def _get_path_identifier(self, path):
        """Create a unique identifier for a path to detect duplicates."""
        # Extract node IDs and relationship types as a hash
        try:
            nodes = [n.element_id for n in path.nodes]
            rels = [r.type for r in path.relationships]
            return hash(tuple(nodes + rels))
        except (AttributeError, TypeError):
            # Fallback for when path structure is different
            return id(path) 