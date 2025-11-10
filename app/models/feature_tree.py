"""
Feature Tree data models for parametric CAD history.

The feature tree represents the modeling history as a hierarchical structure
where each node is a CAD operation/feature with parameters and dependencies.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any, Union, Set
from pydantic import BaseModel, Field
from enum import Enum
import uuid
from datetime import datetime


class FeatureType(str, Enum):
    """Types of CAD features/operations"""
    # Base geometry creation
    WORKPLANE = "workplane"
    SKETCH = "sketch"
    EXTRUDE = "extrude"
    REVOLVE = "revolve"
    LOFT = "loft"
    SWEEP = "sweep"
    
    # Primitive shapes
    BOX = "box"
    CYLINDER = "cylinder"
    SPHERE = "sphere"
    CONE = "cone"
    TORUS = "torus"
    
    # Boolean operations
    UNION = "union"
    DIFFERENCE = "difference"
    INTERSECTION = "intersection"
    
    # Modification operations
    FILLET = "fillet"
    CHAMFER = "chamfer"
    MIRROR = "mirror"
    PATTERN_LINEAR = "pattern_linear"
    PATTERN_CIRCULAR = "pattern_circular"
    
    # Assembly operations
    ASSEMBLY_ROOT = "assembly_root"
    COMPONENT = "component"
    CONSTRAINT = "constraint"
    
    # Datum features
    DATUM_PLANE = "datum_plane"
    DATUM_AXIS = "datum_axis"
    DATUM_POINT = "datum_point"


class ParameterType(str, Enum):
    """Types of parameters that can be stored"""
    FLOAT = "float"
    INTEGER = "integer"
    STRING = "string"
    BOOLEAN = "boolean"
    VECTOR3D = "vector3d"
    POINT3D = "point3d"
    ANGLE = "angle"
    LENGTH = "length"


class Parameter(BaseModel):
    """A single parameter for a feature"""
    name: str
    value: Union[float, int, str, bool, List[float]]
    type: ParameterType
    description: Optional[str] = None
    units: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    original_variable_name: Optional[str] = None  # For mapping back to code variables


class FeatureReference(BaseModel):
    """Reference to another feature or geometric entity"""
    feature_id: str
    entity_type: str  # "face", "edge", "vertex", "solid", "feature"
    entity_index: Optional[int] = None  # For multiple entities of same type
    selection_info: Optional[Dict[str, Any]] = None  # Additional selection data


class FeatureNode(BaseModel):
    """A single node in the feature tree representing a CAD operation"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    feature_type: FeatureType
    description: Optional[str] = None
    
    # Parameters for this feature
    parameters: List[Parameter] = Field(default_factory=list)
    
    # References to parent features/entities this depends on
    parent_references: List[FeatureReference] = Field(default_factory=list)
    
    # Child feature IDs that depend on this feature
    child_ids: List[str] = Field(default_factory=list)
    
    # Generated CADQuery code for this specific feature
    code_fragment: Optional[str] = None
    
    # Success/error state
    is_valid: bool = True
    error_message: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Visual properties
    visible: bool = True
    color: Optional[str] = None
    transparency: Optional[float] = None


