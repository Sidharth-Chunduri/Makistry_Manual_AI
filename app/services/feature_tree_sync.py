"""
Feature Tree Synchronization Service.

Handles synchronizing feature trees with CAD code changes made through chat edits.
"""
import logging
from typing import Optional

from app.services.feature_tree_parser import parse_cadquery_code
from app.services.feature_tree_storage import FeatureTreeStorage
from app.services.parameter_value_extractor import update_feature_tree_with_actual_values

logger = logging.getLogger(__name__)


class FeatureTreeSyncService:
    """Service for keeping feature trees in sync with CAD code changes"""
    
    def __init__(self):
        self.storage = FeatureTreeStorage()
    
    def sync_feature_tree_from_code(self, 
                                  project_id: str, 
                                  user_id: str, 
                                  cad_code: str,
                                  cad_version: int,
                                  session_id: Optional[str] = None) -> bool:
        """
        Synchronize feature tree with edited CAD code.
        
        Args:
            project_id: Project identifier
            user_id: User making the change
            cad_code: The updated CAD code
            cad_version: Version of the CAD code
            session_id: Session identifier for tracking
            
        Returns:
            True if sync was successful, False otherwise
        """
        try:
            logger.info(f"Synchronizing feature tree for project {project_id} with CAD version {cad_version}")
            
            # Parse the CAD code into a new feature tree
            feature_tree = parse_cadquery_code(cad_code, project_id, user_id)
            
            # Update feature tree parameters with actual values from the code
            update_feature_tree_with_actual_values(feature_tree, cad_code)
            
            # Add metadata about the sync
            feature_tree.description = f"Synchronized with CAD code version {cad_version}"
            feature_tree.name = "Chat-Edited CAD Model"
            feature_tree.version = cad_version  # Keep feature tree version in sync with CAD version
            
            # Add design parameters node (if any exist in the code)
            self._add_design_parameters_node(feature_tree, cad_code)
            
            # Save the synchronized feature tree
            self.storage.save_feature_tree(feature_tree)
            
            logger.info(f"Successfully synchronized feature tree with {len(feature_tree.nodes)} nodes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync feature tree for project {project_id}: {e}")
            # Don't raise the exception - feature tree sync should not break the main chat flow
            return False
    
    def _add_design_parameters_node(self, feature_tree, cad_code: str) -> None:
        """Add design parameters node if parameters are found in the code"""
        try:
            from app.services.cad_generation_integration import CADGenerationService
            service = CADGenerationService()
            service._add_design_parameters_node(feature_tree, cad_code)
        except Exception as e:
            logger.warning(f"Could not add design parameters node: {e}")


# Global instance
feature_tree_sync = FeatureTreeSyncService()