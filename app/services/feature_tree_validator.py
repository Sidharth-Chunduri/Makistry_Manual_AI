"""
Feature Tree Validation Service.

This service provides comprehensive validation for feature tree operations,
ensuring that nodes added to the tree will actually affect the final model.
"""
import logging
from typing import Dict, List, Optional, Set, Tuple
from app.models.feature_tree import FeatureTree, FeatureNode, FeatureType, FeatureReference

logger = logging.getLogger(__name__)


class FeatureTreeValidator:
    """Validates feature tree operations and node additions"""
    
    def __init__(self):
        self.valid_parent_types: Dict[FeatureType, Set[FeatureType]] = {
            # Sketches can only be created on workplanes or solid faces
            FeatureType.SKETCH: {
                FeatureType.WORKPLANE,
                FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE,
                FeatureType.EXTRUDE, FeatureType.REVOLVE
            },
            
            # Extrude/revolve operations need sketches as input
            FeatureType.EXTRUDE: {FeatureType.SKETCH},
            FeatureType.REVOLVE: {FeatureType.SKETCH},
            
            # Primitives need workplanes
            FeatureType.BOX: {FeatureType.WORKPLANE},
            FeatureType.CYLINDER: {FeatureType.WORKPLANE},
            FeatureType.SPHERE: {FeatureType.WORKPLANE},
            
            # Surface operations need solids
            FeatureType.FILLET: {
                FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE,
                FeatureType.EXTRUDE, FeatureType.REVOLVE,
                FeatureType.UNION, FeatureType.DIFFERENCE
            },
            FeatureType.CHAMFER: {
                FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE,
                FeatureType.EXTRUDE, FeatureType.REVOLVE,
                FeatureType.UNION, FeatureType.DIFFERENCE
            },
            
            # Boolean operations need two solids
            FeatureType.UNION: {
                FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE,
                FeatureType.EXTRUDE, FeatureType.REVOLVE
            },
            FeatureType.DIFFERENCE: {
                FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE,
                FeatureType.EXTRUDE, FeatureType.REVOLVE
            },
        }
        
        self.solid_types = {
            FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE,
            FeatureType.EXTRUDE, FeatureType.REVOLVE,
            FeatureType.UNION, FeatureType.DIFFERENCE
        }
        
        self.surface_operation_types = {FeatureType.FILLET, FeatureType.CHAMFER}
        self.boolean_operation_types = {FeatureType.UNION, FeatureType.DIFFERENCE}
    
    def validate_node_addition(self, tree: FeatureTree, new_node: FeatureNode, 
                             parent_id: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Comprehensive validation for adding a node to the feature tree.
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # 1. Basic validation
        if new_node.id in tree.nodes:
            errors.append(f"Node with ID {new_node.id} already exists in tree")
        
        # 2. Parent reference validation
        parent_errors = self._validate_parent_references(tree, new_node, parent_id)
        errors.extend(parent_errors)
        
        # 3. Semantic validation - will this node actually affect the model?
        semantic_errors = self._validate_semantic_constraints(tree, new_node, parent_id)
        errors.extend(semantic_errors)
        
        # 4. Dependency validation
        dependency_errors = self._validate_dependencies(tree, new_node)
        errors.extend(dependency_errors)
        
        # 5. Boolean operation validation
        if new_node.feature_type in self.boolean_operation_types:
            boolean_errors = self._validate_boolean_operation(tree, new_node)
            errors.extend(boolean_errors)
        
        # 6. Result impact validation
        impact_errors = self._validate_result_impact(tree, new_node, parent_id)
        errors.extend(impact_errors)
        
        return len(errors) == 0, errors
    
    def _validate_parent_references(self, tree: FeatureTree, new_node: FeatureNode, 
                                   parent_id: Optional[str]) -> List[str]:
        """Validate that parent references are valid"""
        errors = []
        
        # Check if provided parent_id exists
        if parent_id and parent_id not in tree.nodes:
            errors.append(f"Parent node {parent_id} does not exist in tree")
            return errors
        
        # Check all parent references in the node
        for ref in new_node.parent_references:
            if ref.feature_id not in tree.nodes:
                errors.append(f"Referenced parent node {ref.feature_id} does not exist in tree")
                continue
            
            parent_node = tree.nodes[ref.feature_id]
            
            # Check if parent type is compatible with child type
            if new_node.feature_type in self.valid_parent_types:
                valid_parents = self.valid_parent_types[new_node.feature_type]
                if parent_node.feature_type not in valid_parents:
                    errors.append(
                        f"Invalid parent type: {new_node.feature_type.value} cannot be created "
                        f"from {parent_node.feature_type.value}. Valid parent types: "
                        f"{[t.value for t in valid_parents]}"
                    )
        
        return errors
    
    def _validate_semantic_constraints(self, tree: FeatureTree, new_node: FeatureNode, 
                                     parent_id: Optional[str]) -> List[str]:
        """Validate semantic constraints to ensure the node will affect the model"""
        errors = []
        warnings = []
        
        # 1. Check for surface operations applied before boolean operations
        if new_node.feature_type in self.surface_operation_types and parent_id:
            parent_node = tree.nodes.get(parent_id)
            if parent_node:
                # Look for future boolean operations that might use the parent instead of this surface operation
                future_boolean_ops = self._find_future_boolean_operations(tree, parent_node.id)
                if future_boolean_ops:
                    warnings.append(
                        f"Warning: Adding {new_node.feature_type.value} to {parent_node.name} "
                        f"may not appear in final result because future boolean operations "
                        f"reference the original geometry: {[op.name for op in future_boolean_ops]}"
                    )
                    # This is a warning for now, but could be made an error
                    # errors.append(warnings[-1])
        
        # 2. Check for sketches without subsequent solid operations
        if new_node.feature_type == FeatureType.SKETCH:
            # This sketch should eventually be used by an extrude/revolve operation
            # We can't validate this completely at addition time, but we can warn
            warnings.append(
                f"Reminder: Sketch '{new_node.name}' will only affect the model "
                f"if it's used by an extrude, revolve, or similar operation"
            )
        
        # 3. Check for workplanes that aren't used
        if new_node.feature_type == FeatureType.WORKPLANE:
            warnings.append(
                f"Reminder: Workplane '{new_node.name}' will only affect the model "
                f"if it's used for sketching or primitive creation"
            )
        
        # Log warnings
        for warning in warnings:
            logger.warning(warning)
        
        return errors
    
    def _validate_dependencies(self, tree: FeatureTree, new_node: FeatureNode) -> List[str]:
        """Validate that adding this node won't create circular dependencies"""
        errors = []
        
        # Simulate adding the node and check for cycles
        temp_tree = self._create_temp_tree_with_node(tree, new_node)
        
        # Check for circular dependencies using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id: str) -> bool:
            if node_id in rec_stack:
                return True
            if node_id in visited:
                return False
            
            visited.add(node_id)
            rec_stack.add(node_id)
            
            node = temp_tree.nodes.get(node_id)
            if node:
                for ref in node.parent_references:
                    if has_cycle(ref.feature_id):
                        return True
            
            rec_stack.remove(node_id)
            return False
        
        if has_cycle(new_node.id):
            errors.append(f"Adding node {new_node.id} would create a circular dependency")
        
        return errors
    
    def _validate_boolean_operation(self, tree: FeatureTree, new_node: FeatureNode) -> List[str]:
        """Validate boolean operations have proper solid inputs"""
        errors = []
        
        if new_node.feature_type not in self.boolean_operation_types:
            return errors
        
        # Boolean operations need exactly 2 solid parents
        solid_parents = []
        for ref in new_node.parent_references:
            parent_node = tree.nodes.get(ref.feature_id)
            if parent_node and parent_node.feature_type in self.solid_types:
                solid_parents.append(parent_node)
        
        if len(solid_parents) < 2:
            errors.append(
                f"Boolean operation {new_node.feature_type.value} requires 2 solid parents, "
                f"but only {len(solid_parents)} found. Add more solid parent references."
            )
        
        return errors
    
    def _validate_result_impact(self, tree: FeatureTree, new_node: FeatureNode, 
                               parent_id: Optional[str]) -> List[str]:
        """Validate that this node will actually impact the final result"""
        errors = []
        
        # Simulate the tree with this node added
        temp_tree = self._create_temp_tree_with_node(tree, new_node)
        
        # Check if this node would be in the final result chain
        if not self._node_affects_result(temp_tree, new_node.id):
            if new_node.feature_type not in {FeatureType.WORKPLANE, FeatureType.SKETCH}:
                errors.append(
                    f"Node {new_node.name} ({new_node.feature_type.value}) will not affect "
                    f"the final model result. Ensure it's properly connected to the dependency chain."
                )
        
        return errors
    
    def _find_future_boolean_operations(self, tree: FeatureTree, node_id: str) -> List[FeatureNode]:
        """Find boolean operations that might reference this node's parent instead of this node"""
        future_ops = []
        
        # This is a simplified check - in practice, we'd need to analyze the full dependency graph
        for other_node in tree.nodes.values():
            if (other_node.feature_type in self.boolean_operation_types and
                any(ref.feature_id == node_id for ref in other_node.parent_references)):
                future_ops.append(other_node)
        
        return future_ops
    
    def _create_temp_tree_with_node(self, tree: FeatureTree, new_node: FeatureNode) -> FeatureTree:
        """Create a temporary tree with the new node added for validation"""
        # Create a copy of the tree
        temp_tree = FeatureTree(
            project_id=tree.project_id,
            version=tree.version,
            name=tree.name,
            created_by=tree.created_by,
            nodes=tree.nodes.copy(),
            regeneration_order=tree.regeneration_order.copy(),
            global_parameters=tree.global_parameters.copy()
        )
        
        # Add the new node
        temp_tree.nodes[new_node.id] = new_node
        temp_tree.regeneration_order.append(new_node.id)
        
        return temp_tree
    
    def _node_affects_result(self, tree: FeatureTree, node_id: str) -> bool:
        """Check if a node affects the final result by tracing the dependency graph"""
        
        # Build forward dependency graph (who depends on this node)
        dependents = {}
        for nid in tree.nodes:
            dependents[nid] = []
        
        for nid, node in tree.nodes.items():
            for ref in node.parent_references:
                if ref.feature_id in dependents:
                    dependents[ref.feature_id].append(nid)
        
        # Trace forward from this node to see if any path leads to a solid result
        visited = set()
        
        def traces_to_solid(current_id: str) -> bool:
            if current_id in visited:
                return False
            
            visited.add(current_id)
            current_node = tree.nodes.get(current_id)
            
            if not current_node:
                return False
            
            # If this node is a solid and has no dependents, it could be a result
            if (current_node.feature_type in self.solid_types and 
                len(dependents.get(current_id, [])) == 0):
                return True
            
            # Check if any dependent traces to a solid
            for dependent_id in dependents.get(current_id, []):
                if traces_to_solid(dependent_id):
                    return True
            
            return False
        
        return traces_to_solid(node_id)
    
    def suggest_valid_additions(self, tree: FeatureTree, 
                               target_parent_id: Optional[str] = None) -> List[Dict[str, str]]:
        """Suggest valid node types that can be added to the tree"""
        suggestions = []
        
        if not tree.nodes:
            # Empty tree - suggest starting with workplane
            suggestions.append({
                "type": "workplane",
                "reason": "Start with a workplane to establish coordinate system"
            })
            return suggestions
        
        if target_parent_id and target_parent_id in tree.nodes:
            parent_node = tree.nodes[target_parent_id]
            
            if parent_node.feature_type == FeatureType.WORKPLANE:
                suggestions.extend([
                    {"type": "sketch", "reason": "Create a profile for extrusion"},
                    {"type": "box", "reason": "Create a rectangular solid"},
                    {"type": "cylinder", "reason": "Create a cylindrical solid"},
                    {"type": "sphere", "reason": "Create a spherical solid"}
                ])
            
            elif parent_node.feature_type == FeatureType.SKETCH:
                suggestions.extend([
                    {"type": "extrude", "reason": "Convert sketch to 3D solid"},
                    {"type": "revolve", "reason": "Revolve sketch around axis"}
                ])
            
            elif parent_node.feature_type in self.solid_types:
                suggestions.extend([
                    {"type": "sketch", "reason": "Create new sketch on solid face"},
                    {"type": "fillet", "reason": "Round sharp edges"},
                    {"type": "chamfer", "reason": "Cut angular edges"}
                ])
                
                # Suggest boolean operations if there are other solids
                other_solids = [n for n in tree.nodes.values() 
                              if n.feature_type in self.solid_types and n.id != target_parent_id]
                if other_solids:
                    suggestions.extend([
                        {"type": "union", "reason": "Combine with another solid"},
                        {"type": "difference", "reason": "Cut using another solid"}
                    ])
        
        return suggestions


# Global instance
feature_tree_validator = FeatureTreeValidator()