class FeatureTree(BaseModel):
    """Complete feature tree for a CAD model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    version: int
    name: str = "Feature Tree"
    description: Optional[str] = None
    
    # Root node of the tree (usually ASSEMBLY_ROOT or first solid feature)
    root_node_id: Optional[str] = None
    
    # All nodes in the tree (flat list for easy lookup)
    nodes: Dict[str, FeatureNode] = Field(default_factory=dict)
    
    # Ordered list of node IDs representing regeneration order
    regeneration_order: List[str] = Field(default_factory=list)
    
    # Global parameters that can be referenced by features
    global_parameters: List[Parameter] = Field(default_factory=list)
    
    # Final generated CADQuery code (concatenation of all feature code fragments)
    generated_code: Optional[str] = None
    
    # State flags for Command vs Derivation pattern
    dirty: bool = False  # True when parameters changed but 3D model hasn't been regenerated
    needs_full_regeneration: bool = False  # Structural edits that require full code regeneration
    last_good_artifact_id: Optional[str] = None  # ID of last successfully generated artifact
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    
    def add_node(self, node: FeatureNode, parent_id: Optional[str] = None) -> None:
        """Add a node to the tree and update relationships"""
        self.nodes[node.id] = node
        self.regeneration_order.append(node.id)
        
        if parent_id and parent_id in self.nodes:
            # Add this node as child of parent
            if node.id not in self.nodes[parent_id].child_ids:
                self.nodes[parent_id].child_ids.append(node.id)
        
        if not self.root_node_id:
            self.root_node_id = node.id
        
        self.updated_at = datetime.utcnow()
    
    def remove_node(self, node_id: str) -> None:
        """Remove a node and all its descendants"""
        if node_id not in self.nodes:
            return
        
        node = self.nodes[node_id]
        
        # Recursively remove all children
        for child_id in node.child_ids.copy():
            self.remove_node(child_id)
        
        # Remove from parent's children list
        for other_node in self.nodes.values():
            if node_id in other_node.child_ids:
                other_node.child_ids.remove(node_id)
        
        # Remove from regeneration order
        if node_id in self.regeneration_order:
            self.regeneration_order.remove(node_id)
        
        # Remove the node itself
        del self.nodes[node_id]
        
        # Update root if needed
        if self.root_node_id == node_id:
            self.root_node_id = self.regeneration_order[0] if self.regeneration_order else None
        
        self.updated_at = datetime.utcnow()
    
    def get_node_children(self, node_id: str) -> List[FeatureNode]:
        """Get all child nodes of a given node"""
        if node_id not in self.nodes:
            return []
        
        return [self.nodes[child_id] for child_id in self.nodes[node_id].child_ids 
                if child_id in self.nodes]
    
    def get_node_dependencies(self, node_id: str, visited: Optional[Set[str]] = None) -> List[str]:
        """Get all nodes that this node depends on (directly or indirectly)"""
        if node_id not in self.nodes:
            return []
        
        if visited is None:
            visited = set()
        
        if node_id in visited:
            return []
        
        visited.add(node_id)
        
        dependencies = set()
        node = self.nodes[node_id]
        
        # Add direct parent references
        for ref in node.parent_references:
            if ref.feature_id in self.nodes:
                dependencies.add(ref.feature_id)
                # Recursively add dependencies of dependencies
                dependencies.update(self.get_node_dependencies(ref.feature_id, visited))
        
        return list(dependencies)
    
    def validate_tree(self) -> List[str]:
        """Validate the tree structure and return list of errors"""
        errors = []
        
        # Check for circular dependencies
        for node_id in self.nodes:
            dependencies = self.get_node_dependencies(node_id)
            if node_id in dependencies:
                errors.append(f"Circular dependency detected for node {node_id}")
        
        # Check that all referenced nodes exist
        for node in self.nodes.values():
            for ref in node.parent_references:
                if ref.feature_id not in self.nodes:
                    errors.append(f"Node {node.id} references non-existent node {ref.feature_id}")
        
        # Check regeneration order contains all nodes
        if set(self.regeneration_order) != set(self.nodes.keys()):
            errors.append("Regeneration order doesn't match node list")
        
        return errors


class FeatureTreeOperation(BaseModel):
    """Represents an operation to modify the feature tree"""
    operation_type: str  # "add", "remove", "modify", "reorder"
    node_id: Optional[str] = None
    node_data: Optional[FeatureNode] = None
    parent_id: Optional[str] = None
    new_order: Optional[List[str]] = None
    parameter_changes: Optional[Dict[str, Any]] = None


class FeatureTreeHistory(BaseModel):
    """History of changes to a feature tree"""
    tree_id: str
    operations: List[FeatureTreeOperation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
