"""
Database extensions for AI-powered mapping functionality.
Extends the existing database interfaces with AI mapping capabilities.
"""

import logging
import uuid
import json
import datetime
from typing import List, Dict, Any, Optional, Union

# Set up logging
logger = logging.getLogger(__name__)

class AIMappingDatabaseExtension:
    """Extension methods for the database to support AI mapping."""
    
    @staticmethod
    async def extend_db_interface(db_interface):
        """
        Extend database interface with AI mapping methods.
        
        Args:
            db_interface: Existing database interface to extend
        """
        # Add methods to db_interface
        db_interface.get_all_cres = AIMappingDatabaseExtension.get_all_cres.__get__(db_interface)
        db_interface.get_cre_by_id = AIMappingDatabaseExtension.get_cre_by_id.__get__(db_interface)
        db_interface.save_ai_mappings = AIMappingDatabaseExtension.save_ai_mappings.__get__(db_interface)
        db_interface.save_cre_suggestions = AIMappingDatabaseExtension.save_cre_suggestions.__get__(db_interface)
        db_interface.get_ai_mapping_history = AIMappingDatabaseExtension.get_ai_mapping_history.__get__(db_interface)
        
        return db_interface
    
    @staticmethod
    async def get_all_cres() -> List[Dict]:
        """
        Get all CREs from database.
        
        Returns:
            List of CRE objects
        """
        try:
            from application.database import db
            from application.defs import cre_defs
            
            db_instance = db.Node_collection()
            cres = db_instance.get_CREs()
            
            # Convert to dict format
            result = []
            for cre in cres:
                result.append({
                    "id": cre.external_id,
                    "name": cre.name,
                    "description": cre.description,
                    "tags": cre.tags.split(',') if cre.tags else []
                })
                
            return result
            
        except Exception as e:
            logger.error(f"Error getting all CREs: {e}")
            return []
    
    @staticmethod
    async def get_cre_by_id(cre_id: str) -> Optional[Dict]:
        """
        Get CRE by ID.
        
        Args:
            cre_id: CRE ID to find
            
        Returns:
            CRE object if found, None otherwise
        """
        try:
            from application.database import db
            from application.defs import cre_defs
            
            db_instance = db.Node_collection()
            cres = db_instance.get_CREs(external_id=cre_id)
            
            if not cres:
                # Try by database ID
                try:
                    cres = [db_instance.get_node_by_id(cre_id)]
                except:
                    return None
            
            if cres and len(cres) > 0:
                cre = cres[0]
                return {
                    "id": cre.external_id,
                    "name": cre.name,
                    "description": cre.description,
                    "tags": cre.tags.split(',') if cre.tags else []
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting CRE by ID: {e}")
            return None
    
    @staticmethod
    async def save_ai_mappings(mappings: List[Dict], standard_name: str, user_id: Optional[str] = None) -> bool:
        """
        Save AI-generated mappings to database.
        
        Args:
            mappings: List of approved mappings
            standard_name: Name of the standard
            user_id: Optional user ID for tracking
            
        Returns:
            Success flag
        """
        if not mappings:
            logger.warning("No mappings to save")
            return False
            
        try:
            # Save each mapping as a relationship
            for mapping in mappings:
                control = mapping.get('control', {})
                cre = mapping.get('cre', {})
                
                if not control or not cre:
                    continue
                
                # Get CRE ID
                cre_id = cre.get('id') or cre.get('external_id')
                if not cre_id:
                    continue
                    
                # Create control node if it doesn't exist
                control_name = control.get('name') or f"{standard_name} {control.get('id', '')}"
                control_section = control.get('id') or control.get('section', '')
                
                from application.database import db
                db_instance = db.Node_collection()
                
                control_nodes = db_instance.get_nodes(
                    name=standard_name,
                    section=control_section
                )
                
                control_node_id = None
                if control_nodes:
                    # Use existing node
                    control_node_id = str(control_nodes[0].id)
                else:
                    # Create new node
                    import datetime
                    import json
                    
                    control_node = db_instance.add_node(
                        name=standard_name,
                        description=control.get('description', ''),
                        section=control_section,
                        sectionID=control.get('id', ''),
                        metadata=json.dumps({
                            "ai_generated": True,
                            "standard": standard_name,
                            "created_by": user_id,
                            "created_at": datetime.datetime.now().isoformat()
                        })
                    )
                    control_node_id = str(control_node.id)
                
                if not control_node_id:
                    logger.error(f"Failed to get or create control node for {control_name}")
                    continue
                
                # Add relationship
                confidence = mapping.get('confidence', 0.0)
                reasoning = mapping.get('reasoning', '')
                
                db_instance.add_relationship(
                    source_id=control_node_id,
                    target_id=cre_id,
                    relationship_type="implements",
                    metadata=json.dumps({
                        "ai_generated": True,
                        "confidence": confidence,
                        "reasoning": reasoning,
                        "approved_by": user_id,
                        "created_at": datetime.datetime.now().isoformat()
                    })
                )
                
                logger.info(f"Added relationship: {control_name} implements CRE {cre_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving AI mappings: {e}")
            return False
    
    @staticmethod
    async def save_cre_suggestions(suggestions: List[Dict], standard_name: str, user_id: Optional[str] = None) -> bool:
        """
        Save suggested new CREs to database.
        
        Args:
            suggestions: List of suggested CRE objects
            standard_name: Name of the standard that generated these suggestions
            user_id: Optional user ID for tracking
            
        Returns:
            Success flag
        """
        if not suggestions:
            logger.warning("No CRE suggestions to save")
            return False
            
        try:
            import datetime
            import json
            from application.database import db
            from application.defs import cre_defs
            
            db_instance = db.Node_collection()
            
            # Save each suggestion
            for suggestion in suggestions:
                # Generate a temporary external ID for the suggested CRE
                import uuid
                temp_id = f"SUGGESTED-{uuid.uuid4().hex[:8]}"
                
                # Create CRE node
                cre_node = db_instance.add_node(
                    name=suggestion.get('name', 'Suggested CRE'),
                    description=suggestion.get('description', ''),
                    external_id=temp_id,
                    ntype=cre_defs.Credoctypes.CRE.value,
                    metadata=json.dumps({
                        "ai_generated": True,
                        "suggested_from_standard": standard_name,
                        "created_by": user_id,
                        "created_at": datetime.datetime.now().isoformat(),
                        "status": "suggested",
                        "tags": suggestion.get('tags', []),
                        "potential_relationships": suggestion.get('potential_relationships', [])
                    })
                )
                
                logger.info(f"Added suggested CRE: {suggestion.get('name')} with ID {temp_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving CRE suggestions: {e}")
            return False
    
    @staticmethod
    async def get_ai_mapping_history(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        Get history of AI-generated mappings.
        
        Args:
            user_id: Optional user ID to filter by
            limit: Maximum number of results
            
        Returns:
            List of mapping history entries
        """
        try:
            # Get relationships with AI metadata
            query = """
                MATCH (source)-[r]->(target)
                WHERE r.metadata CONTAINS 'ai_generated'
                RETURN source, r, target
                ORDER BY r.created_at DESC
                LIMIT ?
            """
            
            # Execute query
            results = self.execute_query(query, (limit,))
            
            # Format results
            history = []
            for result in results:
                source_node = result["source"]
                relationship = result["r"]
                target_node = result["target"]
                
                # Parse metadata
                try:
                    metadata = json.loads(relationship.get("metadata", "{}"))
                except json.JSONDecodeError:
                    metadata = {}
                
                # Only include if approved by the specified user
                if user_id and metadata.get("approved_by") != user_id:
                    continue
                
                history.append({
                    "source": {
                        "id": source_node.id,
                        "name": source_node.name,
                        "description": source_node.description
                    },
                    "target": {
                        "id": target_node.id,
                        "name": target_node.name,
                        "description": target_node.description
                    },
                    "relationship": {
                        "type": relationship.type,
                        "confidence": metadata.get("confidence", 0.0),
                        "reasoning": metadata.get("reasoning", ""),
                        "created_at": metadata.get("created_at", ""),
                        "approved_by": metadata.get("approved_by", "")
                    }
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting AI mapping history: {e}")
            return [] 