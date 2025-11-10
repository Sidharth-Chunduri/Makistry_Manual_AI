"""
Feature Tree to CADQuery Code Generator.

This service generates complete, clean CADQuery code from a feature tree,
making the feature tree the "source of truth" for parametric models.
"""
import logging
from typing import Dict, List, Optional, Set, Tuple
from app.models.feature_tree import FeatureTree, FeatureNode, FeatureType, Parameter

logger = logging.getLogger(__name__)


class FeatureTreeCodeGenerator:
    """Generates CADQuery code from feature trees"""
    
    def __init__(self):
        self.variable_counter = 0
        self.used_variables: Set[str] = set()
        self.dependency_graph: Dict[str, List[str]] = {}
        self.resolved_order: List[str] = []
    
    def generate_cadquery_code(self, feature_tree: FeatureTree) -> str:
        """
        Generate complete CADQuery code from a feature tree.
        
        Args:
            feature_tree: The feature tree to convert
            
        Returns:
            Complete executable CADQuery Python code
        """
        try:
            self.variable_counter = 0
            self.used_variables = set()
            self.dependency_graph = {}
            self.resolved_order = []
            
            # Build dependency graph first
            self._build_dependency_graph(feature_tree)
            
            # Resolve dependencies using topological sort
            self._resolve_dependencies(feature_tree)
            
            code_lines = []
            
            # Add import
            code_lines.append("import cadquery as cq")
            code_lines.append("")
            
            # Add global parameters first
            if feature_tree.global_parameters:
                code_lines.append("# Global parameters")
                for param in feature_tree.global_parameters:
                    if param.name not in self.used_variables:
                        code_lines.append(f"{param.name} = {self._format_parameter_value(param)}")
                        self.used_variables.add(param.name)
                code_lines.append("")
            
            # Extract design parameters from the special design parameters node
            design_params = self._extract_design_parameters(feature_tree)
            if design_params:
                code_lines.append("# Design parameters")
                for param_name, param_value in design_params.items():
                    if param_name not in self.used_variables:
                        code_lines.append(f"{param_name} = {param_value}")
                        self.used_variables.add(param_name)
                code_lines.append("")
            
            # Generate code for each node in dependency-resolved order
            variables = {}  # Track variable assignments
            
            for node_id in self.resolved_order:
                if node_id in feature_tree.nodes:
                    node = feature_tree.nodes[node_id]
                    
                    # Skip special nodes like design parameters
                    if node.feature_type == FeatureType.SKETCH and "design_params" in node.id:
                        continue
                    
                    try:
                        # Pre-assign variable name before generating code
                        var_name = self._get_variable_name(node)
                        variables[node_id] = var_name
                        
                        code_line = self._generate_node_code(node, variables, feature_tree)
                        if code_line:
                            code_lines.append(code_line)
                    except Exception as e:
                        logger.error(f"Failed to generate code for node {node_id}: {e}")
                        code_lines.append(f"# ERROR: Failed to generate code for {node.name}: {e}")
            
            # Find the final result variable using dependency-aware logic
            result_var = self._find_result_variable_with_dependencies(variables, feature_tree)
            code_lines.append("")
            code_lines.append(f"result = {result_var}")
            
            return "\n".join(code_lines)
            
        except Exception as e:
            logger.error(f"Failed to generate CADQuery code from feature tree: {e}")
            raise
    
    def _extract_design_parameters(self, feature_tree: FeatureTree) -> Dict[str, float]:
        """Extract design parameters from the special design parameters node"""
        design_params = {}
        
        for node in feature_tree.nodes.values():
            if (node.feature_type == FeatureType.SKETCH and 
                "design_params" in node.id and 
                node.name == "Design Parameters"):
                
                for param in node.parameters:
                    if hasattr(param, 'original_variable_name') and param.original_variable_name:
                        # Use the original variable name if available
                        var_name = param.original_variable_name
                    else:
                        # Convert friendly name back to variable name
                        var_name = param.name.lower().replace(' ', '_')
                    
                    # Skip invalid variable names
                    if var_name and var_name.isidentifier() and var_name not in ['None', 'True', 'False']:
                        design_params[var_name] = param.value
                break
        
        return design_params
    
    def _build_dependency_graph(self, feature_tree: FeatureTree) -> None:
        """Build adjacency list representing dependencies between nodes (FreeCAD-inspired)"""
        self.dependency_graph = {}
        
        # Initialize graph with all nodes
        for node_id in feature_tree.nodes:
            self.dependency_graph[node_id] = []
        
        # Add dependencies based on parent references
        for node_id, node in feature_tree.nodes.items():
            if node.parent_references:
                for ref in node.parent_references:
                    parent_id = ref.feature_id
                    if parent_id in self.dependency_graph:
                        self.dependency_graph[parent_id].append(node_id)
        
        logger.info(f"Built dependency graph: {self.dependency_graph}")
    
    def _resolve_dependencies(self, feature_tree: FeatureTree) -> None:
        """Topological sort to resolve feature dependencies (FreeCAD-style)"""
        # Implementation of Kahn's algorithm for topological sorting
        in_degree = {}
        
        # Initialize in-degree count for all nodes
        for node_id in feature_tree.nodes:
            in_degree[node_id] = 0
        
        # Calculate in-degrees
        for node_id, node in feature_tree.nodes.items():
            if node.parent_references:
                for ref in node.parent_references:
                    if ref.feature_id in in_degree:
                        in_degree[node_id] += 1
        
        # Find nodes with no dependencies (in-degree = 0)
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        
        self.resolved_order = []
        
        while queue:
            # Remove node with no dependencies
            current = queue.pop(0)
            self.resolved_order.append(current)
            
            # Update in-degrees of dependent nodes
            if current in self.dependency_graph:
                for dependent in self.dependency_graph[current]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        # Check for cyclic dependencies
        if len(self.resolved_order) != len(feature_tree.nodes):
            logger.error("Cyclic dependency detected in feature tree!")
            # Fallback to original regeneration order
            self.resolved_order = feature_tree.regeneration_order
        
        logger.info(f"Resolved dependency order: {self.resolved_order}")
    
    def _find_result_variable_with_dependencies(self, variables: Dict[str, str], 
                                               feature_tree: FeatureTree) -> str:
        """Find result variable considering dependency chain and actual usage"""
        
        # Find nodes that are not dependencies of other nodes (leaf nodes)
        # A leaf node has no outgoing dependencies (empty list in dependency graph)
        leaf_nodes = []
        for node_id in self.resolved_order:
            if node_id in variables and node_id in self.dependency_graph:
                # A leaf has no dependents (empty dependency list)
                if len(self.dependency_graph[node_id]) == 0:
                    node = feature_tree.nodes.get(node_id)
                    # Skip workplanes as they're just construction planes
                    if node and node.feature_type != FeatureType.WORKPLANE:
                        leaf_nodes.append(node_id)
        
        logger.info(f"Found leaf nodes: {leaf_nodes}")
        
        # Priority for result selection in leaf nodes
        priority_types = [
            ['union', 'difference', 'intersection'],  # Boolean operations (highest priority)
            ['fillet', 'chamfer'],                    # Surface operations
            ['extrude', 'revolve', 'loft', 'sweep'], # Volume operations  
            ['box', 'cylinder', 'sphere', 'cone']    # Basic shapes
        ]
        
        # Check leaf nodes by priority
        for type_group in priority_types:
            for node_id in reversed(leaf_nodes):  # Most recent first
                node = feature_tree.nodes.get(node_id)
                if node and node.feature_type.value.lower() in type_group:
                    logger.info(f"Selected result from leaf node {node_id}: {variables[node_id]}")
                    return variables[node_id]
        
        # Fallback to any leaf node
        if leaf_nodes:
            result_id = leaf_nodes[-1]
            logger.info(f"Fallback to last leaf node {result_id}: {variables[result_id]}")
            return variables[result_id]
        
        # Emergency fallback to old logic
        return self._find_result_variable(variables, feature_tree)
    
    def _generate_node_code(self, node: FeatureNode, variables: Dict[str, str], 
                           feature_tree: FeatureTree) -> str:
        """Generate CADQuery code for a single node"""
        
        # DEBUG: Log every node being processed
        logger.info(f"DEBUG: _generate_node_code called for node {node.id}")
        logger.info(f"DEBUG: Node feature_type: {node.feature_type} (type: {type(node.feature_type)})")
        logger.info(f"DEBUG: Node name: {node.name}")
        
        # Get parameter values
        params = {p.name: p.value for p in node.parameters}
        logger.info(f"DEBUG: Node parameters: {params}")
        
        # Get variable name for this node (should already be assigned)
        var_name = variables.get(node.id)
        if not var_name:
            var_name = self._get_variable_name(node)
            variables[node.id] = var_name
        
        # Handle different feature types
        if node.feature_type == FeatureType.WORKPLANE:
            plane = params.get('plane', 'XY')
            return f"{var_name} = cq.Workplane('{plane}')"
        
        elif node.feature_type == FeatureType.BOX:
            width = self._get_param_value(params, ['width', 'arg_0'], 1)
            height = self._get_param_value(params, ['height', 'arg_1'], 1) 
            depth = self._get_param_value(params, ['depth', 'arg_2'], 1)
            base_var = self._get_base_variable(node, variables, feature_tree)
            return f"{var_name} = {base_var}.box({width}, {height}, {depth})"
        
        elif node.feature_type == FeatureType.CYLINDER:
            radius = self._get_param_value(params, ['radius', 'arg_0'], 1)
            height = self._get_param_value(params, ['height', 'arg_1'], 1)
            base_var = self._get_base_variable(node, variables, feature_tree)
            return f"{var_name} = {base_var}.cylinder({radius}, {height})"
        
        elif node.feature_type == FeatureType.SPHERE:
            radius = self._get_param_value(params, ['radius', 'arg_0'], 1)
            base_var = self._get_base_variable(node, variables, feature_tree)
            return f"{var_name} = {base_var}.sphere({radius})"
        
        elif node.feature_type == FeatureType.EXTRUDE:
            distance = self._get_param_value(params, ['distance', 'arg_0'], 1)
            base_var = self._get_base_variable(node, variables, feature_tree)
            return f"{var_name} = {base_var}.extrude({distance})"
        
        elif node.feature_type == FeatureType.REVOLVE:
            angle = self._get_param_value(params, ['angle', 'arg_0'], 360)
            base_var = self._get_base_variable(node, variables, feature_tree)
            return f"{var_name} = {base_var}.revolve({angle})"
        
        elif node.feature_type == FeatureType.FILLET:
            radius = self._get_param_value(params, ['radius', 'arg_0'], 0.1)
            base_var = self._get_base_variable(node, variables, feature_tree)
            
            # CRITICAL CHECK: Detect if this fillet will be ineffective due to subsequent boolean operations
            base_node = self._get_parent_node(node, feature_tree)
            if base_node:
                # Look for boolean operations that use the base geometry (not the fillet)
                node_index = self.resolved_order.index(node.id) if node.id in self.resolved_order else -1
                if node_index >= 0:
                    for future_node_id in self.resolved_order[node_index+1:]:
                        future_node = feature_tree.nodes.get(future_node_id)
                        if future_node and future_node.feature_type in [FeatureType.UNION, FeatureType.DIFFERENCE]:
                            # Check if the boolean operation references the original base, not this fillet
                            for ref in future_node.parent_references:
                                if ref.feature_id == base_node.id:
                                    logger.warning(f"POTENTIAL ISSUE: Fillet {node.name} on {base_node.name} may not appear in final result because {future_node.name} uses the original geometry!")
                                    logger.warning(f"SUGGESTION: Apply fillet to the result of the boolean operation instead")
                                    break
            
            return f"{var_name} = {base_var}.edges().fillet({radius})"
        
        elif node.feature_type == FeatureType.CHAMFER:
            distance = self._get_param_value(params, ['distance', 'arg_0'], 0.1)
            base_var = self._get_base_variable(node, variables, feature_tree)
            return f"{var_name} = {base_var}.edges().chamfer({distance})"
        
        elif node.feature_type == FeatureType.UNION:
            base_var = self._get_base_variable(node, variables, feature_tree)
            other_var = self._get_reference_variable(node, variables, feature_tree)
            
            # CRITICAL FIX: Never use filleted/chamfered geometries in boolean operations
            # Boolean operations should use the original unmodified geometry
            # Surface operations like fillets should be applied AFTER boolean operations
            
            # Ensure we're using the original unfilleted geometry for boolean operations
            if node.parent_references:
                for i, ref in enumerate(node.parent_references):
                    parent_id = ref.feature_id
                    parent_node = feature_tree.nodes.get(parent_id)
                    
                    # If parent is a fillet/chamfer, find its parent instead
                    if parent_node and parent_node.feature_type in [FeatureType.FILLET, FeatureType.CHAMFER]:
                        if parent_node.parent_references:
                            original_parent_id = parent_node.parent_references[0].feature_id
                            if original_parent_id in variables:
                                if i == 0:
                                    base_var = variables[original_parent_id]
                                    logger.info(f"Using original geometry {base_var} instead of fillet/chamfer for union")
                                else:
                                    other_var = variables[original_parent_id]
            
            return f"{var_name} = {base_var}.union({other_var})"
        
        elif node.feature_type == FeatureType.DIFFERENCE:
            base_var = self._get_base_variable(node, variables, feature_tree)
            other_var = self._get_reference_variable(node, variables, feature_tree)
            
            # CRITICAL FIX: Same as union - use original geometry for boolean operations
            if node.parent_references:
                for i, ref in enumerate(node.parent_references):
                    parent_id = ref.feature_id
                    parent_node = feature_tree.nodes.get(parent_id)
                    
                    # If parent is a fillet/chamfer, find its parent instead
                    if parent_node and parent_node.feature_type in [FeatureType.FILLET, FeatureType.CHAMFER]:
                        if parent_node.parent_references:
                            original_parent_id = parent_node.parent_references[0].feature_id
                            if original_parent_id in variables:
                                if i == 0:
                                    base_var = variables[original_parent_id]
                                    logger.info(f"Using original geometry {base_var} instead of fillet/chamfer for difference")
                                else:
                                    other_var = variables[original_parent_id]
            
            return f"{var_name} = {base_var}.cut({other_var})"
        
        elif node.feature_type == FeatureType.SKETCH:
            base_var = self._get_base_variable(node, variables, feature_tree)
            # DEBUG: Log sketch node processing
            logger.info(f"DEBUG: Processing SKETCH node {node.id} - {node.name}")
            logger.info(f"DEBUG: Sketch node parameters: {[(p.name, p.value) for p in node.parameters]}")
            logger.info(f"DEBUG: Base variable: {base_var}")
            
            # For sketches, we need to create geometry and then finalize
            # Default to a circle sketch for now
            radius = self._get_param_value(params, ['radius', 'arg_0'], 5)
            generated_line = f"{var_name} = {base_var}.circle({radius})"
            logger.info(f"DEBUG: Generated sketch line: {generated_line}")
            return generated_line
        
        else:
            # Generic method call
            logger.info(f"DEBUG: Generic method call for node {node.id}")
            logger.info(f"DEBUG: Node feature_type: {node.feature_type} (type: {type(node.feature_type)})")
            logger.info(f"DEBUG: FeatureType.SKETCH: {FeatureType.SKETCH} (type: {type(FeatureType.SKETCH)})")
            logger.info(f"DEBUG: Are they equal? {node.feature_type == FeatureType.SKETCH}")
            method_name = node.feature_type.value
            logger.info(f"DEBUG: Method name: {method_name}")
            base_var = self._get_base_variable(node, variables, feature_tree)
            
            # Build arguments
            args = []
            # CRITICAL FIX: Never pass arguments to sketch() method regardless of feature type
            if method_name.lower() != 'sketch':
                for param in node.parameters:
                    if param.name.startswith('arg_'):
                        args.append(str(param.value))
                    else:
                        args.append(f"{param.name}={repr(param.value)}")
            
            args_str = ", ".join(args) if args else ""
            logger.info(f"DEBUG: Final method call: {var_name} = {base_var}.{method_name}({args_str})")
            return f"{var_name} = {base_var}.{method_name}({args_str})"
    
    def _get_param_value(self, params: Dict, param_names: List[str], default):
        """Get parameter value, trying multiple possible names"""
        for name in param_names:
            if name in params:
                return params[name]
        return default
    
    def _get_variable_name(self, node: FeatureNode) -> str:
        """Generate a clean variable name for a node"""
        base_name = node.feature_type.value.lower()
        
        # Make it unique
        counter = 1
        var_name = base_name
        while var_name in self.used_variables:
            var_name = f"{base_name}_{counter}"
            counter += 1
        
        self.used_variables.add(var_name)
        return var_name
    
    def _get_base_variable(self, node: FeatureNode, variables: Dict[str, str], 
                          feature_tree: FeatureTree) -> str:
        """Get the base variable this node operates on"""
        
        # If node has parent references, use the first one
        if node.parent_references:
            parent_id = node.parent_references[0].feature_id
            if parent_id in variables:
                parent_node = feature_tree.nodes.get(parent_id)
                if parent_node:
                    # CRITICAL FIX: Handle different parent types correctly
                    if node.feature_type == FeatureType.SKETCH:
                        # Sketches can only be created on workplanes, not on other sketches
                        if parent_node.feature_type == FeatureType.WORKPLANE:
                            return variables[parent_id]
                        elif parent_node.feature_type == FeatureType.SKETCH:
                            # Cannot chain sketches - need to find the workplane this sketch was created on
                            return self._find_workplane_for_sketch(parent_id, variables, feature_tree)
                        else:
                            # If parent is a solid, create a new workplane for sketching
                            return "cq.Workplane()"
                    else:
                        # For non-sketch operations, use the parent directly
                        # But prevent sketches from being used as bases for non-sketch operations
                        if parent_node.feature_type == FeatureType.SKETCH:
                            # Operations like extrude/revolve should operate on the sketch itself
                            if parent_id in variables:
                                return variables[parent_id]
                            return self._find_solid_from_sketch(parent_id, variables, feature_tree)
                        # Treat extrude/revolve children of solids as new workplanes on the parent
                        if (node.feature_type in (FeatureType.EXTRUDE, FeatureType.REVOLVE)
                                and parent_node.feature_type in {
                                    FeatureType.EXTRUDE,
                                    FeatureType.BOX,
                                    FeatureType.CYLINDER,
                                    FeatureType.SPHERE,
                                    FeatureType.REVOLVE,
                                    FeatureType.LOFT,
                                    FeatureType.SWEEP
                                }):
                            parent_var = variables[parent_id]
                            return f"{parent_var}.faces('>Z').workplane()"
                        else:
                            return variables[parent_id]
        
        # Look for parent in regeneration order
        node_index = -1
        try:
            node_index = feature_tree.regeneration_order.index(node.id)
        except ValueError:
            pass
        
        if node_index > 0:
            # For sketch nodes, find the last workplane or solid
            if node.feature_type == FeatureType.SKETCH:
                # Look backwards for a workplane or solid (but not another sketch)
                for i in range(node_index - 1, -1, -1):
                    prev_node_id = feature_tree.regeneration_order[i]
                    if prev_node_id in variables:
                        prev_node = feature_tree.nodes.get(prev_node_id)
                        if prev_node:
                            if prev_node.feature_type == FeatureType.WORKPLANE:
                                return variables[prev_node_id]
                            elif prev_node.feature_type in [FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE, FeatureType.EXTRUDE]:
                                # Use a new workplane for sketching
                                return "cq.Workplane()"
                            elif prev_node.feature_type == FeatureType.SKETCH:
                                # Skip sketch nodes when looking for base for another sketch
                                continue
            else:
                # For non-sketch operations, use the previous non-sketch variable
                for i in range(node_index - 1, -1, -1):
                    prev_node_id = feature_tree.regeneration_order[i]
                    if prev_node_id in variables:
                        prev_node = feature_tree.nodes.get(prev_node_id)
                        if prev_node and prev_node.feature_type != FeatureType.SKETCH:
                            return variables[prev_node_id]
        
        # Default to creating a new workplane
        return "cq.Workplane()"
    
    def _find_workplane_for_sketch(self, sketch_id: str, variables: Dict[str, str], 
                                  feature_tree: FeatureTree) -> str:
        """Find the workplane that a sketch was created on"""
        sketch_node = feature_tree.nodes.get(sketch_id)
        if sketch_node and sketch_node.parent_references:
            parent_id = sketch_node.parent_references[0].feature_id
            parent_node = feature_tree.nodes.get(parent_id)
            if parent_node and parent_node.feature_type == FeatureType.WORKPLANE:
                return variables[parent_id]
        
        # Fallback to new workplane
        return "cq.Workplane()"
    
    def _find_solid_from_sketch(self, sketch_id: str, variables: Dict[str, str], 
                               feature_tree: FeatureTree) -> str:
        """Find a solid that was created from a sketch"""
        # Look for nodes that reference this sketch as a parent
        for node_id, node in feature_tree.nodes.items():
            if node.parent_references:
                for ref in node.parent_references:
                    if ref.feature_id == sketch_id and node.feature_type in [
                        FeatureType.EXTRUDE, FeatureType.REVOLVE, FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE
                    ]:
                        if node_id in variables:
                            return variables[node_id]
        
        # Fallback to new workplane
        return "cq.Workplane()"
    
    def _get_reference_variable(self, node: FeatureNode, variables: Dict[str, str],
                               feature_tree: FeatureTree) -> str:
        """Get reference variable for boolean operations"""
        
        # For now, use the second parent reference or a simple default
        if len(node.parent_references) > 1:
            ref_id = node.parent_references[1].feature_id
            if ref_id in variables:
                return variables[ref_id]
        
        # Fallback - find the second most recent solid (for boolean operations)
        node_index = feature_tree.regeneration_order.index(node.id)
        solids_found = []
        for i in range(node_index - 1, -1, -1):
            prev_node_id = feature_tree.regeneration_order[i]
            if prev_node_id in variables:
                prev_node = feature_tree.nodes.get(prev_node_id)
                if prev_node and prev_node.feature_type in [
                    FeatureType.BOX, FeatureType.CYLINDER, FeatureType.SPHERE
                ]:
                    solids_found.append(variables[prev_node_id])
        
        # For boolean operations, we want the second-to-last solid as the cutting tool
        if len(solids_found) >= 2:
            return solids_found[1]  # Second most recent solid
        elif len(solids_found) >= 1:
            return solids_found[0]  # Fall back to most recent if only one found
        
        return "cq.Workplane().box(1, 1, 1)"  # Emergency fallback
    
    def _get_parent_node(self, node: FeatureNode, feature_tree: FeatureTree) -> Optional[FeatureNode]:
        """Get the parent node of a given node"""
        if node.parent_references:
            parent_id = node.parent_references[0].feature_id
            return feature_tree.nodes.get(parent_id)
        return None
    
    def _find_result_variable(self, variables: Dict[str, str], 
                             feature_tree: FeatureTree) -> str:
        """Find the variable that should be assigned to 'result'"""
        
        # Look for the final solid operation in reverse order
        # Priority: union/difference > fillet/chamfer > extrude/revolve > basic shapes
        priority_types = [
            ['union', 'difference', 'intersection'],  # Boolean operations (highest priority)
            ['fillet', 'chamfer'],                    # Surface operations
            ['extrude', 'revolve', 'loft', 'sweep'], # Volume operations  
            ['box', 'cylinder', 'sphere', 'cone']    # Basic shapes
        ]
        
        if feature_tree.regeneration_order and variables:
            # Check each priority level
            for type_group in priority_types:
                for node_id in reversed(feature_tree.regeneration_order):
                    if node_id in variables:
                        node = feature_tree.nodes.get(node_id)
                        if node and node.feature_type.value.lower() in type_group:
                            return variables[node_id]
            
            # Fallback to last variable if no priority matches
            for node_id in reversed(feature_tree.regeneration_order):
                if node_id in variables:
                    return variables[node_id]
        
        # Emergency fallback
        return "cq.Workplane().box(1, 1, 1)"
    
    def _format_parameter_value(self, param: Parameter) -> str:
        """Format a parameter value for code generation"""
        if param.type in ['float', 'length', 'angle']:
            return str(float(param.value))
        elif param.type == 'integer':
            return str(int(param.value))
        elif param.type == 'string':
            return repr(str(param.value))
        elif param.type == 'boolean':
            return str(bool(param.value))
        else:
            return str(param.value)


# Global instance
feature_tree_code_generator = FeatureTreeCodeGenerator()
