"""
Standard Mapper - Main orchestrator for the AI-based mapping process.
Coordinates between the embedding engine, LLM evaluation, and database operations.
"""

import logging
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from .semantic_mapping import SemanticMappingEngine, MappingConfidenceEvaluator
import time
import functools
from concurrent.futures import ThreadPoolExecutor

# Set up logging
logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 20  # Process controls in batches of 20
MAX_WORKERS = 5  # Maximum number of concurrent workers

class StandardMapper:
    """
    Comprehensive mapper for standards to CREs using AI techniques.
    Orchestrates the mapping process from start to finish.
    """
    
    def __init__(self, db_connection, api_key=None):
        """
        Initialize the standard mapper.
        
        Args:
            db_connection: Database connection for accessing CREs and standards
            api_key: Optional API key for LLM service
        """
        self.db = db_connection
        self.mapping_engine = SemanticMappingEngine()
        self.evaluator = MappingConfidenceEvaluator(api_key=api_key)
        self.initialized = False
        self._cre_cache = {}  # Cache for CREs to reduce database calls
        
    async def initialize(self):
        """
        Load and precompute CRE embeddings.
        Should be called before mapping standards.
        """
        try:
            # Load all CREs from database
            from application.ai_mapping.db_extensions import AIMappingDatabaseExtension
            cres = await AIMappingDatabaseExtension.get_all_cres()
            
            if not cres:
                logger.warning("No CREs found in database")
                return False
            
            # Cache CREs by ID
            for cre in cres:
                cre_id = cre.get('id')
                if cre_id:
                    self._cre_cache[cre_id] = cre
                
            # Precompute embeddings
            self.mapping_engine.precompute_cre_embeddings(cres)
            self.initialized = True
            logger.info("StandardMapper initialization complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize StandardMapper: {e}")
            return False
            
    async def map_standard(self, 
                    standard_name: str, 
                    standard_controls: List[Dict]) -> Dict:
        """
        Map an entire standard to CREs.
        
        Args:
            standard_name: Name of the standard
            standard_controls: List of controls in the standard
            
        Returns:
            Mapping results with mapped controls, unmapped controls, and suggestions
        """
        if not self.initialized:
            success = await self.initialize()
            if not success:
                logger.error("StandardMapper initialization failed")
                return self._create_error_result(standard_name)
                
        # Prepare result structure
        results = {
            "standard": standard_name,
            "mapped_controls": [],
            "unmapped_controls": [],
            "suggested_new_cres": [],
            "summary": {
                "total_controls": len(standard_controls),
                "mapped_count": 0,
                "unmapped_count": 0,
                "high_confidence_count": 0,
                "requires_review_count": 0,
                "processing_time": 0
            }
        }
        
        start_time = time.time()
        
        # Process controls in batches for better performance
        for i in range(0, len(standard_controls), BATCH_SIZE):
            batch = standard_controls[i:i + BATCH_SIZE]
            
            # Process batch in parallel
            batch_tasks = []
            for control in batch:
                task = asyncio.create_task(self._process_control(control, results))
                batch_tasks.append(task)
                
            # Wait for all tasks in batch to complete
            await asyncio.gather(*batch_tasks)
            
            # Log progress
            processed = min(i + BATCH_SIZE, len(standard_controls))
            logger.info(f"Processed {processed}/{len(standard_controls)} controls")
                
        # Update summary statistics
        results["summary"]["mapped_count"] = len(results["mapped_controls"])
        results["summary"]["unmapped_count"] = len(results["unmapped_controls"])
        results["summary"]["high_confidence_count"] = len([
            m for m in results["mapped_controls"] 
            if not m.get("requires_review", True)
        ])
        results["summary"]["requires_review_count"] = len([
            m for m in results["mapped_controls"] 
            if m.get("requires_review", True)
        ])
        results["summary"]["processing_time"] = round(time.time() - start_time, 2)
        
        return results
    
    async def _process_control(self, control: Dict, results: Dict) -> None:
        """
        Process a single control for mapping.
        
        Args:
            control: The control to process
            results: Results dictionary to update
        """
        try:
            # Get candidate matches
            matches = self.mapping_engine.map_standard_control(control)
            
            # No good matches found
            if not matches or matches[0][1] < 0.5:
                await self._handle_unmapped_control(control, results)
                return
                
            # Get best match
            top_cre_id, similarity = matches[0]
            
            # Try to get from cache first
            top_cre = self._cre_cache.get(top_cre_id)
            
            # If not in cache, get from database
            if not top_cre:
                from application.ai_mapping.db_extensions import AIMappingDatabaseExtension
                top_cre = await AIMappingDatabaseExtension.get_cre_by_id(top_cre_id)
                
                # Add to cache
                if top_cre:
                    self._cre_cache[top_cre_id] = top_cre
            
            if not top_cre:
                logger.warning(f"CRE {top_cre_id} not found in database")
                await self._handle_unmapped_control(control, results)
                return
                
            # Evaluate mapping confidence
            evaluation = await self.evaluator.evaluate_mapping(
                control, top_cre, similarity
            )
            
            # Process based on evaluation result
            if evaluation["is_match"]:
                self._add_mapped_control(control, top_cre, evaluation, results)
            else:
                # Try next best match if available
                if len(matches) > 1 and matches[1][1] > 0.6:
                    second_cre_id, second_similarity = matches[1]
                    
                    # Try cache first
                    second_cre = self._cre_cache.get(second_cre_id)
                    
                    # If not in cache, get from database
                    if not second_cre:
                        from application.ai_mapping.db_extensions import AIMappingDatabaseExtension
                        second_cre = await AIMappingDatabaseExtension.get_cre_by_id(second_cre_id)
                        
                        # Add to cache
                        if second_cre:
                            self._cre_cache[second_cre_id] = second_cre
                    
                    if second_cre:
                        second_evaluation = await self.evaluator.evaluate_mapping(
                            control, second_cre, second_similarity
                        )
                        
                        if second_evaluation["is_match"]:
                            self._add_mapped_control(
                                control, second_cre, second_evaluation, results
                            )
                            return
                
                # If still no match, consider it unmapped
                await self._handle_unmapped_control(control, results, 
                                           attempted_cre=top_cre,
                                           reason=evaluation["reasoning"])
        except Exception as e:
            logger.error(f"Error processing control {control.get('name')}: {e}")
            await self._handle_unmapped_control(control, results, 
                                     reason=f"Processing error: {str(e)}")
    
    async def _handle_unmapped_control(self, 
                              control: Dict, 
                              results: Dict,
                              attempted_cre: Dict = None,
                              reason: str = None) -> None:
        """
        Handle an unmapped control by generating a CRE suggestion.
        
        Args:
            control: The control that couldn't be mapped
            results: Results dictionary to update
            attempted_cre: Optional CRE that was attempted but failed
            reason: Optional reason for mapping failure
        """
        # Add to unmapped controls
        unmapped_entry = {
            "control": control,
            "reason": reason or "No suitable CRE found"
        }
        
        if attempted_cre:
            unmapped_entry["attempted_cre"] = attempted_cre
            
        results["unmapped_controls"].append(unmapped_entry)
        
        # Generate CRE suggestion
        try:
            suggested_cre = await self.evaluator.generate_cre_suggestion(control)
            if suggested_cre:
                results["suggested_new_cres"].append(suggested_cre)
        except Exception as e:
            logger.error(f"Failed to generate CRE suggestion: {e}")
    
    def _add_mapped_control(self, 
                          control: Dict, 
                          cre: Dict, 
                          evaluation: Dict,
                          results: Dict) -> None:
        """
        Add a mapped control to the results.
        
        Args:
            control: The mapped control
            cre: The matched CRE
            evaluation: The mapping evaluation results
            results: Results dictionary to update
        """
        results["mapped_controls"].append({
            "control": control,
            "cre": cre,
            "confidence": evaluation["confidence"],
            "reasoning": evaluation["reasoning"],
            "requires_review": evaluation["requires_review"]
        })
    
    def _create_error_result(self, standard_name: str) -> Dict:
        """Create an error result when mapping fails."""
        return {
            "standard": standard_name,
            "error": "Failed to initialize mapping engine",
            "mapped_controls": [],
            "unmapped_controls": [],
            "suggested_new_cres": [],
            "summary": {
                "total_controls": 0,
                "mapped_count": 0,
                "unmapped_count": 0,
                "high_confidence_count": 0,
                "requires_review_count": 0,
                "error": True
            }
        }
        
    async def save_mapping_results(self, results: Dict, user_id: str = None) -> bool:
        """
        Save mapping results to database.
        
        Args:
            results: Mapping results to save
            user_id: Optional user ID for tracking
            
        Returns:
            Success flag
        """
        try:
            # Save only approved mappings
            approved_mappings = [
                m for m in results["mapped_controls"] 
                if not m.get("requires_review") or m.get("user_approved")
            ]
            
            # Import db_extensions module
            from application.ai_mapping.db_extensions import AIMappingDatabaseExtension
            
            # Save mappings to database
            await AIMappingDatabaseExtension.save_ai_mappings(
                approved_mappings, 
                results["standard"],
                user_id
            )
                
            # Save CRE suggestions if any
            if results["suggested_new_cres"]:
                await AIMappingDatabaseExtension.save_cre_suggestions(
                    results["suggested_new_cres"],
                    results["standard"],
                    user_id
                )
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to save mapping results: {e}")
            return False 