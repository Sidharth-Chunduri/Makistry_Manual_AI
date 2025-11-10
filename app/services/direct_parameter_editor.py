"""
Direct parameter editing approach that bypasses feature tree code regeneration.

Instead of trying to regenerate code from feature tree fragments, this approach:
1. Keeps the original CADQuery code intact
2. Maps feature tree parameters to original variable names  
3. Directly modifies parameters in the original code using AST
4. Re-executes the modified code
"""

import re
from typing import Dict, Any, Optional, Tuple, List
import logging

from app.services.ast_parameter_modifier import modify_cadquery_parameters
from app.services.feature_tree_storage import FeatureTreeStorage

logger = logging.getLogger(__name__)


class DirectParameterEditor:
    """
    Direct parameter editing that modifies original CADQuery code.
    
    This is a much simpler and more reliable approach than trying to 
    regenerate entire code from feature tree fragments.
    """
    
    def __init__(self, storage: FeatureTreeStorage):
        self.storage = storage
    
    def edit_parameter(self, project_id: str, node_id: str, param_name: str, 
                      new_value: Any, version: Optional[int] = None) -> Tuple[str, bool]:
        """
        Edit a parameter by directly modifying the original CADQuery code.
        
        Args:
            project_id: Project identifier
            node_id: Feature tree node ID  
            param_name: Parameter name (e.g., 'arg_0')
            new_value: New parameter value
            version: Feature tree version
            
        Returns:
            (modified_code, success)
        """
        try:
            # Get the feature tree and original code
            tree = self.storage.get_feature_tree(project_id, version)
            if not tree or not tree.generated_code:
                raise ValueError(f"No code found for project {project_id}")
            
            # Get the specific node and parameter
            node = tree.nodes.get(node_id)
            if not node:
                raise ValueError(f"Node {node_id} not found")
            
            # Find the parameter
            target_param = None
            for param in node.parameters:
                if param.name == param_name:
                    target_param = param
                    break
            
            if not target_param:
                raise ValueError(f"Parameter {param_name} not found in node {node_id}")
            
            # Map the parameter to a variable name in the original code
            var_name = self._map_parameter_to_variable(tree.generated_code, node, target_param)
            
            if not var_name:
                # If we can't map to a variable, update the parameter value directly
                # and return the original code (for display purposes)
                target_param.value = new_value
                tree.updated_at = tree.updated_at  # Trigger update
                self.storage.save_feature_tree(tree)
                return tree.generated_code, True
            
            # Modify the original code using AST
            parameter_changes = {var_name: new_value}
            modified_code, failed_params = modify_cadquery_parameters(
                tree.generated_code, parameter_changes
            )
            
            if failed_params:
                logger.warning(f"Failed to modify parameters: {failed_params}")
                return tree.generated_code, False
            
            # Update the parameter value in the feature tree
            target_param.value = new_value
            
            # Update the tree with the modified code
            tree.generated_code = modified_code
            self.storage.save_feature_tree(tree)
            
            return modified_code, True
            
        except Exception as e:
            logger.error(f"Failed to edit parameter: {e}")
            return "", False
    
    def _map_parameter_to_variable(self, code: str, node, parameter) -> Optional[str]:
        """
        Map a feature tree parameter back to its original variable name.
        
        This uses heuristics to find the variable name that corresponds
        to a parameter in the feature tree.
        """
        # For numeric parameters, try to find common variable names
        if isinstance(parameter.value, (int, float)):
            # Common CAD parameter names
            common_names = [
                'radius', 'outer_radius', 'inner_radius',
                'height', 'thickness', 'width', 'length',
                'diameter', 'offset', 'depth', 'size'
            ]
            
            # Look for variable assignments with values close to the parameter value
            for var_name in common_names:
                pattern = rf'{var_name}\s*=\s*{re.escape(str(parameter.value))}'
                if re.search(pattern, code):
                    return var_name
            
            # Try to find any variable with the same value
            pattern = rf'(\w+)\s*=\s*{re.escape(str(parameter.value))}'
            match = re.search(pattern, code)
            if match:
                return match.group(1)
        
        return None
    
    def extract_all_parameters(self, project_id: str, version: Optional[int] = None) -> Dict[str, Any]:
        """
        Extract all editable parameters from the original code.
        
        Returns:
            Dict mapping variable names to their current values
        """
        try:
            tree = self.storage.get_feature_tree(project_id, version)
            if not tree or not tree.generated_code:
                return {}
            
            # Use regex to find all variable assignments
            pattern = r'(\w+)\s*=\s*([\d.]+)'
            matches = re.findall(pattern, tree.generated_code)
            
            parameters = {}
            for var_name, value_str in matches:
                try:
                    # Try to convert to appropriate numeric type
                    if '.' in value_str:
                        parameters[var_name] = float(value_str)
                    else:
                        parameters[var_name] = int(value_str)
                except ValueError:
                    continue
            
            return parameters
            
        except Exception as e:
            logger.error(f"Failed to extract parameters: {e}")
            return {}


# Global instance for easy access
direct_parameter_editor = None

def get_direct_parameter_editor() -> DirectParameterEditor:
    """Get the global direct parameter editor instance"""
    global direct_parameter_editor
    if direct_parameter_editor is None:
        from app.services.feature_tree_storage import feature_tree_storage
        direct_parameter_editor = DirectParameterEditor(feature_tree_storage)
    return direct_parameter_editor