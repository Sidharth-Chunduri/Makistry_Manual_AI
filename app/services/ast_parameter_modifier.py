"""
AST-based parameter modification for CADQuery code.

This follows CadQuery's own approach for parametric models - modify variable 
assignments in the AST rather than trying to regenerate code from fragments.
"""

import ast
import copy
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class ParameterInfo:
    """Information about a parameter found in the code"""
    name: str
    value: Any
    line_number: int
    node: ast.AST
    

class ASTParameterModifier:
    """
    Modifies CADQuery code parameters using AST manipulation.
    
    This is the proper way to handle parametric CADQuery models - modify
    variable values in place rather than regenerating entire code.
    """
    
    def __init__(self, original_code: str):
        self.original_code = original_code
        self.tree = ast.parse(original_code)
        self.parameters = self._extract_parameters()
    
    def _extract_parameters(self) -> Dict[str, ParameterInfo]:
        """Extract all parameter assignments from the code"""
        parameters = {}
        
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                # Handle simple assignments like: radius = 5.0
                if (len(node.targets) == 1 and 
                    isinstance(node.targets[0], ast.Name) and
                    isinstance(node.value, (ast.Constant, ast.Num))):
                    
                    var_name = node.targets[0].id
                    value = self._extract_value(node.value)
                    
                    parameters[var_name] = ParameterInfo(
                        name=var_name,
                        value=value,
                        line_number=node.lineno,
                        node=node
                    )
        
        return parameters
    
    def _extract_value(self, node: ast.AST) -> Any:
        """Extract value from AST node"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # Python < 3.8 compatibility
            return node.n
        elif isinstance(node, ast.Str):  # Python < 3.8 compatibility
            return node.s
        else:
            return None
    
    def modify_parameter(self, param_name: str, new_value: Any) -> bool:
        """
        Modify a parameter value in the AST.
        
        Args:
            param_name: Name of the parameter to modify
            new_value: New value to assign
            
        Returns:
            True if parameter was found and modified, False otherwise
        """
        if param_name not in self.parameters:
            return False
        
        param_info = self.parameters[param_name]
        
        # Create new AST node for the value
        if isinstance(new_value, (int, float)):
            new_node = ast.Constant(value=new_value)
        elif isinstance(new_value, str):
            new_node = ast.Constant(value=new_value)
        elif isinstance(new_value, bool):
            new_node = ast.Constant(value=new_value)
        else:
            return False
        
        # Replace the value node in the assignment
        param_info.node.value = new_node
        
        # Update our tracking
        param_info.value = new_value
        
        return True
    
    def modify_parameters(self, param_changes: Dict[str, Any]) -> List[str]:
        """
        Modify multiple parameters.
        
        Args:
            param_changes: Dict mapping parameter names to new values
            
        Returns:
            List of parameter names that couldn't be modified
        """
        failed_params = []
        
        for param_name, new_value in param_changes.items():
            if not self.modify_parameter(param_name, new_value):
                failed_params.append(param_name)
        
        return failed_params
    
    def get_modified_code(self) -> str:
        """
        Get the modified code with updated parameter values.
        
        Returns:
            Modified Python code as string
        """
        # Convert AST back to code
        import astor
        return astor.to_source(self.tree)
    
    def get_modified_code_simple(self) -> str:
        """
        Get modified code using a simple string replacement approach.
        This is more reliable than astor for maintaining code formatting.
        """
        lines = self.original_code.split('\n')
        
        for param_name, param_info in self.parameters.items():
            line_idx = param_info.line_number - 1  # Convert to 0-based index
            if line_idx < len(lines):
                # Replace the line with updated parameter value
                if isinstance(param_info.value, str):
                    new_line = f"{param_name} = {repr(param_info.value)}"
                else:
                    new_line = f"{param_name} = {param_info.value}"
                
                # Preserve indentation
                original_line = lines[line_idx]
                indent = len(original_line) - len(original_line.lstrip())
                lines[line_idx] = " " * indent + new_line
        
        return '\n'.join(lines)
    
    def validate_modified_code(self) -> Tuple[bool, Optional[str]]:
        """
        Validate that the modified code has valid syntax.
        
        Returns:
            (is_valid, error_message)
        """
        try:
            modified_code = self.get_modified_code_simple()
            ast.parse(modified_code)
            return True, None
        except SyntaxError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Validation error: {e}"


def modify_cadquery_parameters(original_code: str, 
                             parameter_changes: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Modify CADQuery code parameters using AST manipulation.
    
    Args:
        original_code: Original CADQuery Python code
        parameter_changes: Dict mapping parameter names to new values
        
    Returns:
        (modified_code, failed_parameters)
    """
    modifier = ASTParameterModifier(original_code)
    failed_params = modifier.modify_parameters(parameter_changes)
    modified_code = modifier.get_modified_code_simple()
    
    return modified_code, failed_params