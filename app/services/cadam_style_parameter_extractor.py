"""
CADAM-Style Parameter Extractor for CADQuery Code

Extracts meaningful design parameters from variable declarations,
similar to how CADAM handles OpenSCAD parameters.
"""
import re
from typing import Dict, List, Optional, Union, Tuple
import ast
from app.models.feature_tree import Parameter, ParameterType


class CADAMStyleParameterExtractor:
    """Extract parameters from CADQuery code using CADAM's variable-first approach"""
    
    def __init__(self):
        # Parameter type mapping based on variable names
        self.type_patterns = {
            ParameterType.FLOAT: [
                r'.*radius.*', r'.*diameter.*', r'.*width.*', r'.*height.*', 
                r'.*thickness.*', r'.*depth.*', r'.*length.*', r'.*size.*',
                r'.*distance.*', r'.*offset.*', r'.*spacing.*'
            ],
            ParameterType.INTEGER: [
                r'.*count.*', r'.*number.*', r'.*quantity.*', r'.*steps.*'
            ],
            ParameterType.ANGLE: [
                r'.*angle.*', r'.*rotation.*', r'.*degrees.*'
            ],
            ParameterType.LENGTH: [
                r'.*radius.*', r'.*diameter.*', r'.*width.*', r'.*height.*',
                r'.*thickness.*', r'.*depth.*', r'.*length.*'
            ]
        }

    def extract_parameters_from_code(self, code: str) -> List[Parameter]:
        """
        Extract parameters from CADQuery code variable declarations.
        
        Like CADAM, focuses on the top section before main operations.
        """
        parameters = []
        
        # Split code into lines and process the parameter section
        lines = code.split('\n')
        parameter_section = self._extract_parameter_section(lines)
        
        # Parse variable assignments in the parameter section
        for line_num, line in enumerate(parameter_section):
            stripped = line.strip()
            if self._is_parameter_line(stripped):
                param = self._parse_parameter_line(stripped)
                if param:
                    parameters.append(param)
        
        return parameters
    
    def _extract_parameter_section(self, lines: List[str]) -> List[str]:
        """
        Extract the parameter section (like CADAM does for OpenSCAD).
        Stops at the first function/class definition or complex operation.
        """
        parameter_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue
            
            # Skip imports
            if stripped.startswith('import ') or stripped.startswith('from '):
                continue
                
            # Stop at function definitions, class definitions, or complex operations
            if (stripped.startswith('def ') or 
                stripped.startswith('class ') or
                'cq.Workplane' in stripped or
                '.extrude(' in stripped or
                '.circle(' in stripped):
                break
                
            parameter_lines.append(line)
        
        return parameter_lines
    
    def _is_parameter_line(self, line: str) -> bool:
        """Check if a line contains a parameter assignment"""
        # Match: variable_name = value
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*.+', line))
    
    def _parse_parameter_line(self, line: str) -> Optional[Parameter]:
        """Parse a single parameter line into a Parameter object"""
        try:
            # Extract variable name and value
            match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)', line)
            if not match:
                return None
            
            var_name = match.group(1).strip()
            value_str = match.group(2).strip()
            
            # Parse the value using AST (safer than eval)
            try:
                parsed_value = ast.literal_eval(value_str)
            except:
                # If AST fails, try simple numeric parsing
                try:
                    if '.' in value_str:
                        parsed_value = float(value_str)
                    else:
                        parsed_value = int(value_str)
                except:
                    parsed_value = value_str  # Keep as string
            
            # Determine parameter type and metadata
            param_type = self._determine_parameter_type(var_name, parsed_value)
            display_name = self._create_display_name(var_name)
            units = self._determine_units(var_name, param_type)
            min_val, max_val = self._calculate_parameter_range(parsed_value, param_type)
            
            return Parameter(
                name=display_name,  # Human-readable name
                value=parsed_value,
                type=param_type,
                description=f"Design parameter: {display_name}",
                units=units,
                min_value=min_val,
                max_value=max_val,
                original_variable_name=var_name  # Store original for code updates
            )
            
        except Exception as e:
            print(f"Error parsing parameter line '{line}': {e}")
            return None
    
    def _determine_parameter_type(self, var_name: str, value: any) -> ParameterType:
        """Determine parameter type based on name and value"""
        var_name_lower = var_name.lower()
        
        # Check type patterns
        for param_type, patterns in self.type_patterns.items():
            for pattern in patterns:
                if re.match(pattern, var_name_lower):
                    return param_type
        
        # Fallback based on value type
        if isinstance(value, bool):
            return ParameterType.BOOLEAN
        elif isinstance(value, int):
            return ParameterType.INTEGER
        elif isinstance(value, float):
            return ParameterType.FLOAT
        elif isinstance(value, list):
            return ParameterType.VECTOR3D if len(value) == 3 else ParameterType.POINT3D
        else:
            return ParameterType.STRING
    
    def _create_display_name(self, var_name: str) -> str:
        """Convert snake_case to Title Case (like CADAM)"""
        # Convert snake_case to words
        words = var_name.replace('_', ' ').split()
        
        # Capitalize each word
        display_name = ' '.join(word.capitalize() for word in words)
        
        return display_name
    
    def _determine_units(self, var_name: str, param_type: ParameterType) -> Optional[str]:
        """Determine units based on variable name"""
        var_name_lower = var_name.lower()
        
        if param_type == ParameterType.ANGLE:
            return "degrees"
        elif param_type in [ParameterType.LENGTH, ParameterType.FLOAT]:
            # Common measurement parameters get mm units
            measurement_keywords = ['radius', 'diameter', 'width', 'height', 'thickness', 
                                   'depth', 'length', 'size', 'distance', 'offset']
            if any(keyword in var_name_lower for keyword in measurement_keywords):
                return "mm"
        
        return None
    
    def _calculate_parameter_range(self, value: any, param_type: ParameterType) -> Tuple[Optional[float], Optional[float]]:
        """Calculate intelligent parameter ranges (like CADAM)"""
        if not isinstance(value, (int, float)):
            return None, None
        
        # CADAM-style range calculation
        if value <= 1:
            # Small values: 0 to 1
            min_val, max_val = 0.1, 1.0
        elif value <= 10:
            # Small-medium values: 0 to 2x value  
            min_val, max_val = 0.1, value * 2
        elif value <= 100:
            # Medium values: 0 to next round hundred
            min_val, max_val = 1.0, 100.0
        else:
            # Large values: 0 to 2x value
            min_val, max_val = 1.0, value * 2
        
        return min_val, max_val
    
    def update_parameter_in_code(self, code: str, original_var_name: str, new_value: any) -> str:
        """Update a parameter value in the code (like CADAM's updateParameter)"""
        lines = code.split('\n')
        updated_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Check if this line contains the variable assignment
            pattern = rf'^(\s*)({re.escape(original_var_name)})\s*=\s*.+'
            match = re.match(pattern, line)
            
            if match:
                indent = match.group(1)
                var_name = match.group(2)
                
                # Create new assignment line
                if isinstance(new_value, str) and not new_value.replace('.', '').replace('-', '').isdigit():
                    # String value - add quotes
                    new_line = f"{indent}{var_name} = \"{new_value}\""
                else:
                    # Numeric or other value
                    new_line = f"{indent}{var_name} = {new_value}"
                
                updated_lines.append(new_line)
            else:
                updated_lines.append(line)
        
        return '\n'.join(updated_lines)