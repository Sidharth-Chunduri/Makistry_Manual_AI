"""
CAD Generation Integration with Feature Trees.

This module integrates the existing CAD generation pipeline with the new feature tree system.
It creates feature trees from generated CADQuery code and provides regeneration capabilities.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional, Any, Tuple

from app.models.feature_tree import FeatureTree
from app.services.feature_tree_storage import feature_tree_storage
from app.services.feature_tree_parser import parse_cadquery_code
from app.agents.code_creation_aws import generate_cadquery
from app.services.sandbox import run_cadquery, SandboxError

logger = logging.getLogger(__name__)


class CADGenerationWithFeatureTree:
    """Enhanced CAD generation that creates and manages feature trees"""
    
    def __init__(self):
        self.storage = feature_tree_storage
    
    def generate_cad_with_feature_tree(self, brainstorm: Dict[str, Any], 
                                     project_id: str, user_id: str, 
                                     session_id: str) -> Tuple[str, FeatureTree, Dict[str, Any]]:
        """
        Generate CAD code and create a feature tree.
        
        Args:
            brainstorm: Design requirements in JSON format
            project_id: Project identifier
            user_id: User identifier
            session_id: Session identifier
        
        Returns:
            Tuple of (cad_code, feature_tree, usage_stats)
        """
        try:
            # Generate CAD code using existing AI pipeline
            logger.info(f"Generating CAD code for project {project_id}")
            raw_cad_code, usage = generate_cadquery(brainstorm)
            
            # Add variable declarations to the generated code for parameter editing
            cad_code = self._add_parameter_variables(raw_cad_code, brainstorm)
            
            # Parse the generated code into a feature tree
            logger.info(f"Parsing generated code into feature tree")
            feature_tree = parse_cadquery_code(cad_code, project_id, user_id)
            
            # Update feature tree parameters with actual values from the code
            from app.services.parameter_value_extractor import update_feature_tree_with_actual_values
            update_feature_tree_with_actual_values(feature_tree, cad_code)
            
            # Add meaningful design parameters as a special node
            self._add_design_parameters_node(feature_tree, cad_code)
            
            # Add metadata about the generation
            feature_tree.description = f"Generated from brainstorm: {brainstorm.get('description', 'CAD Model')}"
            feature_tree.name = brainstorm.get('name', 'Generated CAD Model')
            
            # Save the feature tree
            self.storage.save_feature_tree(feature_tree)
            
            logger.info(f"Created feature tree with {len(feature_tree.nodes)} nodes")
            return cad_code, feature_tree, usage
            
        except Exception as e:
            logger.error(f"Failed to generate CAD with feature tree: {e}")
            raise
    
    def regenerate_from_feature_tree(self, project_id: str, version: Optional[int] = None) -> str:
        """
        Regenerate CAD code from feature tree using complete code generation.
        
        This approach treats the feature tree as the "source of truth" and generates
        clean, complete CADQuery code from the current parameter values.
        
        Args:
            project_id: Project identifier
            version: Feature tree version (latest if None)
        
        Returns:
            Complete regenerated CADQuery code
        """
        try:
            # Get the feature tree
            tree = self.storage.get_feature_tree(project_id, version)
            if not tree:
                raise ValueError(f"Feature tree not found for project {project_id}")
            
            # Use the new feature tree code generator
            from app.services.feature_tree_code_generator import feature_tree_code_generator
            
            logger.info(f"Regenerating CADQuery code from feature tree for project {project_id}")
            regenerated_code = feature_tree_code_generator.generate_cadquery_code(tree)
            
            # Update the tree with the regenerated code
            tree.generated_code = regenerated_code
            tree.dirty = False
            if hasattr(tree, "needs_full_regeneration"):
                tree.needs_full_regeneration = False
            self.storage.save_feature_tree(tree)
            
            logger.info(f"Successfully regenerated {len(regenerated_code)} characters of CADQuery code")
            return regenerated_code
            
        except Exception as e:
            logger.error(f"Failed to regenerate from feature tree: {e}")
            raise
    
    def test_feature_tree_execution(self, project_id: str, version: Optional[int] = None) -> Tuple[bool, str]:
        """
        Test if the feature tree can be executed successfully.
        
        Args:
            project_id: Project identifier
            version: Feature tree version (latest if None)
        
        Returns:
            Tuple of (success, error_message_or_stl_path)
        """
        try:
            # Regenerate code from feature tree
            code = self.regenerate_from_feature_tree(project_id, version)
            
            # Test execution in sandbox
            stl_path = run_cadquery(code, ext="stl")
            return True, stl_path
            
        except SandboxError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Unexpected error: {e}"
    
    def update_node_and_regenerate(self, project_id: str, node_id: str, 
                                 parameter_changes: Dict[str, Any],
                                 version: Optional[int] = None) -> Tuple[FeatureTree, str]:
        """
        Update a node's parameters and regenerate the code.
        
        Args:
            project_id: Project identifier
            node_id: Node to update
            parameter_changes: New parameter values
            version: Feature tree version (latest if None)
        
        Returns:
            Tuple of (updated_tree, regenerated_code)
        """
        try:
            # Update the node
            tree = self.storage.update_node_in_tree(project_id, node_id, parameter_changes, version)
            
            # Regenerate code
            code = self.regenerate_from_feature_tree(project_id, tree.version)
            
            return tree, code
            
        except Exception as e:
            logger.error(f"Failed to update node and regenerate: {e}")
            raise
    
    def create_tree_from_existing_code(self, project_id: str, user_id: str, 
                                     existing_code: str) -> FeatureTree:
        """
        Create a feature tree from existing CADQuery code.
        
        Args:
            project_id: Project identifier
            user_id: User identifier
            existing_code: Existing CADQuery code
        
        Returns:
            Created feature tree
        """
        try:
            # Parse the existing code
            feature_tree = parse_cadquery_code(existing_code, project_id, user_id)
            
            # Update feature tree parameters with actual values from the code
            from app.services.parameter_value_extractor import update_feature_tree_with_actual_values
            update_feature_tree_with_actual_values(feature_tree, existing_code)
            
            # Add meaningful design parameters as a special node
            self._add_design_parameters_node(feature_tree, existing_code)
            
            feature_tree.name = "Imported from Code"
            feature_tree.description = "Feature tree created from existing CADQuery code"
            
            # Save the tree
            self.storage.save_feature_tree(feature_tree)
            
            logger.info(f"Created feature tree from existing code with {len(feature_tree.nodes)} nodes")
            return feature_tree
            
        except Exception as e:
            logger.error(f"Failed to create tree from existing code: {e}")
            raise
    
    def _generate_code_from_node(self, node, previous_var: Optional[str] = None, var_name: Optional[str] = None) -> str:
        """
        Generate CADQuery code for a single feature node.
        
        Args:
            node: Feature node
            previous_var: Previous variable name to chain from
        
        Returns:
            Generated code line
        """
        from app.models.feature_tree import FeatureType
        
        # Get parameter values
        params = {p.name: p.value for p in node.parameters}
        
        base_var = previous_var or "cq.Workplane()"
        
        if node.feature_type == FeatureType.WORKPLANE:
            plane = params.get('plane', 'XY')
            return f"{node.id} = cq.Workplane('{plane}')"
        
        elif node.feature_type == FeatureType.BOX:
            width = params.get('width', params.get('arg_0', 1))
            height = params.get('height', params.get('arg_1', 1))
            depth = params.get('depth', params.get('arg_2', 1))
            return f"{node.id} = {base_var}.box({width}, {height}, {depth})"
        
        elif node.feature_type == FeatureType.CYLINDER:
            radius = params.get('radius', params.get('arg_0', 1))
            height = params.get('height', params.get('arg_1', 1))
            return f"{node.id} = {base_var}.cylinder({radius}, {height})"
        
        elif node.feature_type == FeatureType.SPHERE:
            radius = params.get('radius', params.get('arg_0', 1))
            return f"{node.id} = {base_var}.sphere({radius})"
        
        elif node.feature_type == FeatureType.EXTRUDE:
            distance = params.get('distance', params.get('arg_0', 1))
            return f"{node.id} = {base_var}.extrude({distance})"
        
        elif node.feature_type == FeatureType.REVOLVE:
            angle = params.get('angle', params.get('arg_0', 360))
            return f"{node.id} = {base_var}.revolve({angle})"
        
        elif node.feature_type == FeatureType.FILLET:
            radius = params.get('radius', params.get('arg_0', 0.1))
            return f"{node.id} = {base_var}.edges().fillet({radius})"
        
        elif node.feature_type == FeatureType.CHAMFER:
            distance = params.get('distance', params.get('arg_0', 0.1))
            return f"{node.id} = {base_var}.edges().chamfer({distance})"
        
        elif node.feature_type == FeatureType.UNION:
            # This would need reference to another object
            return f"{node.id} = {base_var}.union(other_object)"
        
        elif node.feature_type == FeatureType.DIFFERENCE:
            return f"{node.id} = {base_var}.cut(other_object)"
        
        else:
            # Generic method call
            method_name = node.feature_type.value
            args = [str(p.value) for p in node.parameters if p.name.startswith('arg_')]
            kwargs = [f"{p.name}={repr(p.value)}" for p in node.parameters if not p.name.startswith('arg_')]
            all_args = args + kwargs
            args_str = ", ".join(all_args)
            return f"{node.id} = {base_var}.{method_name}({args_str})"
    
    def _add_design_parameters_node(self, feature_tree: FeatureTree, code: str) -> None:
        """Add a 'Design Parameters' node with meaningful parameters users can edit (CADAM-style)"""
        try:
            from app.services.cadam_style_parameter_extractor import CADAMStyleParameterExtractor
            from app.models.feature_tree import FeatureNode, FeatureType
            
            # Use CADAM-style variable-first parameter extraction
            extractor = CADAMStyleParameterExtractor()
            design_params = extractor.extract_parameters_from_code(code)
            
            if design_params:
                # Create a special design parameters node
                design_node = FeatureNode(
                    id=f"{feature_tree.project_id}_design_params",
                    name="Design Parameters",
                    feature_type=FeatureType.SKETCH,  # Use sketch as a generic type
                    parameters=design_params,
                    child_ids=[],  # Use child_ids instead of children
                    parent_references=[]
                )
                
                # Add to the front of the tree so it appears first (bypass validation for internal system nodes)
                feature_tree.nodes[design_node.id] = design_node
                # Add to regeneration order at the beginning
                if design_node.id not in feature_tree.regeneration_order:
                    feature_tree.regeneration_order.insert(0, design_node.id)
                
                logger.info(f"Added CADAM-style design parameters node with {len(design_params)} parameters")
                for param in design_params:
                    logger.info(f"  - {param.name}: {param.value} ({param.type})")
                
        except Exception as e:
            logger.error(f"Failed to add design parameters node: {e}")
    
    def _add_parameter_variables(self, raw_code: str, brainstorm: Dict[str, Any]) -> str:
        """
        Add variable declarations to generated CADQuery code based on brainstorm geometry.
        
        Converts inline values to variables for parameter editing.
        Ensures no duplicate variables and clean parameter substitution.
        """
        try:
            # Extract geometry parameters from brainstorm
            geometry = brainstorm.get('optimal_geometry', {})
            
            # Common geometry parameter mappings
            param_mappings = {
                'outer_diameter': ['outer_diameter', 'diameter', 'width', 'size'],
                'inner_diameter': ['inner_diameter', 'axle_bore_diameter', 'hole_diameter'],
                'height': ['height', 'tread_width', 'thickness', 'depth'],
                'radius': ['radius', 'outer_radius'],
                'inner_radius': ['inner_radius'],
                'thickness': ['thickness', 'wall_thickness']
            }
            
            # Extract numeric values from geometry
            variables = {}
            
            for var_name, possible_keys in param_mappings.items():
                for key in possible_keys:
                    if key in geometry:
                        value_str = str(geometry[key])
                        # Extract numeric value from strings like "200 mm"
                        numeric_match = re.search(r'(\d+(?:\.\d+)?)', value_str)
                        if numeric_match:
                            variables[var_name] = float(numeric_match.group(1))
                            break
            
            # If no variables found, create sensible defaults based on common wheel dimensions
            if not variables:
                variables = {
                    'outer_radius': 100.0,
                    'inner_radius': 10.0,
                    'thickness': 20.0
                }
            
            # First, check if the code already has variable declarations to avoid duplicates
            existing_vars = set()
            var_pattern = r'^(\w+)\s*=\s*[\d.]+\s*$'
            for line in raw_code.split('\n'):
                match = re.match(var_pattern, line.strip())
                if match:
                    existing_vars.add(match.group(1))
            
            # Only add variables that don't already exist
            final_variables = {}
            for var_name, value in variables.items():
                if var_name not in existing_vars:
                    final_variables[var_name] = value
                else:
                    logger.info(f"Variable {var_name} already exists in code, skipping")
            
            # Generate variable declarations only for new variables
            var_declarations = ""
            if final_variables:
                var_declarations = "# Design parameters\n"
                for var_name, value in final_variables.items():
                    var_declarations += f"{var_name} = {value}\n"
                var_declarations += "\n"
            
            # Replace inline numeric values with variables in the code
            modified_code = raw_code
            
            # Find all variables (both existing and new) for substitution
            all_variables = {**variables}  # Use all variables for substitution
            
            # More comprehensive pattern matching for value replacement
            replacements = [
                # Circle patterns
                (r'\.circle\((\d+(?:\.\d+)?)\)', lambda m: f'.circle({self._find_best_variable(float(m.group(1)), all_variables, "radius")})'),
                # Extrude patterns  
                (r'\.extrude\((\d+(?:\.\d+)?)\)', lambda m: f'.extrude({self._find_best_variable(float(m.group(1)), all_variables, "thickness")})'),
                # Cylinder patterns
                (r'\.cylinder\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)', 
                 lambda m: f'.cylinder({self._find_best_variable(float(m.group(1)), all_variables, "radius")}, {self._find_best_variable(float(m.group(2)), all_variables, "thickness")})'),
                # Box patterns
                (r'\.box\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)',
                 lambda m: f'.box({self._find_best_variable(float(m.group(1)), all_variables, "width")}, {self._find_best_variable(float(m.group(2)), all_variables, "height")}, {self._find_best_variable(float(m.group(3)), all_variables, "thickness")})'),
                # Sphere patterns
                (r'\.sphere\((\d+(?:\.\d+)?)\)', lambda m: f'.sphere({self._find_best_variable(float(m.group(1)), all_variables, "radius")})'),
                # Fillet/chamfer patterns
                (r'\.fillet\((\d+(?:\.\d+)?)\)', lambda m: f'.fillet({self._find_best_variable(float(m.group(1)), all_variables, "radius")})'),
                (r'\.chamfer\((\d+(?:\.\d+)?)\)', lambda m: f'.chamfer({self._find_best_variable(float(m.group(1)), all_variables, "distance")})'),
            ]
            
            for pattern, replacement in replacements:
                modified_code = re.sub(pattern, replacement, modified_code)
            
            # Remove any existing variable definitions that might conflict
            # This prevents duplicate variable declarations
            if final_variables:
                code_lines = modified_code.split('\n')
                cleaned_lines = []
                for line in code_lines:
                    # Skip lines that define variables we're about to add
                    line_stripped = line.strip()
                    is_duplicate = False
                    for var_name in final_variables.keys():
                        if re.match(rf'^{re.escape(var_name)}\s*=\s*[\d.]+\s*$', line_stripped):
                            is_duplicate = True
                            logger.info(f"Removing duplicate variable definition: {line_stripped}")
                            break
                    if not is_duplicate:
                        cleaned_lines.append(line)
                modified_code = '\n'.join(cleaned_lines)
            
            # Combine variable declarations with modified code
            if final_variables:
                if "import cadquery as cq" in modified_code:
                    # Insert variables after import
                    parts = modified_code.split("import cadquery as cq", 1)
                    final_code = parts[0] + "import cadquery as cq\n\n" + var_declarations + parts[1]
                else:
                    final_code = var_declarations + modified_code
            else:
                final_code = modified_code
            
            logger.info(f"Added {len(final_variables)} new parameter variables to generated code")
            return final_code
            
        except Exception as e:
            logger.error(f"Failed to add parameter variables: {e}")
            return raw_code
    
    def _find_best_variable(self, value: float, variables: Dict[str, float], hint: str) -> str:
        """Find the best variable match for a given value"""
        # Look for exact matches first (within small tolerance)
        for var_name, var_value in variables.items():
            if abs(var_value - value) < 0.01:  # Close enough match
                return var_name
        
        # Look for close matches (within 10% tolerance)
        best_match = None
        best_diff = float('inf')
        for var_name, var_value in variables.items():
            if var_value > 0:  # Avoid division by zero
                diff = abs(var_value - value) / var_value
                if diff < 0.1 and diff < best_diff:  # Within 10% and closer than previous
                    best_match = var_name
                    best_diff = diff
        
        if best_match:
            return best_match
        
        # If no close match, look for variables with hint-based names
        hint_mappings = {
            "radius": ["outer_radius", "inner_radius", "radius"],
            "diameter": ["outer_diameter", "inner_diameter", "diameter"],
            "thickness": ["thickness", "height", "depth"],
            "height": ["height", "thickness", "depth"], 
            "width": ["width", "outer_diameter", "diameter"],
            "distance": ["thickness", "height", "radius"]
        }
        
        if hint in hint_mappings:
            for preferred_var in hint_mappings[hint]:
                if preferred_var in variables:
                    return preferred_var
        
        # If we have any variables, use the first reasonable one based on value size
        if variables:
            # For small values (< 50), prefer radius/thickness variables
            if value < 50:
                for var_name in ["inner_radius", "thickness", "radius"]:
                    if var_name in variables:
                        return var_name
            # For larger values, prefer diameter/outer dimensions
            else:
                for var_name in ["outer_diameter", "outer_radius", "height"]:
                    if var_name in variables:
                        return var_name
            
            # Last resort - use any available variable
            return list(variables.keys())[0]
        
        # Absolute fallback to original value
        return str(value)


# Global instance
cad_integration = CADGenerationWithFeatureTree()
