"""
Design Parameter Extractor - Extract meaningful parameters from CADQuery code.

This service identifies the key design variables that users would want to edit,
like dimensions, radii, etc., rather than generic method arguments.
"""

import ast
import re
from typing import Dict, List, Optional, Any, Tuple
import logging

from app.models.feature_tree import Parameter, ParameterType

logger = logging.getLogger(__name__)


class DesignParameterExtractor:
    """Extract meaningful design parameters from CADQuery code"""
    
    # Common parameter name patterns that indicate meaningful dimensions
    DIMENSION_PATTERNS = [
        r'.*radius.*',
        r'.*diameter.*',
        r'.*width.*',
        r'.*height.*',
        r'.*length.*',
        r'.*thickness.*',
        r'.*depth.*',
        r'.*size.*',
        r'.*distance.*',
        r'.*offset.*',
        r'.*angle.*',
        r'.*rim.*',
        r'.*inner.*',
        r'.*outer.*',
        r'.*hole.*',
        r'.*gap.*',
        r'.*spacing.*',
        r'.*pitch.*'
    ]
    
    def __init__(self, code: str):
        self.code = code
        self.variables = self._extract_variables()
        
    def _extract_variables(self) -> Dict[str, Any]:
        """Extract all variable assignments from the code"""
        variables = {}
        
        try:
            tree = ast.parse(self.code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    if (len(node.targets) == 1 and 
                        isinstance(node.targets[0], ast.Name)):
                        
                        var_name = node.targets[0].id
                        value = self._extract_value_from_node(node.value, variables)
                        
                        if value is not None:
                            variables[var_name] = value
                            
        except Exception as e:
            logger.error(f"Failed to extract variables: {e}")
            # Fallback to regex
            pattern = r'(\w+)\s*=\s*([\d.]+)'
            matches = re.findall(pattern, self.code)
            
            for var_name, value_str in matches:
                try:
                    if '.' in value_str:
                        variables[var_name] = float(value_str)
                    else:
                        variables[var_name] = int(value_str)
                except ValueError:
                    continue
        
        return variables
    
    def _extract_value_from_node(self, node: ast.AST, known_vars: Dict[str, Any]) -> Any:
        """Extract value from AST node with support for expressions"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # Python < 3.8
            return node.n
        elif isinstance(node, ast.Name):
            var_name = node.id
            return known_vars.get(var_name)
        elif isinstance(node, ast.BinOp):
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
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        
        return None
    
    def get_design_parameters(self) -> List[Parameter]:
        """Get meaningful design parameters that users would want to edit"""
        design_params = []
        
        for var_name, value in self.variables.items():
            if self._is_design_parameter(var_name) and isinstance(value, (int, float)):
                # Create a user-friendly parameter
                param = Parameter(
                    name=self._get_friendly_name(var_name),
                    type=ParameterType.FLOAT if isinstance(value, float) else ParameterType.INTEGER,
                    value=value,
                    description=f"Design parameter: {var_name}",
                    min_value=0.1 if 'radius' in var_name.lower() or 'thickness' in var_name.lower() else None,
                    max_value=1000.0 if any(dim in var_name.lower() for dim in ['radius', 'width', 'height', 'length']) else None
                )
                
                # Store the original variable name for mapping back to code
                param.original_variable_name = var_name
                design_params.append(param)
        
        return design_params
    
    def _is_design_parameter(self, var_name: str) -> bool:
        """Check if a variable name represents a meaningful design parameter"""
        var_lower = var_name.lower()
        
        # Check against dimension patterns
        for pattern in self.DIMENSION_PATTERNS:
            if re.match(pattern, var_lower):
                return True
        
        # Exclude common non-design variables
        excluded_patterns = [
            'result', 'output', 'temp', 'tmp', 'i', 'j', 'k', 'index',
            'count', 'iter', 'step', 'cq', 'cadquery'
        ]
        
        for excluded in excluded_patterns:
            if excluded in var_lower:
                return False
        
        return False
    
    def _get_friendly_name(self, var_name: str) -> str:
        """Convert variable name to user-friendly parameter name"""
        # Convert snake_case to Title Case
        friendly = var_name.replace('_', ' ').title()
        
        # Common replacements for better UX
        replacements = {
            'Outer Radius': 'Outer Radius',
            'Inner Radius': 'Inner Radius', 
            'Rim Radius': 'Rim Radius',
            'Thickness': 'Thickness',
            'Height': 'Height',
            'Width': 'Width',
            'Length': 'Length',
            'Diameter': 'Diameter',
            'Hole Size': 'Hole Size',
            'Gap': 'Gap',
            'Spacing': 'Spacing'
        }
        
        return replacements.get(friendly, friendly)
    
    def map_parameter_to_variable(self, parameter_name: str) -> Optional[str]:
        """Map a user-friendly parameter name back to the original variable name"""
        for param in self.get_design_parameters():
            if param.name == parameter_name:
                return getattr(param, 'original_variable_name', None)
        return None


def create_design_parameters_node(code: str, project_id: str) -> Optional[Dict[str, Any]]:
    """Create a virtual 'Design Parameters' node with meaningful parameters"""
    try:
        extractor = DesignParameterExtractor(code)
        design_params = extractor.get_design_parameters()
        
        if not design_params:
            return None
        
        # Create a virtual node for design parameters
        node_data = {
            'id': f"{project_id}_design_params",
            'name': 'Design Parameters',
            'feature_type': 'DESIGN_PARAMETERS',
            'parameters': [
                {
                    'name': param.name,
                    'type': param.type.value,
                    'value': param.value,
                    'description': param.description,
                    'min_value': param.min_value,
                    'max_value': param.max_value,
                    'original_variable_name': getattr(param, 'original_variable_name', None)
                }
                for param in design_params
            ],
            'children': [],
            'parent_id': None
        }
        
        return node_data
        
    except Exception as e:
        logger.error(f"Failed to create design parameters node: {e}")
        return None