"""
Semantic mapping engine for AI-powered CRE mapping.
Uses embedding models and LLMs to find matches between standards and CREs.
"""

import os
import logging
import json
import numpy as np
import time
from typing import List, Dict, Tuple, Any, Optional
from functools import lru_cache

# Set up logging
logger = logging.getLogger(__name__)

# Try to import AI dependencies - provide graceful fallbacks if missing
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI module not available - LLM features will be disabled")

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    logger.warning("Embedding modules not available - similarity features will be disabled")

# Default configuration
DEFAULT_CONFIDENCE_THRESHOLD = 0.75
DEFAULT_EMBEDDING_MODEL = "all-mpnet-base-v2"
DEFAULT_LLM_MODEL = "gpt-4"
EMBEDDING_CACHE_SIZE = 1000  # Number of embeddings to cache

class SemanticMappingEngine:
    """
    Engine for generating embeddings and computing semantic similarity.
    """
    
    def __init__(self):
        """Initialize the semantic mapping engine."""
        self.embedding_model = None
        self.cre_embeddings = {}
        self.initialized = False
        
        # Initialize embedding model if available
        if EMBEDDING_AVAILABLE:
            try:
                self.embedding_model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
                self.initialized = True
                logger.info(f"Initialized embedding model: {DEFAULT_EMBEDDING_MODEL}")
            except Exception as e:
                logger.error(f"Failed to initialize embedding model: {e}")
        else:
            logger.warning("Semantic mapping features disabled - missing required packages")
    
    def precompute_cre_embeddings(self, cres: List[Dict]) -> bool:
        """
        Precompute embeddings for all CREs to speed up matching.
        
        Args:
            cres: List of CRE objects with ID, name, and description
            
        Returns:
            Success flag
        """
        if not self.initialized:
            logger.warning("Cannot precompute embeddings - engine not initialized")
            return False
            
        try:
            start_time = time.time()
            logger.info(f"Precomputing embeddings for {len(cres)} CREs...")
            
            # Clear existing embeddings
            self.cre_embeddings = {}
            
            # Process in batches to avoid memory issues
            batch_size = 50
            for i in range(0, len(cres), batch_size):
                batch = cres[i:i+batch_size]
                
                # Prepare texts for embedding
                texts = []
                cre_ids = []
                
                for cre in batch:
                    cre_id = cre.get('id')
                    if not cre_id:
                        continue
                        
                    # Combine name and description for better context
                    text = f"{cre.get('name', '')}: {cre.get('description', '')}"
                    if text.strip():
                        texts.append(text)
                        cre_ids.append(cre_id)
                
                if not texts:
                    continue
                    
                # Generate embeddings for batch
                try:
                    batch_embeddings = self.embedding_model.encode(texts)
                    
                    # Store embeddings
                    for idx, cre_id in enumerate(cre_ids):
                        self.cre_embeddings[cre_id] = batch_embeddings[idx]
                except Exception as e:
                    logger.error(f"Error generating embeddings for batch: {e}")
                
                # Log progress for large datasets
                if len(cres) > 100 and (i + batch_size) % 500 == 0:
                    progress = min(i + batch_size, len(cres))
                    logger.info(f"Processed {progress}/{len(cres)} CREs")
            
            duration = time.time() - start_time
            logger.info(f"Finished precomputing {len(self.cre_embeddings)} CRE embeddings in {duration:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Error precomputing CRE embeddings: {e}")
            return False
    
    @lru_cache(maxsize=EMBEDDING_CACHE_SIZE)
    def _get_embedding_cached(self, text: str) -> np.ndarray:
        """
        Get embedding for text with caching.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        if not self.initialized:
            logger.warning("Cannot generate embedding - engine not initialized")
            return np.zeros(768)  # Return zero vector as fallback
            
        try:
            return self.embedding_model.encode(text)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return np.zeros(768)  # Return zero vector on error
    
    def map_standard_control(self, control: Dict) -> List[Tuple[str, float]]:
        """
        Map a standard control to the most relevant CREs using semantic similarity.
        
        Args:
            control: Standard control object with name and description
            
        Returns:
            List of (cre_id, similarity_score) tuples, sorted by score
        """
        if not self.initialized or not self.cre_embeddings:
            logger.warning("Semantic mapping engine not properly initialized")
            return []
        
        try:
            # Generate embedding for control
            control_text = f"{control.get('name', '')}: {control.get('description', '')}"
            control_embedding = self._get_embedding_cached(control_text)
            
            # Find matches with all CREs
            matches = []
            for cre_id, cre_embedding in self.cre_embeddings.items():
                # Calculate cosine similarity
                similarity = cosine_similarity(
                    [control_embedding], 
                    [cre_embedding]
                )[0][0]
                matches.append((cre_id, float(similarity)))
            
            # Sort by similarity (descending)
            matches.sort(key=lambda x: x[1], reverse=True)
            
            return matches
            
        except Exception as e:
            logger.error(f"Error in semantic mapping: {e}")
            return []

class MappingConfidenceEvaluator:
    """Evaluates and enriches mapping confidence using LLMs."""
    
    def __init__(self, threshold=DEFAULT_CONFIDENCE_THRESHOLD, api_key=None):
        """
        Initialize the confidence evaluator.
        
        Args:
            threshold: Confidence threshold (0.0-1.0) for automatic acceptance
            api_key: Optional API key for LLM service
        """
        self.confidence_threshold = threshold
        self.llm_client = None
        self.initialized = False
        
        # Initialize LLM if OpenAI is available
        if OPENAI_AVAILABLE:
            try:
                # Use API key from args or environment
                api_key = api_key or os.environ.get("OPENAI_API_KEY")
                if api_key:
                    self.llm_client = OpenAI(api_key=api_key)
                    self.initialized = True
                else:
                    logger.warning("No OpenAI API key provided")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
    
    async def evaluate_mapping(self, 
                       standard_control: Dict, 
                       cre: Dict, 
                       similarity_score: float) -> Dict:
        """
        Evaluate if a mapping is valid and enrich with explanation.
        
        Args:
            standard_control: Standard control with name and description
            cre: CRE with id, name and description
            similarity_score: Similarity score from embedding comparison
            
        Returns:
            Evaluation result with confidence and reasoning
        """
        # For high confidence matches, accept without LLM verification
        if similarity_score >= self.confidence_threshold:
            return {
                "is_match": True,
                "confidence": similarity_score,
                "reasoning": "Strong semantic similarity",
                "requires_review": False
            }
        
        # For lower confidence, use LLM if available
        if self.initialized and self.llm_client:
            try:
                # Construct prompt for LLM
                prompt = self._create_evaluation_prompt(standard_control, cre)
                
                # Call LLM
                response = self.llm_client.chat.completions.create(
                    model=DEFAULT_LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )
                
                # Parse response
                analysis = response.choices[0].message.content
                is_match = analysis.startswith("MATCH")
                reasoning = analysis.split("\n", 1)[1] if "\n" in analysis else ""
                
                return {
                    "is_match": is_match,
                    "confidence": similarity_score,
                    "reasoning": reasoning,
                    "requires_review": True  # Always require review for LLM-verified mappings
                }
                
            except Exception as e:
                logger.error(f"Error in LLM evaluation: {e}")
        
        # Fallback when LLM is not available or fails
        return {
            "is_match": similarity_score > 0.5,  # Use lower threshold as fallback
            "confidence": similarity_score,
            "reasoning": "Based on embedding similarity only",
            "requires_review": True
        }
    
    def _create_evaluation_prompt(self, standard_control: Dict, cre: Dict) -> str:
        """Create prompt for LLM evaluation."""
        return f"""
        Evaluate whether this standard control is a valid match for this CRE:
        
        STANDARD CONTROL:
        Title: {standard_control.get('name', '')}
        Description: {standard_control.get('description', '')}
        
        COMMON REQUIREMENT ENUMERATION (CRE):
        ID: {cre.get('id') or cre.get('external_id')}
        Name: {cre.get('name', '')}
        Description: {cre.get('description', '')}
        
        Answer with "MATCH" or "NOT_MATCH" followed by your reasoning.
        """
        
    async def generate_cre_suggestion(self, control: Dict) -> Dict:
        """
        Generate a suggestion for a new CRE based on a control.
        
        Args:
            control: Standard control with name and description
            
        Returns:
            Suggested CRE with name, description and tags
        """
        if not self.initialized or not self.llm_client:
            # Fallback when LLM is not available
            return {
                "name": f"[Suggested] {control.get('name', '')}",
                "description": control.get('description', ''),
                "tags": [],
                "potential_relationships": []
            }
            
        try:
            # Create prompt for CRE suggestion
            prompt = f"""
            Create a Common Requirement Enumeration (CRE) based on this control:
            
            STANDARD CONTROL:
            Title: {control.get('name', '')}
            Description: {control.get('description', '')}
            
            Generate a CRE with:
            - A clear name (required)
            - A detailed description (required)
            - Suggested tags (optional)
            - Potential relationships to existing CREs (optional)
            
            Format as JSON with fields: name, description, tags, potential_relationships
            """
            
            # Call LLM
            response = self.llm_client.chat.completions.create(
                model=DEFAULT_LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            # Parse response
            suggestion = json.loads(response.choices[0].message.content)
            return suggestion
            
        except Exception as e:
            logger.error(f"Error generating CRE suggestion: {e}")
            # Fallback
            return {
                "name": f"[Suggested] {control.get('name', '')}",
                "description": control.get('description', ''),
                "tags": [],
                "potential_relationships": []
            } 