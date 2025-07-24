"""
Vectorized path representation for similarity search.
This module provides efficient path encoding and similarity search capabilities
for fast gap analysis without full graph traversal.
"""

import logging
import time
import json
import numpy as np
import os
from typing import Dict, List, Any, Tuple, Optional, Set, Union
from collections import defaultdict
import hashlib

# Try to import vector DB libraries
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    
try:
    import tensorflow as tf
    import tensorflow_hub as hub
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

logger = logging.getLogger(__name__)

# Vector dimensions for different encoding methods
RELATIONSHIP_DIMENSIONS = 10  # One-hot encoding dimensions for relationships
NODE_TYPE_DIMENSIONS = 5  # One-hot encoding for node types
PATH_FEATURE_DIMENSIONS = 50  # Combined path features
EMBEDDING_DIMENSIONS = 512  # For text embedding features

# Constants
MAX_PATH_LENGTH = 5  # Maximum number of hops to encode
VECTOR_CACHE_DIR = ".vector_cache"  # Directory for saving vector indexes

class PathVectorizer:
    """
    Converts graph paths to vector representations for fast similarity search.
    
    Features:
    - Multiple encoding methods (structure-based, feature-based)
    - Similarity search using vector distances
    - Path clustering and classification
    """
    
    def __init__(self, vector_dim=None, cache_dir=VECTOR_CACHE_DIR, use_embeddings=False):
        """
        Initialize path vectorizer.
        
        Args:
            vector_dim: Dimension of vectors (default chosen by encoding method)
            cache_dir: Directory for saving vector indexes
            use_embeddings: Whether to use text embeddings (requires TensorFlow)
        """
        self.vector_dim = vector_dim or PATH_FEATURE_DIMENSIONS
        self.cache_dir = cache_dir
        self.use_embeddings = use_embeddings and TF_AVAILABLE
        
        # Create cache directory if needed
        os.makedirs(cache_dir, exist_ok=True)
        
        # Initialize vectors and paths mapping
        self.path_vectors = {}  # Maps path_id to vector
        self.vector_paths = {}  # Maps path_id to actual path data
        
        # FAISS index for fast similarity search
        self.index = None
        if FAISS_AVAILABLE:
            self.index = faiss.IndexFlatL2(self.vector_dim)
            
        # Text embedding model
        self.embedding_model = None
        if self.use_embeddings:
            try:
                self.embedding_model = hub.load("https://tfhub.dev/google/universal-sentence-encoder/4")
                logger.info("Loaded text embedding model")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                self.use_embeddings = False
                
        # Mappings for encoding
        self.relationship_types = {
            "LINKED_TO": 0,
            "AUTOMATICALLY_LINKED_TO": 1,
            "CONTAINS": 2,
            "RELATED": 3,
            "SAME": 4,
            "CONTAINS_UP": 5,
            "CONTAINS_DOWN": 6,
            "UNKNOWN": 7
        }
        
        self.node_types = {
            "NeoStandard": 0,
            "NeoCRE": 1,
            "NeoTool": 2,
            "NeoCode": 3,
            "NeoDocument": 4
        }
        
        # Statistics
        self.vectorized_paths = 0
        
    def vectorize_path(self, path: Dict[str, Any]) -> np.ndarray:
        """
        Convert a path to a fixed-size vector representation.
        
        Args:
            path: Path dictionary with nodes and relationships
            
        Returns:
            Numpy array vector representation
        """
        # Check for cached vector
        path_id = self._get_path_id(path)
        if path_id in self.path_vectors:
            return self.path_vectors[path_id]
        
        # Extract features from path
        features = []
        
        # Basic path features
        path_length = len(path.get("path", []))
        features.append(path_length / MAX_PATH_LENGTH)  # Normalized path length
        
        # Get path score if available
        path_score = path.get("score", 0)
        features.append(min(path_score, 10) / 10)  # Normalized score
        
        # Encode relationship types in path
        rel_features = self._encode_relationships(path)
        features.extend(rel_features)
        
        # Encode node types in path
        node_features = self._encode_node_types(path)
        features.extend(node_features)
        
        # Add structural features
        struct_features = self._extract_structural_features(path)
        features.extend(struct_features)
        
        # If using text embeddings, add them
        if self.use_embeddings and self.embedding_model is not None:
            text_features = self._extract_text_features(path)
            if text_features is not None:
                features.extend(text_features)
                
        # Pad or truncate to target dimension
        if len(features) < self.vector_dim:
            features.extend([0] * (self.vector_dim - len(features)))
        elif len(features) > self.vector_dim:
            features = features[:self.vector_dim]
            
        # Convert to numpy array
        vector = np.array(features, dtype=np.float32)
        
        # Normalize vector
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
            
        # Cache vector
        self.path_vectors[path_id] = vector
        self.vector_paths[path_id] = path
        self.vectorized_paths += 1
        
        return vector
        
    def vectorize_paths(self, paths: List[Dict[str, Any]]) -> np.ndarray:
        """
        Vectorize a batch of paths.
        
        Args:
            paths: List of path dictionaries
            
        Returns:
            Array of vector representations
        """
        vectors = []
        for path in paths:
            vectors.append(self.vectorize_path(path))
            
        return np.array(vectors, dtype=np.float32)
        
    def add_to_index(self, paths: List[Dict[str, Any]]) -> None:
        """
        Add paths to search index.
        
        Args:
            paths: List of path dictionaries
        """
        if not FAISS_AVAILABLE or not self.index:
            logger.warning("FAISS not available, cannot add to index")
            return
            
        # Vectorize paths
        vectors = self.vectorize_paths(paths)
        
        # Add to index
        self.index.add(vectors)
        logger.info(f"Added {len(paths)} paths to index. Total indexed: {self.index.ntotal}")
        
    def find_similar_paths(self, 
                         query_path: Dict[str, Any], 
                         k: int = 10) -> List[Dict[str, Any]]:
        """
        Find paths similar to the query path.
        
        Args:
            query_path: Path to find similar paths to
            k: Number of similar paths to return
            
        Returns:
            List of similar paths with similarity scores
        """
        if not FAISS_AVAILABLE or not self.index or self.index.ntotal == 0:
            logger.warning("FAISS index not available or empty")
            return []
            
        # Vectorize query path
        query_vector = self.vectorize_path(query_path)
        
        # Reshape for FAISS search
        query_vector = np.array([query_vector], dtype=np.float32)
        
        # Search index
        distances, indices = self.index.search(query_vector, k)
        
        # Get paths for results
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= self.index.ntotal:
                continue
                
            # Find path corresponding to this index
            path_id = None
            for pid, vec in self.path_vectors.items():
                if np.array_equal(vec, self.index.reconstruct(idx)):
                    path_id = pid
                    break
                    
            if path_id and path_id in self.vector_paths:
                path = self.vector_paths[path_id]
                results.append({
                    "path": path,
                    "similarity": 1.0 - distances[0][i],
                    "distance": distances[0][i]
                })
                
        return results
        
    def precompute_standard_paths(self, 
                               standard_name: str,
                               paths: List[Dict[str, Any]]) -> None:
        """
        Precompute and index paths for a standard.
        
        Args:
            standard_name: Name of the standard
            paths: List of paths starting or ending at this standard
        """
        # Vectorize and add to index
        self.add_to_index(paths)
        
        # Save index for this standard
        self.save_index(f"{standard_name.lower().replace(' ', '_')}_index")
        
    def save_index(self, name: str) -> bool:
        """
        Save FAISS index to disk.
        
        Args:
            name: Index name
            
        Returns:
            Success flag
        """
        if not FAISS_AVAILABLE or not self.index:
            return False
            
        try:
            index_path = os.path.join(self.cache_dir, f"{name}.index")
            faiss.write_index(self.index, index_path)
            
            # Also save path mappings
            mappings_path = os.path.join(self.cache_dir, f"{name}.json")
            with open(mappings_path, 'w') as f:
                # Convert numpy arrays to lists for JSON serialization
                serializable_vectors = {
                    k: v.tolist() for k, v in self.path_vectors.items()
                }
                json.dump({
                    "vectors": serializable_vectors,
                    "paths": self.vector_paths
                }, f)
                
            logger.info(f"Saved index to {index_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
            return False
            
    def load_index(self, name: str) -> bool:
        """
        Load FAISS index from disk.
        
        Args:
            name: Index name
            
        Returns:
            Success flag
        """
        if not FAISS_AVAILABLE:
            return False
            
        try:
            index_path = os.path.join(self.cache_dir, f"{name}.index")
            self.index = faiss.read_index(index_path)
            
            # Load path mappings
            mappings_path = os.path.join(self.cache_dir, f"{name}.json")
            with open(mappings_path, 'r') as f:
                data = json.load(f)
                # Convert lists back to numpy arrays
                self.path_vectors = {
                    k: np.array(v, dtype=np.float32) 
                    for k, v in data.get("vectors", {}).items()
                }
                self.vector_paths = data.get("paths", {})
                
            logger.info(f"Loaded index from {index_path} with {self.index.ntotal} vectors")
            return True
        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return False
            
    def _get_path_id(self, path: Dict[str, Any]) -> str:
        """Generate unique ID for a path."""
        try:
            # Extract key elements that define path identity
            start_id = path.get("start", {}).get("id", "")
            end_id = path.get("end", {}).get("id", "")
            
            # Get relationship sequence
            rel_sequence = []
            for step in path.get("path", []):
                rel = step.get("relationship", "UNKNOWN")
                start = step.get("start", {}).get("id", "")
                end = step.get("end", {}).get("id", "")
                rel_sequence.append(f"{start}:{rel}:{end}")
                
            path_str = f"{start_id}|{'|'.join(rel_sequence)}|{end_id}"
            return hashlib.md5(path_str.encode()).hexdigest()
        except Exception:
            # Fallback to json string
            try:
                return hashlib.md5(json.dumps(path).encode()).hexdigest()
            except:
                # Last resort
                return str(id(path))
                
    def _encode_relationships(self, path: Dict[str, Any]) -> List[float]:
        """Encode relationships in path as vector features."""
        # One-hot encoding of relationships
        rel_counts = [0] * len(self.relationship_types)
        
        # Count each relationship type
        for step in path.get("path", []):
            rel_type = step.get("relationship", "UNKNOWN")
            if rel_type in self.relationship_types:
                rel_counts[self.relationship_types[rel_type]] += 1
                
        # Normalize counts by path length
        path_length = max(1, len(path.get("path", [])))
        rel_features = [count / path_length for count in rel_counts]
        
        return rel_features
        
    def _encode_node_types(self, path: Dict[str, Any]) -> List[float]:
        """Encode node types in path as vector features."""
        # One-hot encoding of node types
        node_counts = [0] * len(self.node_types)
        
        # Count start and end nodes
        start_type = path.get("start", {}).get("doctype", "").split(".")[-1]
        if start_type in self.node_types:
            node_counts[self.node_types[start_type]] += 1
            
        end_type = path.get("end", {}).get("doctype", "").split(".")[-1]
        if end_type in self.node_types:
            node_counts[self.node_types[end_type]] += 1
            
        # Count intermediate nodes
        for step in path.get("path", []):
            start_type = step.get("start", {}).get("doctype", "").split(".")[-1]
            if start_type in self.node_types:
                node_counts[self.node_types[start_type]] += 1
                
            end_type = step.get("end", {}).get("doctype", "").split(".")[-1]
            if end_type in self.node_types:
                node_counts[self.node_types[end_type]] += 1
                
        # Normalize by total node count
        total_nodes = sum(node_counts)
        if total_nodes > 0:
            node_features = [count / total_nodes for count in node_counts]
        else:
            node_features = [0] * len(self.node_types)
            
        return node_features
        
    def _extract_structural_features(self, path: Dict[str, Any]) -> List[float]:
        """Extract structural features from path."""
        features = []
        path_steps = path.get("path", [])
        
        # Path length
        path_length = len(path_steps)
        features.append(path_length / MAX_PATH_LENGTH)  # Normalized path length
        
        # Directed vs undirected path patterns
        direction_changes = 0
        prev_direction = None
        for i, step in enumerate(path_steps):
            if i == 0:
                continue
                
            prev_step = path_steps[i-1]
            prev_end = prev_step.get("end", {}).get("id", "")
            curr_start = step.get("start", {}).get("id", "")
            
            # If previous end is not current start, direction changed
            if prev_end != curr_start:
                direction_changes += 1
                
        features.append(direction_changes / max(1, path_length - 1))
        
        # CRE density (proportion of CRE nodes in the path)
        cre_count = 0
        for step in path_steps:
            start_type = step.get("start", {}).get("doctype", "")
            end_type = step.get("end", {}).get("doctype", "")
            
            if "NeoCRE" in start_type:
                cre_count += 1
            if "NeoCRE" in end_type:
                cre_count += 1
                
        # Normalize by total possible node count (2 per step)
        features.append(cre_count / (2 * max(1, path_length)))
        
        # Path "straightness" - how direct the path is
        # This is the ratio of path length to geometric distance
        # Lower is straighter
        if path.get("start") and path.get("end"):
            direct_distance = 1.0  # Base distance
            actual_distance = path_length
            straightness = direct_distance / max(1, actual_distance)
            features.append(straightness)
        else:
            features.append(0.0)
            
        return features
        
    def _extract_text_features(self, path: Dict[str, Any]) -> Optional[List[float]]:
        """Extract text embedding features from path descriptions."""
        if not self.use_embeddings or not self.embedding_model:
            return None
            
        # Collect text from path nodes
        texts = []
        
        # Start and end nodes
        if path.get("start") and path.get("start").get("description"):
            texts.append(path["start"]["description"])
            
        if path.get("end") and path.get("end").get("description"):
            texts.append(path["end"]["description"])
            
        # Intermediate nodes
        for step in path.get("path", []):
            if step.get("start") and step.get("start").get("description"):
                texts.append(step["start"]["description"])
                
            if step.get("end") and step.get("end").get("description"):
                texts.append(step["end"]["description"])
                
        # If no texts, return None
        if not texts:
            return None
            
        try:
            # Join texts and get embedding
            text = " ".join(texts)
            embeddings = self.embedding_model([text])
            
            # Convert to list and normalize
            features = embeddings[0].numpy().tolist()
            
            # Reduce dimensionality if needed
            if len(features) > EMBEDDING_DIMENSIONS:
                features = features[:EMBEDDING_DIMENSIONS]
                
            return features
        except Exception as e:
            logger.error(f"Error generating text embeddings: {e}")
            return None


class VectorizedPathIndex:
    """
    Maintains a searchable index of vectorized paths for fast gap analysis.
    Allows for precomputation and storage of path information to avoid
    expensive graph traversals.
    """
    
    def __init__(self, index_dir=VECTOR_CACHE_DIR, use_embeddings=False):
        """
        Initialize vectorized path index.
        
        Args:
            index_dir: Directory for storing indexes
            use_embeddings: Whether to use text embeddings
        """
        self.index_dir = index_dir
        self.vectorizer = PathVectorizer(
            vector_dim=PATH_FEATURE_DIMENSIONS,
            cache_dir=index_dir,
            use_embeddings=use_embeddings
        )
        
        # Track standards and their paths
        self.standard_paths = {}
        self.standard_indexes = {}
        
        # Create index directory if needed
        os.makedirs(index_dir, exist_ok=True)
        
    def add_standard_paths(self, standard_name: str, paths: List[Dict[str, Any]]) -> None:
        """
        Add paths for a standard to the index.
        
        Args:
            standard_name: Name of standard
            paths: List of paths
        """
        if not paths:
            return
            
        # Store paths for this standard
        self.standard_paths[standard_name] = paths
        
        # Vectorize and add to index
        self.vectorizer.add_to_index(paths)
        
        # Save index
        index_name = self._get_index_name(standard_name)
        self.standard_indexes[standard_name] = index_name
        self.vectorizer.save_index(index_name)
        
    def find_paths_between_standards(self, 
                                  standard1: str, 
                                  standard2: str,
                                  max_paths: int = 30) -> List[Dict[str, Any]]:
        """
        Find paths between two standards using vector similarity search.
        
        Args:
            standard1: First standard name
            standard2: Second standard name
            max_paths: Maximum number of paths to return
            
        Returns:
            List of paths between standards
        """
        # First try to load precomputed index for standard1
        index_name = self._get_index_name(standard1)
        loaded = self.vectorizer.load_index(index_name)
        
        if not loaded:
            logger.warning(f"No precomputed index found for {standard1}")
            return []
            
        # Get sample paths for standard2
        if standard2 not in self.standard_paths:
            logger.warning(f"No paths available for {standard2}")
            return []
            
        # Get a sample path for standard2 to use as query
        sample_paths = self.standard_paths.get(standard2, [])
        if not sample_paths:
            logger.warning(f"No sample paths for {standard2}")
            return []
            
        # Use first path as query
        query_path = sample_paths[0]
        
        # Find similar paths
        similar_paths = self.vectorizer.find_similar_paths(query_path, k=max_paths)
        
        # Filter paths between the two standards
        filtered_paths = []
        for result in similar_paths:
            path = result["path"]
            start_name = path.get("start", {}).get("name", "")
            end_name = path.get("end", {}).get("name", "")
            
            # Check if path connects the two standards
            if ((start_name == standard1 and end_name == standard2) or 
                (start_name == standard2 and end_name == standard1)):
                filtered_paths.append({
                    "path": path,
                    "similarity": result["similarity"]
                })
                
        return filtered_paths
        
    def precompute_all_standards(self, standards: List[str], paths: List[Dict[str, Any]]) -> None:
        """
        Precompute path indexes for all standards.
        
        Args:
            standards: List of standard names
            paths: List of all paths
        """
        # Group paths by standard
        standard_paths = defaultdict(list)
        
        for path in paths:
            start_name = path.get("start", {}).get("name", "")
            end_name = path.get("end", {}).get("name", "")
            
            if start_name in standards:
                standard_paths[start_name].append(path)
                
            if end_name in standards and end_name != start_name:
                # Also add with reversed direction
                standard_paths[end_name].append(path)
                
        # Create indexes for each standard
        for standard, std_paths in standard_paths.items():
            logger.info(f"Precomputing index for {standard} with {len(std_paths)} paths")
            self.add_standard_paths(standard, std_paths)
            
    def _get_index_name(self, standard_name: str) -> str:
        """Get index name for a standard."""
        return standard_name.lower().replace(" ", "_").replace("-", "_")
        
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vectorized index."""
        return {
            "standards_indexed": len(self.standard_indexes),
            "standards": list(self.standard_indexes.keys()),
            "total_paths_vectorized": self.vectorizer.vectorized_paths,
            "total_paths_stored": sum(len(paths) for paths in self.standard_paths.values()),
            "using_embeddings": self.vectorizer.use_embeddings
        } 