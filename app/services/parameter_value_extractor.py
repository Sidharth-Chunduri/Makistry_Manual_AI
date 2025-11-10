"""
Parameter value extraction from CADQuery code.

This service extracts actual parameter values from the original CADQuery code
and maps them to feature tree parameters, ensuring the UI shows numeric values
instead of variable names.
"""

import re
import ast
from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ParameterValueExtractor:
    """
    Extracts parameter values from CADQuery code to populate feature tree parameters.
    """
    
    def __init__(self, code: str):
        self.code = code
        self.variable_values = self._extract_variable_values()
    
    def _extract_variable_values(self) -> Dict[str, Any]:
        """Extract all variable assignments from the code"""
        variable_values = {}
        
        try:
            # Parse the code into AST
            tree = ast.parse(self.code)
            
            # Find all variable assignments
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    # Handle simple assignments like: radius = 5.0
                    if (len(node.targets) == 1 and 
                        isinstance(node.targets[0], ast.Name)):
                        
                        var_name = node.targets[0].id
                        value = self._extract_value_from_node(node.value, variable_values)
                        
                        if value is not None:
                            variable_values[var_name] = value
            
        except Exception as e:
            logger.error(f"Failed to extract variable values: {e}")
            
            # Fallback to regex-based extraction
            pattern = r'(\w+)\s*=\s*([\d.]+)'
            matches = re.findall(pattern, self.code)
            
            for var_name, value_str in matches:
                try:
                    if '.' in value_str:
                        variable_values[var_name] = float(value_str)
                    else:
                        variable_values[var_name] = int(value_str)
                except ValueError:
                    continue
        
        return variable_values
    
    def _extract_value_from_node(self, node: ast.AST, known_vars: Dict[str, Any]) -> Any:
        """Extract value from AST node with support for expressions"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # Python < 3.8
            return node.n
        elif isinstance(node, ast.Str):  # Python < 3.8
            return node.s
        elif isinstance(node, ast.Name):
            # Try to resolve variable reference
            var_name = node.id
            return known_vars.get(var_name)
        elif isinstance(node, ast.BinOp):
            # Handle arithmetic operations
            try:
                left = self._extract_value_from_node(node.left, known_vars)
                right = self._extract_value_from_node(node.right, known_vars)
                
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    if isinstance(node.op, ast.Add):
                        return left + right
                    elif isinstance(node.op, ast.Sub):
                        return left - right
                    elif isinstance(node.op, ast.Mult):
                        return left * right
                    elif isinstance(node.op, ast.Div):
                        return left / right if right != 0 else None
                    elif isinstance(node.op, ast.FloorDiv):
                        return left // right if right != 0 else None
                    elif isinstance(node.op, ast.Mod):
                        return left % right if right != 0 else None
                    elif isinstance(node.op, ast.Pow):
                        return left ** right
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        elif isinstance(node, ast.UnaryOp):
            # Handle unary operations like -5
            try:
                operand = self._extract_value_from_node(node.operand, known_vars)
                if isinstance(operand, (int, float)):
                    if isinstance(node.op, ast.USub):
                        return -operand
                    elif isinstance(node.op, ast.UAdd):
                        return +operand
            except (TypeError, ValueError):
                pass
        
        return None
    
    def resolve_parameter_value(self, param_value: Any) -> Any:
        """
        Resolve a parameter value to its actual numeric value.
        
        Args:
            param_value: The parameter value (could be variable name or actual value)
            
        Returns:
            The resolved numeric value or the original value if it can't be resolved
        """
        # If it's already a numeric value, return it
        if isinstance(param_value, (int, float)):
            return param_value
        
        # If it's a string that might be a variable name, try to resolve it
        if isinstance(param_value, str):
            # First, check if it's a variable name we know
            if param_value in self.variable_values:
                return self.variable_values[param_value]
            
            # Try to parse it as a number
            try:
                if '.' in param_value:
                    return float(param_value)
                else:
                    return int(param_value)
            except ValueError:
                pass
            
            # Look for common parameter patterns
            for var_name, value in self.variable_values.items():
                if var_name.lower() in param_value.lower() or param_value.lower() in var_name.lower():
                    return value
        
        # Return original value if we can't resolve it
        return param_value
    
    def get_common_parameters(self) -> Dict[str, Any]:
        """Get common CAD parameters from the code"""
        common_param_names = [
            'radius', 'outer_radius', 'inner_radius', 'rim_radius',
            'height', 'thickness', 'width', 'length', 'diameter', 
            'depth', 'size', 'offset', 'angle', 'distance'
        ]
        
        common_params = {}
        for param_name in common_param_names:
            if param_name in self.variable_values:
                common_params[param_name] = self.variable_values[param_name]
        
        return common_params


def update_feature_tree_with_actual_values(feature_tree, original_code: str) -> None:
    """
    Update feature tree parameters with actual values from the original code.
    
    This ensures the UI shows numeric values instead of variable names.
    """
    try:
        extractor = ParameterValueExtractor(original_code)
        
        # Update all parameters in the feature tree
        for node in feature_tree.nodes.values():
            for param in node.parameters:
                resolved_value = extractor.resolve_parameter_value(param.value)
                
                # Only update if we got a different (hopefully numeric) value
                if resolved_value != param.value and isinstance(resolved_value, (int, float)):
                    logger.info(f"Resolved parameter {param.name}: {param.value} -> {resolved_value}")
                    param.value = resolved_value
                    
                    # Update parameter type to match the resolved value
                    from app.models.feature_tree import ParameterType
                    if isinstance(resolved_value, int):
                        param.type = ParameterType.INTEGER
                    elif isinstance(resolved_value, float):
                        param.type = ParameterType.FLOAT
        
    except Exception as e:
        logger.error(f"Failed to update feature tree with actual values: {e}")