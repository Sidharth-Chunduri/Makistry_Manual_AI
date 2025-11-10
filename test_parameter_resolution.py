#!/usr/bin/env python3
"""
Test script for parameter resolution in feature tree parsing.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.services.feature_tree_parser import parse_cadquery_code

def test_parameter_resolution():
    """Test that variable values are properly resolved in parameters"""
    print("🧪 Testing parameter resolution in feature tree parsing...")
    
    # Test code with variables that should be resolved to numeric values
    test_code = """
import cadquery as cq

# Variables
outer_radius = 150.0
inner_radius = 10.0
thickness = 35.0
width = outer_radius / 5

# Create wheel
result = (cq.Workplane("XY")
    .circle(outer_radius)
    .extrude(thickness)
    .faces(">Z")
    .workplane()
    .circle(inner_radius)
    .cutThru())
"""
    
    try:
        tree = parse_cadquery_code(test_code, "test_project", "test_user")
        
        print(f"✅ Parsed code into feature tree with {len(tree.nodes)} nodes")
        
        # Check parameter values
        for node_id, node in tree.nodes.items():
            print(f"\n📋 Node: {node.name} ({node.feature_type})")
            for param in node.parameters:
                print(f"   - {param.name}: {param.value} ({type(param.value).__name__})")
                
                # Check if we have numeric values instead of variable names
                if isinstance(param.value, str) and param.value in ['outer_radius', 'inner_radius', 'thickness', 'width']:
                    print(f"   ❌ Parameter '{param.name}' still has variable name '{param.value}' instead of numeric value")
                    return False
                elif isinstance(param.value, (int, float)):
                    print(f"   ✅ Parameter '{param.name}' has numeric value: {param.value}")
        
        print("\n✅ All parameters resolved to proper values!")
        return True
        
    except Exception as e:
        print(f"❌ Parameter resolution test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_simple_variable_resolution():
    """Test simple variable resolution"""
    print("\n🧪 Testing simple variable resolution...")
    
    simple_code = """
import cadquery as cq

radius = 5.0
height = 10.0

result = cq.Workplane("XY").cylinder(radius, height)
"""
    
    try:
        # Let's debug the parser
        from app.services.feature_tree_parser import FeatureTreeParser
        parser = FeatureTreeParser()
        tree = parser.parse_code_to_tree(simple_code, "test_project_simple", "test_user")
        
        print(f"✅ Parsed simple code into feature tree with {len(tree.nodes)} nodes")
        print(f"📊 Variable tracker: {parser.variable_tracker}")
        
        # Check if cylinder parameters are resolved
        for node_id, node in tree.nodes.items():
            if node.feature_type.value == 'cylinder':
                print(f"\n📋 Cylinder Node: {node.name}")
                for param in node.parameters:
                    print(f"   - {param.name}: {param.value} ({type(param.value).__name__})")
                    
                    if param.name == 'arg_0' and param.value == 5.0:
                        print(f"   ✅ Radius resolved correctly: {param.value}")
                    elif param.name == 'arg_1' and param.value == 10.0:
                        print(f"   ✅ Height resolved correctly: {param.value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Simple variable resolution test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Running Parameter Resolution Tests\n")
    
    tests = [test_simple_variable_resolution, test_parameter_resolution]
    passed = 0
    
    for test in tests:
        if test():
            passed += 1
        print("-" * 50)
    
    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All parameter resolution tests passed!")
        print("Parameters should now show numeric values instead of variable names!")
    else:
        print("⚠️  Some tests failed - parameter resolution needs more work")