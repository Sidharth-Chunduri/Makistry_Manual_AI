"""
Feature Tree Parser for CADQuery code.

Analyzes CADQuery Python code to extract features and build a feature tree.
This allows reverse engineering existing code into the parametric feature tree structure.
"""
from __future__ import annotations

import ast
import re
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass

from app.models.feature_tree import (
    FeatureTree, FeatureNode, FeatureType, Parameter, ParameterType, FeatureReference
)


@dataclass
class CodeAnalysis:
    """Results of analyzing CADQuery code"""
    imports: List[str]
    variables: Dict[str, Any]
    function_calls: List[Dict[str, Any]]
    assignments: List[Dict[str, Any]]
    method_chains: List[Dict[str, Any]]


class FeatureTreeParser:
    """Parser to extract feature tree from CADQuery code"""
    
    # Mapping of CADQuery methods to feature types
    METHOD_TO_FEATURE = {
        # Workplane operations
        'Workplane': FeatureType.WORKPLANE,
        'workplane': FeatureType.WORKPLANE,
        
        # Sketching
        'rect': FeatureType.SKETCH,
        'circle': FeatureType.SKETCH,
        'ellipse': FeatureType.SKETCH,
        'polygon': FeatureType.SKETCH,
        'polyline': FeatureType.SKETCH,
        'spline': FeatureType.SKETCH,
        'line': FeatureType.SKETCH,
        'arc': FeatureType.SKETCH,
        
        # 3D operations
        'extrude': FeatureType.EXTRUDE,
        'revolve': FeatureType.REVOLVE,
        'loft': FeatureType.LOFT,
        'sweep': FeatureType.SWEEP,
        
        # Primitives
        'box': FeatureType.BOX,
        'cylinder': FeatureType.CYLINDER,
        'sphere': FeatureType.SPHERE,
        'cone': FeatureType.CONE,
        'torus': FeatureType.TORUS,
        
        # Boolean operations
        'union': FeatureType.UNION,
        'cut': FeatureType.DIFFERENCE,
        'intersect': FeatureType.INTERSECTION,
        'fuse': FeatureType.UNION,
        
        # Modifications
        'fillet': FeatureType.FILLET,
        'chamfer': FeatureType.CHAMFER,
        'mirror': FeatureType.MIRROR,
        
        # Patterns
        'rarray': FeatureType.PATTERN_LINEAR,
        'polarArray': FeatureType.PATTERN_CIRCULAR,
    }
    
    def __init__(self):
        self.current_tree = None
        self.variable_tracker = {}
        self.node_counter = 0
    
    def parse_code_to_tree(self, code: str, project_id: str, user_id: str) -> FeatureTree:
        """Parse CADQuery code and build a feature tree"""
        self.current_tree = FeatureTree(
            project_id=project_id,
            version=1,
            name="Parsed Feature Tree",
            created_by=user_id
        )
        self.variable_tracker = {}
        self.node_counter = 0
        
        try:
            # Parse the code into AST
            tree = ast.parse(code)
            analysis = self._analyze_ast(tree)
            
            # Extract features from the analysis
            self._extract_features_from_analysis(analysis)
            
            # Set the generated code
            self.current_tree.generated_code = code
            
            return self.current_tree
            
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse code: {e}")
    
    def _analyze_ast(self, tree: ast.AST) -> CodeAnalysis:
        """Analyze the AST to extract relevant information"""
        analysis = CodeAnalysis(
            imports=[],
            variables={},
            function_calls=[],
            assignments=[],
            method_chains=[]
        )
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    analysis.imports.append(alias.name)
            
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    analysis.imports.append(f"{module}.{alias.name}")
            
            elif isinstance(node, ast.Assign):
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    var_name = node.targets[0].id
                    analysis.assignments.append({
                        'variable': var_name,
                        'value': node.value,
                        'lineno': node.lineno
                    })
            
            elif isinstance(node, ast.Call):
                call_info = self._extract_call_info(node)
                if call_info:
                    analysis.function_calls.append(call_info)
        
        # Extract method chains from assignments
        for assignment in analysis.assignments:
            if isinstance(assignment['value'], ast.Call):
                chain = self._extract_method_chain(assignment['value'])
                if chain:
                    chain['variable'] = assignment['variable']
                    chain['lineno'] = assignment['lineno']
                    analysis.method_chains.append(chain)
        
        return analysis
    
    def _extract_call_info(self, node: ast.Call) -> Optional[Dict[str, Any]]:
        """Extract information from a function call"""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        else:
            return None
        
        args = []
        kwargs = {}
        
        for arg in node.args:
            args.append(self._extract_value(arg))
        
        for keyword in node.keywords:
            kwargs[keyword.arg] = self._extract_value(keyword.value)
        
        return {
            'function': func_name,
            'args': args,
            'kwargs': kwargs,
            'lineno': node.lineno
        }
    
    def _extract_method_chain(self, node: ast.Call) -> Optional[Dict[str, Any]]:
        """Extract a method chain from a call node"""
        chain = []
        current = node
        
        while isinstance(current, ast.Call):
            call_info = self._extract_call_info(current)
            if call_info:
                chain.insert(0, call_info)
            
            if isinstance(current.func, ast.Attribute):
                current = current.func.value
            else:
                break
        
        if chain:
            return {
                'chain': chain,
                'base': self._extract_value(current) if current else None
            }
        
        return None
    
    def _extract_value(self, node: ast.AST) -> Any:
        """Extract value from an AST node"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # Python < 3.8 compatibility
            return node.n
        elif isinstance(node, ast.Str):  # Python < 3.8 compatibility
            return node.s
        elif isinstance(node, ast.Name):
            # Try to resolve variable reference to actual value
            var_name = node.id
            if var_name in self.variable_tracker:
                resolved_value = self.variable_tracker[var_name]
                # Only return numeric values, not other variable references
                if isinstance(resolved_value, (int, float, bool)):
                    return resolved_value
                else:
                    # If the resolved value is not numeric, return a default
                    return 1.0  # Default numeric value for unresolved variables
            else:
                # Return a default numeric value if we can't resolve it
                return 1.0  # Default numeric value
        elif isinstance(node, ast.List):
            return [self._extract_value(item) for item in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(self._extract_value(item) for item in node.elts)
        elif isinstance(node, ast.BinOp):
            # Handle simple arithmetic operations
            try:
                left = self._extract_value(node.left)
                right = self._extract_value(node.right)
                
                # Only proceed if both operands are numeric
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    if isinstance(node.op, ast.Add):
                        return left + right
                    elif isinstance(node.op, ast.Sub):
                        return left - right
                    elif isinstance(node.op, ast.Mult):
                        return left * right
                    elif isinstance(node.op, ast.Div):
                        return left / right if right != 0 else 1.0
                    elif isinstance(node.op, ast.FloorDiv):
                        return left // right if right != 0 else 1.0
                    elif isinstance(node.op, ast.Mod):
                        return left % right if right != 0 else 0.0
                    elif isinstance(node.op, ast.Pow):
                        return left ** right
                
                # If we can't resolve to numbers, try to create a reasonable default
                # This handles cases like outer_radius / 5 where outer_radius might not be resolved yet
                return 1.0  # Default numeric value
                
            except (TypeError, ValueError, ZeroDivisionError):
                return 1.0  # Default numeric value
        elif isinstance(node, ast.UnaryOp):
            # Handle unary operations like -5
            try:
                operand = self._extract_value(node.operand)
                if isinstance(node.op, ast.USub):
                    return -operand
                elif isinstance(node.op, ast.UAdd):
                    return +operand
                else:
                    return f"<UnaryOp:{type(node.op).__name__}>"
            except (TypeError, ValueError):
                return f"<UnaryOp:{type(node.op).__name__}>"
        else:
            return f"<{type(node).__name__}>"
    
    def _extract_features_from_analysis(self, analysis: CodeAnalysis) -> None:
        """Extract features from the code analysis and build the tree"""
        
        # First, process variable assignments to track values
        self._build_variable_tracker(analysis)
        
        # Process method chains to create feature nodes
        for chain_info in analysis.method_chains:
            self._process_method_chain(chain_info)
        
        # Process standalone function calls
        for call in analysis.function_calls:
            if call['function'] in self.METHOD_TO_FEATURE:
                self._create_feature_node_from_call(call)
        
        # Post-process all nodes to resolve any remaining variable references
        self._resolve_parameter_variables()
    
    def _build_variable_tracker(self, analysis: CodeAnalysis) -> None:
        """Build a tracker of variable values for resolving references"""
        # First pass: find simple literal assignments
        for assignment in analysis.assignments:
            var_name = assignment['variable']
            value_node = assignment['value']
            
            # Handle simple literals first
            if isinstance(value_node, ast.Constant):
                self.variable_tracker[var_name] = value_node.value
            elif isinstance(value_node, ast.Num):  # Python < 3.8
                self.variable_tracker[var_name] = value_node.n
            elif isinstance(value_node, ast.Str):  # Python < 3.8
                self.variable_tracker[var_name] = value_node.s
        
        # Multiple passes to resolve complex expressions that depend on other variables
        max_passes = 3
        for pass_num in range(max_passes):
            resolved_any = False
            
            for assignment in analysis.assignments:
                var_name = assignment['variable']
                if var_name not in self.variable_tracker:  # Only process if not already resolved
                    try:
                        var_value = self._extract_value(assignment['value'])
                        # Store the actual value, not variable references (only basic types)
                        if isinstance(var_value, (int, float, bool)):
                            self.variable_tracker[var_name] = var_value
                            resolved_any = True
                        elif isinstance(var_value, str) and var_value.replace('.', '').replace('-', '').isdigit():
                            # Try to convert string numbers to actual numbers
                            try:
                                if '.' in var_value:
                                    self.variable_tracker[var_name] = float(var_value)
                                else:
                                    self.variable_tracker[var_name] = int(var_value)
                                resolved_any = True
                            except ValueError:
                                self.variable_tracker[var_name] = var_value
                        elif pass_num == max_passes - 1:  # Last pass, assign defaults
                            # If we can't extract the value, store a default
                            self.variable_tracker[var_name] = 1.0  # Default numeric value
                    except Exception:
                        if pass_num == max_passes - 1:  # Last pass, assign defaults
                            # If we can't extract the value, store a default
                            self.variable_tracker[var_name] = 1.0  # Default numeric value
            
            # If we didn't resolve anything new in this pass, break early
            if not resolved_any:
                break
    
    def _resolve_parameter_variables(self) -> None:
        """Post-process all feature nodes to resolve variable references in parameters"""
        for node in self.current_tree.nodes.values():
            for param in node.parameters:
                if isinstance(param.value, str) and param.value in self.variable_tracker:
                    resolved_value = self.variable_tracker[param.value]
                    
                    # Only resolve to basic numeric values, not complex types or node IDs
                    if isinstance(resolved_value, (int, float, bool)):
                        param.value = resolved_value
                        # Update parameter type if needed
                        param.type = self._infer_parameter_type(resolved_value)
                    # For node IDs, keep them as feature references (don't resolve)
    
    def _process_method_chain(self, chain_info: Dict[str, Any]) -> None:
        """Process a method chain to create feature nodes"""
        var_name = chain_info.get('variable', f"temp_{self.node_counter}")
        chain = chain_info['chain']
        
        parent_id = None
        
        for i, call in enumerate(chain):
            func_name = call['function']
            
            if func_name in self.METHOD_TO_FEATURE:
                node = self._create_feature_node_from_call(call, var_name, i)
                
                # Set parent relationship
                if parent_id:
                    node.parent_references.append(FeatureReference(
                        feature_id=parent_id,
                        entity_type="feature"
                    ))
                
                # Add to tree
                self.current_tree.add_node(node, parent_id)
                
                # Track the variable
                self.variable_tracker[var_name] = node.id
                parent_id = node.id
    
    def _create_feature_node_from_call(self, call: Dict[str, Any], 
                                     var_name: Optional[str] = None,
                                     chain_index: int = 0) -> FeatureNode:
        """Create a feature node from a function call"""
        func_name = call['function']
        feature_type = self.METHOD_TO_FEATURE.get(func_name, FeatureType.WORKPLANE)
        
        self.node_counter += 1
        node_name = var_name or f"{func_name}_{self.node_counter}"
        if chain_index > 0:
            node_name += f"_{chain_index}"
        
        # Extract parameters from args and kwargs
        parameters = []
        
        # Convert positional arguments to parameters
        for i, arg in enumerate(call['args']):
            param_name = f"arg_{i}"
            
            # Only create parameters for basic types, skip complex types like lists/tuples
            if isinstance(arg, (int, float, str, bool)):
                param_type = self._infer_parameter_type(arg)
                parameters.append(Parameter(
                    name=param_name,
                    value=arg,
                    type=param_type
                ))
        
        # Convert keyword arguments to parameters
        for key, value in call['kwargs'].items():
            # Only create parameters for basic types, skip complex types like lists/tuples
            if isinstance(value, (int, float, str, bool)):
                param_type = self._infer_parameter_type(value)
                parameters.append(Parameter(
                    name=key,
                    value=value,
                    type=param_type
                ))
        
        # Generate code fragment
        code_fragment = self._generate_code_fragment(func_name, call['args'], call['kwargs'])
        
        node = FeatureNode(
            name=node_name,
            feature_type=feature_type,
            description=f"Generated from {func_name}() call",
            parameters=parameters,
            code_fragment=code_fragment
        )
        
        return node
    
    def _infer_parameter_type(self, value: Any) -> ParameterType:
        """Infer parameter type from value"""
        if isinstance(value, bool):
            return ParameterType.BOOLEAN
        elif isinstance(value, int):
            return ParameterType.INTEGER
        elif isinstance(value, float):
            return ParameterType.FLOAT
        elif isinstance(value, str):
            return ParameterType.STRING
        elif isinstance(value, (list, tuple)) and len(value) == 3:
            return ParameterType.VECTOR3D
        else:
            return ParameterType.STRING
    
    def _generate_code_fragment(self, func_name: str, args: List[Any], kwargs: Dict[str, Any]) -> str:
        """Generate code fragment for a function call"""
        arg_strs = []
        for arg in args:
            if isinstance(arg, (int, float)):
                # Ensure numeric values are properly formatted
                arg_strs.append(str(arg))
            elif isinstance(arg, str):
                # String values need quotes
                arg_strs.append(repr(arg))
            else:
                arg_strs.append(repr(arg))
        
        kwarg_strs = []
        for k, v in kwargs.items():
            if isinstance(v, (int, float)):
                kwarg_strs.append(f"{k}={v}")
            elif isinstance(v, str):
                kwarg_strs.append(f"{k}={repr(v)}")
            else:
                kwarg_strs.append(f"{k}={repr(v)}")
        
        all_args = arg_strs + kwarg_strs
        args_str = ", ".join(all_args)
        
        return f".{func_name}({args_str})" if func_name != "Workplane" else f"cq.Workplane({args_str})"


def parse_cadquery_code(code: str, project_id: str, user_id: str) -> FeatureTree:
    """
    Parse CADQuery code and return a feature tree.
    
    Args:
        code: CADQuery Python code to parse
        project_id: Project ID for the feature tree
        user_id: User ID who owns the tree
    
    Returns:
        FeatureTree object representing the parsed code
    """
    parser = FeatureTreeParser()
    return parser.parse_code_to_tree(code, project_id, user_id)