#!/usr/bin/env python3
"""
Test the new AST-based parameter modification approach.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.services.ast_parameter_modifier import modify_cadquery_parameters, ASTParameterModifier

def test_ast_parameter_modification():
    """Test AST-based parameter modification"""
    print("🧪 Testing AST-based parameter modification...")
    
    # Sample CADQuery code with parameters
    original_code = """
import cadquery as cq

# Parameters
outer_radius = 150.0
inner_radius = 10.0
thickness = 35.0
width = 30.0

# Create wheel
result = (cq.Workplane("XY")
    .circle(outer_radius)
    .extrude(thickness)
    .faces(">Z")
    .workplane()
    .circle(inner_radius)
    .cutThru())
"""
    
    print("📋 Original code:")
    print(original_code)
    
    try:
        # Test parameter extraction
        modifier = ASTParameterModifier(original_code)
        print(f"✅ Found {len(modifier.parameters)} parameters:")
        for name, info in modifier.parameters.items():
            print(f"   - {name}: {info.value} (line {info.line_number})")
        
        # Test parameter modification
        parameter_changes = {
            'outer_radius': 200.0,
            'inner_radius': 15.0,
            'thickness': 40.0
        }
        
        print(f"\n🔧 Modifying parameters: {parameter_changes}")
        
        modified_code, failed_params = modify_cadquery_parameters(original_code, parameter_changes)
        
        if failed_params:
            print(f"❌ Failed to modify: {failed_params}")
            return False
        
        print("✅ All parameters modified successfully!")
        print("\n📋 Modified code:")
        print(modified_code)
        
        # Test syntax validation
        try:
            import ast
            ast.parse(modified_code)
            print("✅ Modified code has valid Python syntax!")
        except SyntaxError as e:
            print(f"❌ Syntax error in modified code: {e}")
            return False
        
        # Verify values were actually changed
        if 'outer_radius = 200.0' in modified_code and 'inner_radius = 15.0' in modified_code:
            print("✅ Parameter values correctly updated in code!")
            return True
        else:
            print("❌ Parameter values not found in modified code")
            return False
        
    except Exception as e:
        print(f"❌ AST parameter modification test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_syntax_preservation():
    """Test that the modification preserves syntax and structure"""
    print("\n🧪 Testing syntax preservation...")
    
    simple_code = """
import cadquery as cq

radius = 50.0
height = 10.0

result = cq.Workplane("XY").circle(radius).extrude(height)
"""
    
    try:
        modifier = ASTParameterModifier(simple_code)
        modifier.modify_parameter('radius', 75.5)
        modifier.modify_parameter('height', 15.2)
        
        modified_code = modifier.get_modified_code_simple()
        
        print("📋 Modified simple code:")
        print(modified_code)
        
        # Verify syntax
        import ast
        ast.parse(modified_code)
        
        if 'radius = 75.5' in modified_code and 'height = 15.2' in modified_code:
            print("✅ Syntax preservation test passed!")
            return True
        else:
            print("❌ Values not properly updated")
            return False
            
    except Exception as e:
        print(f"❌ Syntax preservation test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing AST-Based Parameter Modification\n")
    
    tests = [test_ast_parameter_modification, test_syntax_preservation]
    passed = 0
    
    for test in tests:
        if test():
            passed += 1
        print("-" * 50)
    
    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 AST-based parameter modification works correctly!")
        print("This approach properly modifies parameter values while preserving code structure.")
    else:
        print("⚠️  AST-based approach needs more work")