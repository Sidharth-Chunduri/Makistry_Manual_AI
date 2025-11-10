"""
Feature Tree storage backend for Makistry.

Provides CRUD operations for feature trees using Firestore.
Integrates with the existing GCP storage layer.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from google.cloud import firestore
from google.api_core.datetime_helpers import DatetimeWithNanoseconds

from app.models.feature_tree import (
    FeatureTree, FeatureNode, FeatureTreeOperation, FeatureTreeHistory,
    Parameter, FeatureReference
)
from app.services.gcp_clients import get_firestore_client
from app.core.config import settings


class FeatureTreeStorage:
    """Storage operations for feature trees"""
    
    def __init__(self):
        self.db = get_firestore_client()
        self.collection = "feature_trees"
        self.history_collection = "feature_tree_history"
    
    def create_feature_tree(self, project_id: str, user_id: str, name: str = "Feature Tree") -> FeatureTree:
        """Create a new feature tree for a project"""
        tree = FeatureTree(
            project_id=project_id,
            version=1,
            name=name,
            created_by=user_id
        )
        
        doc_id = f"{project_id}_v{tree.version}"
        doc_data = self._serialize_tree(tree)
        
        self.db.collection(self.collection).document(doc_id).set(doc_data)
        
        return tree
    
    def get_feature_tree(self, project_id: str, version: Optional[int] = None) -> Optional[FeatureTree]:
        """Get feature tree for a project (latest version if version not specified)"""
        if version:
            doc_id = f"{project_id}_v{version}"
            doc = self.db.collection(self.collection).document(doc_id).get()
            if doc.exists:
                return self._deserialize_tree(doc.to_dict())
        else:
            # Get latest version - avoid composite index requirement
            try:
                query = self.db.collection(self.collection).where("project_id", "==", project_id)
                docs = list(query.stream())
                
                if not docs:
                    return None
                
                # Sort by version in Python to avoid Firestore composite index requirement
                sorted_docs = sorted(docs, key=lambda d: d.to_dict().get("version", 0), reverse=True)
                return self._deserialize_tree(sorted_docs[0].to_dict())
            except Exception as e:
                # Log the error and return None instead of crashing
                print(f"Error retrieving feature tree for project {project_id}: {e}")
                return None
        
        return None
    
    def save_feature_tree(self, tree: FeatureTree) -> None:
        """Save/update a feature tree"""
        tree.updated_at = datetime.utcnow()
        doc_id = f"{tree.project_id}_v{tree.version}"
        doc_data = self._serialize_tree(tree)
        
        self.db.collection(self.collection).document(doc_id).set(doc_data)
    
    def create_new_version(self, tree: FeatureTree, user_id: str) -> FeatureTree:
        """Create a new version of the feature tree"""
        new_tree = FeatureTree(**tree.dict())
        new_tree.id = None  # Generate new ID
        new_tree.version += 1
        new_tree.created_at = datetime.utcnow()
        new_tree.updated_at = datetime.utcnow()
        new_tree.created_by = user_id
        
        self.save_feature_tree(new_tree)
        return new_tree
    
    def list_versions(self, project_id: str) -> List[Dict[str, Any]]:
        """List all versions of feature trees for a project"""
        try:
            query = self.db.collection(self.collection).where("project_id", "==", project_id)
            docs = list(query.stream())
            
            versions = []
            for doc in docs:
                data = doc.to_dict()
                versions.append({
                    "version": data.get("version", 1),
                    "name": data.get("name", "Feature Tree"),
                    "created_at": data.get("created_at"),
                    "created_by": data.get("created_by", ""),
                    "node_count": len(data.get("nodes", {}))
                })
            
            # Sort by version descending in Python
            versions.sort(key=lambda v: v["version"], reverse=True)
            return versions
        except Exception as e:
            print(f"Error listing feature tree versions for project {project_id}: {e}")
            return []
    
    def add_node_to_tree(self, project_id: str, node: FeatureNode, 
                        parent_id: Optional[str] = None, version: Optional[int] = None) -> FeatureTree:
        """Add a node to the feature tree with comprehensive validation"""
        tree = self.get_feature_tree(project_id, version)
        if not tree:
            raise ValueError(f"Feature tree not found for project {project_id}")
        
        # ENHANCED VALIDATION: Use the new validator to prevent illegal node additions
        from app.services.feature_tree_validator import feature_tree_validator
        
        # Ensure dependency reference is recorded if parent provided but no explicit reference set
        if parent_id and parent_id in tree.nodes:
            has_parent_ref = any(ref.feature_id == parent_id for ref in node.parent_references)
            if not has_parent_ref:
                node.parent_references.append(FeatureReference(
                    feature_id=parent_id,
                    entity_type="feature"
                ))
        
        # CRITICAL: Validate the node addition before actually adding it
        # Skip validation for special design parameter nodes created during code generation
        if not ("design_params" in node.id and node.name == "Design Parameters"):
            is_valid, validation_errors = feature_tree_validator.validate_node_addition(tree, node, parent_id)
            if not is_valid:
                # Include suggestions for valid additions
                suggestions = feature_tree_validator.suggest_valid_additions(tree, parent_id)
                suggestion_text = ""
                if suggestions:
                    suggestion_text = f"\n\nSuggested alternatives:\n" + "\n".join([
                        f"- {s['type']}: {s['reason']}" for s in suggestions[:3]
                    ])
                
                raise ValueError(f"Invalid node addition: {', '.join(validation_errors)}{suggestion_text}")
        
        # Add node to tree (this validates for circular dependencies)
        tree.add_node(node, parent_id)
        
        # Basic tree validation (backup check)
        basic_validation_errors = tree.validate_tree()
        if basic_validation_errors:
            raise ValueError(f"Tree validation failed after adding node: {', '.join(basic_validation_errors)}")
        
        # Mark tree state - use more granular regeneration logic
        tree.dirty = True  # mark tree as requiring regeneration to incorporate new node
        
        # Only require full regeneration for structural changes
        is_structural_change = (
            node.feature_type in ['workplane', 'sketch', 'assembly_root'] or
            len(tree.nodes) == 1  # First node
        )
        tree.needs_full_regeneration = is_structural_change
        
        self.save_feature_tree(tree)
        
        # Log the operation
        self._log_operation(tree.id, FeatureTreeOperation(
            operation_type="add",
            node_id=node.id,
            node_data=node,
            parent_id=parent_id
        ))
        
        return tree
    
    def remove_node_from_tree(self, project_id: str, node_id: str, 
                             version: Optional[int] = None) -> FeatureTree:
        """Remove a node from the feature tree"""
        tree = self.get_feature_tree(project_id, version)
        if not tree:
            raise ValueError(f"Feature tree not found for project {project_id}")
        
        if node_id not in tree.nodes:
            raise ValueError(f"Node {node_id} not found in tree")
        
        # Store the node before removal for logging
        removed_node = tree.nodes[node_id]
        
        tree.remove_node(node_id)
        tree.dirty = True
        tree.needs_full_regeneration = True
        self.save_feature_tree(tree)
        
        # Log the operation
        self._log_operation(tree.id, FeatureTreeOperation(
            operation_type="remove",
            node_id=node_id,
            node_data=removed_node
        ))
        
        return tree
    
    def update_node_in_tree(self, project_id: str, node_id: str, 
                           parameter_changes: Dict[str, Any],
                           version: Optional[int] = None) -> FeatureTree:
        """Update a node's parameters in the feature tree"""
        tree = self.get_feature_tree(project_id, version)
        if not tree:
            raise ValueError(f"Feature tree not found for project {project_id}")
        
        if node_id not in tree.nodes:
            raise ValueError(f"Node {node_id} not found in tree")
        
        node = tree.nodes[node_id]
        
        # Apply parameter changes
        for param_name, new_value in parameter_changes.items():
            for param in node.parameters:
                if param.name == param_name:
                    param.value = new_value
                    break
        
        node.updated_at = datetime.utcnow()
        tree.updated_at = datetime.utcnow()
        
        self.save_feature_tree(tree)
        
        # Log the operation
        self._log_operation(tree.id, FeatureTreeOperation(
            operation_type="modify",
            node_id=node_id,
            parameter_changes=parameter_changes
        ))
        
        return tree
    
    def reorder_nodes(self, project_id: str, new_order: List[str], 
                     version: Optional[int] = None) -> FeatureTree:
        """Reorder the regeneration sequence of nodes"""
        tree = self.get_feature_tree(project_id, version)
        if not tree:
            raise ValueError(f"Feature tree not found for project {project_id}")
        
        # Validate that all node IDs exist
        if set(new_order) != set(tree.nodes.keys()):
            raise ValueError("New order must contain exactly the same nodes")
        
        old_order = tree.regeneration_order.copy()
        tree.regeneration_order = new_order
        tree.dirty = True
        tree.needs_full_regeneration = True
        tree.updated_at = datetime.utcnow()
        
        self.save_feature_tree(tree)
        
        # Log the operation
        self._log_operation(tree.id, FeatureTreeOperation(
            operation_type="reorder",
            new_order=new_order
        ))
        
        return tree
    
    def get_tree_history(self, tree_id: str) -> Optional[FeatureTreeHistory]:
        """Get the operation history for a feature tree"""
        doc = self.db.collection(self.history_collection).document(tree_id).get()
        if doc.exists:
            data = doc.to_dict()
            return FeatureTreeHistory(
                tree_id=tree_id,
                operations=[FeatureTreeOperation(**op) for op in data.get("operations", [])],
                created_at=data.get("created_at", datetime.utcnow())
            )
        return None
    
    def delete_feature_tree(self, project_id: str, version: Optional[int] = None) -> bool:
        """Delete a feature tree version"""
        if version:
            doc_id = f"{project_id}_v{version}"
            self.db.collection(self.collection).document(doc_id).delete()
            return True
        else:
            # Delete all versions
            query = self.db.collection(self.collection).where("project_id", "==", project_id)
            deleted = False
            for doc in query.stream():
                doc.reference.delete()
                deleted = True
            return deleted
    
    def _serialize_tree(self, tree: FeatureTree) -> Dict[str, Any]:
        """Convert FeatureTree to Firestore document"""
        data = tree.dict()
        
        # Convert datetime objects to Firestore timestamps
        if isinstance(data["created_at"], datetime):
            data["created_at"] = data["created_at"]
        if isinstance(data["updated_at"], datetime):
            data["updated_at"] = data["updated_at"]
        
        # Convert nodes dict for storage
        nodes_data = {}
        for node_id, node in data["nodes"].items():
            node_dict = node.dict() if hasattr(node, 'dict') else node
            # Convert datetime in nodes
            if isinstance(node_dict.get("created_at"), datetime):
                node_dict["created_at"] = node_dict["created_at"]
            if isinstance(node_dict.get("updated_at"), datetime):
                node_dict["updated_at"] = node_dict["updated_at"]
            nodes_data[node_id] = node_dict
        
        data["nodes"] = nodes_data
        
        return data
    
    def _deserialize_tree(self, data: Dict[str, Any]) -> FeatureTree:
        """Convert Firestore document to FeatureTree"""
        try:
            # Convert Firestore timestamps back to datetime
            if isinstance(data.get("created_at"), DatetimeWithNanoseconds):
                data["created_at"] = datetime.fromtimestamp(data["created_at"].timestamp())
            if isinstance(data.get("updated_at"), DatetimeWithNanoseconds):
                data["updated_at"] = datetime.fromtimestamp(data["updated_at"].timestamp())
            
            # Ensure required fields have defaults
            data.setdefault("nodes", {})
            data.setdefault("regeneration_order", [])
            data.setdefault("global_parameters", [])
            
            # Convert nodes back to FeatureNode objects
            nodes = {}
            for node_id, node_data in data.get("nodes", {}).items():
                try:
                    # Ensure node_data is a dict
                    if not isinstance(node_data, dict):
                        print(f"Warning: Invalid node data for {node_id}, skipping")
                        continue
                    
                    # Convert timestamps in nodes
                    if isinstance(node_data.get("created_at"), DatetimeWithNanoseconds):
                        node_data["created_at"] = datetime.fromtimestamp(node_data["created_at"].timestamp())
                    if isinstance(node_data.get("updated_at"), DatetimeWithNanoseconds):
                        node_data["updated_at"] = datetime.fromtimestamp(node_data["updated_at"].timestamp())
                    
                    # Ensure required fields exist
                    node_data.setdefault("parameters", [])
                    node_data.setdefault("parent_references", [])
                    node_data.setdefault("child_ids", [])
                    
                    # Convert parameters and references safely
                    if "parameters" in node_data and isinstance(node_data["parameters"], list):
                        node_data["parameters"] = [Parameter(**p) for p in node_data["parameters"] if isinstance(p, dict)]
                    if "parent_references" in node_data and isinstance(node_data["parent_references"], list):
                        node_data["parent_references"] = [FeatureReference(**r) for r in node_data["parent_references"] if isinstance(r, dict)]
                    
                    nodes[node_id] = FeatureNode(**node_data)
                except Exception as e:
                    print(f"Warning: Failed to deserialize node {node_id}: {e}")
                    continue
            
            data["nodes"] = nodes
            
            # Convert global parameters safely
            if "global_parameters" in data and isinstance(data["global_parameters"], list):
                data["global_parameters"] = [Parameter(**p) for p in data["global_parameters"] if isinstance(p, dict)]
            
            return FeatureTree(**data)
        except Exception as e:
            print(f"Error in _deserialize_tree: {e}")
            print(f"Data keys: {list(data.keys()) if data else 'None'}")
            raise
    
    def _log_operation(self, tree_id: str, operation: FeatureTreeOperation) -> None:
        """Log an operation to the feature tree history"""
        doc_ref = self.db.collection(self.history_collection).document(tree_id)
        
        # Get existing history or create new
        doc = doc_ref.get()
        if doc.exists:
            history_data = doc.to_dict()
            operations = history_data.get("operations", [])
        else:
            operations = []
            history_data = {
                "tree_id": tree_id,
                "created_at": datetime.utcnow()
            }
        
        # Add new operation
        op_data = operation.dict()
        if operation.node_data is not None:
            # Preserve the serialized node data as plain dict
            op_data["node_data"] = operation.node_data.dict()
        
        operations.append(op_data)
        history_data["operations"] = operations
        
        doc_ref.set(history_data)


# Global instance
feature_tree_storage = FeatureTreeStorage()
