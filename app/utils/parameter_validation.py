"""
Parameter validation utilities for feature trees.

This module provides standalone parameter validation functions that can be used
both in the API routes and for testing purposes.
"""
from typing import Dict, List, Any
from app.models.feature_tree import FeatureNode, ParameterType


def validate_parameter_changes(node: FeatureNode, parameter_changes: Dict[str, Any]) -> List[str]:
    """Validate parameter changes for a feature node"""
    errors = []
    
    # Create a lookup for existing parameters
    existing_params = {p.name: p for p in node.parameters}
    
    for param_name, new_value in parameter_changes.items():
        if param_name not in existing_params:
            errors.append(f"Parameter '{param_name}' does not exist on node '{node.name}'")
            continue
            
        param = existing_params[param_name]
        
        # Type validation
        try:
            if param.type == ParameterType.FLOAT:
                float(new_value)
            elif param.type == ParameterType.INTEGER:
                int(new_value)
            elif param.type == ParameterType.BOOLEAN:
                if not isinstance(new_value, bool) and str(new_value).lower() not in ['true', 'false']:
                    raise ValueError("Invalid boolean value")
            elif param.type == ParameterType.STRING:
                str(new_value)
            elif param.type in [ParameterType.VECTOR3D, ParameterType.POINT3D]:
                if not isinstance(new_value, list) or len(new_value) != 3:
                    raise ValueError("Vector3D/Point3D must be a list of 3 numbers")
                [float(x) for x in new_value]
            elif param.type in [ParameterType.LENGTH, ParameterType.ANGLE]:
                float(new_value)
                
        except (ValueError, TypeError) as e:
            errors.append(f"Parameter '{param_name}' has invalid type: expected {param.type}, got {type(new_value).__name__}")
            continue
        
        # Range validation
        if param.type in [ParameterType.FLOAT, ParameterType.INTEGER, ParameterType.LENGTH, ParameterType.ANGLE]:
            try:
                numeric_value = float(new_value)
                if param.min_value is not None and numeric_value < param.min_value:
                    errors.append(f"Parameter '{param_name}' value {numeric_value} is below minimum {param.min_value}")
                if param.max_value is not None and numeric_value > param.max_value:
                    errors.append(f"Parameter '{param_name}' value {numeric_value} is above maximum {param.max_value}")
            except (ValueError, TypeError):
                pass  # Type error already caught above
        
        # Special validations based on feature type
        if param_name in ['radius', 'diameter'] and param.type in [ParameterType.FLOAT, ParameterType.LENGTH]:
            try:
                if float(new_value) <= 0:
                    errors.append(f"Parameter '{param_name}' must be positive")
            except (ValueError, TypeError):
                pass
                
        if param_name in ['count', 'number'] and param.type == ParameterType.INTEGER:
            try:
                if int(new_value) <= 0:
                    errors.append(f"Parameter '{param_name}' must be a positive integer")
            except (ValueError, TypeError):
                pass
    
    return errors