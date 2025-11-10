#!/usr/bin/env python3
"""
Test parameter value extraction to ensure UI shows numeric values.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_parameter_value_extraction():
    """Test parameter value extraction from CADQuery code"""
    print("🧪 Testing parameter value extraction...")
    
    # CADQuery code with variables
    code = """
import cadquery as cq

# Parameters
outer_radius = 150.0
inner_radius = 10.0
thickness = 35.0
rim = outer_radius - 20.0

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
        from app.services.parameter_value_extractor import ParameterValueExtractor
        
        # Test parameter extraction
        extractor = ParameterValueExtractor(code)
        
        print(f"✅ Extracted variables: {extractor.variable_values}")
        
        # Test resolution of different parameter values
        test_cases = [
            ("rim", 130.0),  # Should resolve rim = outer_radius - 20.0 = 130.0
            ("outer_radius", 150.0),  # Direct variable
            ("inner_radius", 10.0),   # Direct variable
            ("thickness", 35.0),      # Direct variable
            (150.0, 150.0),          # Already numeric
            ("unknown_var", "unknown_var")  # Unknown variable
        ]
        
        print("\n📋 Testing parameter resolution:")
        all_passed = True
        
        for input_value, expected in test_cases:
            resolved = extractor.resolve_parameter_value(input_value)
            status = "✅" if resolved == expected else "❌"
            print(f"   {status} {input_value} -> {resolved} (expected: {expected})")
            if resolved != expected:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Parameter value extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_feature_tree_parameter_update():
    """Test updating feature tree parameters with actual values"""
    print("\n🧪 Testing feature tree parameter update...")
    
    code = """
import cadquery as cq

outer_diameter = 200.0
hole_size = 20.0

result = cq.Workplane("XY").circle(outer_diameter / 2).extrude(10).circle(hole_size).cutThru()
"""
    
    try:
        # Parse the code
        from app.services.feature_tree_parser import parse_cadquery_code
        tree = parse_cadquery_code(code, "test_project", "test_user")
        
        print(f"✅ Parsed feature tree with {len(tree.nodes)} nodes")
        
        # Show parameters before update
        print("\n📋 Parameters before update:")
        for node_id, node in tree.nodes.items():
            if node.parameters:
                for param in node.parameters:
                    print(f"   {node.name}.{param.name}: {param.value} ({type(param.value).__name__})")
        
        # Update with actual values
        from app.services.parameter_value_extractor import update_feature_tree_with_actual_values
        update_feature_tree_with_actual_values(tree, code)
        
        # Show parameters after update
        print("\n📋 Parameters after update:")
        numeric_params_found = False
        for node_id, node in tree.nodes.items():
            if node.parameters:
                for param in node.parameters:
                    print(f"   {node.name}.{param.name}: {param.value} ({type(param.value).__name__})")
                    if isinstance(param.value, (int, float)):
                        numeric_params_found = True
        
        if numeric_params_found:
            print("✅ Found numeric parameters after update")
            return True
        else:
            print("❌ No numeric parameters found after update")
            return False
        
    except Exception as e:
        print(f"❌ Feature tree parameter update test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing Parameter Value Extraction\n")
    
    tests = [test_parameter_value_extraction, test_feature_tree_parameter_update]
    passed = 0
    
    for test in tests:
        if test():
            passed += 1
        print("-" * 60)
    
    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 Parameter value extraction works correctly!")
        print("\n✅ This should fix the UI parameter display:")
        print("   • Parameters now show actual numeric values")
        print("   • Variable names are resolved to their values")
        print("   • Users can edit meaningful numbers instead of variable names")
    else:
        print("⚠️  Parameter value extraction needs more work")