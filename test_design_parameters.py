#!/usr/bin/env python3
"""
Test design parameter extraction to ensure UI shows meaningful parameters.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_design_parameter_extraction():
    """Test extracting meaningful design parameters from CADQuery code"""
    print("🧪 Testing design parameter extraction...")
    
    # Example wheel code with design variables
    code = """
import cadquery as cq

# Design parameters
outer_radius = 150.0
inner_radius = 10.0
thickness = 35.0
rim_radius = outer_radius - 20.0
hole_spacing = 45.0

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
        from app.services.design_parameter_extractor import DesignParameterExtractor
        
        extractor = DesignParameterExtractor(code)
        design_params = extractor.get_design_parameters()
        
        print(f"✅ Found {len(design_params)} design parameters:")
        
        expected_params = {
            'Outer Radius': 150.0,
            'Inner Radius': 10.0, 
            'Thickness': 35.0,
            'Rim Radius': 130.0,  # Should resolve expression
            'Hole Spacing': 45.0
        }
        
        all_passed = True
        for param in design_params:
            print(f"   📐 {param.name}: {param.value} ({param.type.value})")
            print(f"      Original variable: {getattr(param, 'original_variable_name', 'N/A')}")
            
            # Check if expected
            if param.name in expected_params:
                expected_value = expected_params[param.name] 
                if param.value == expected_value:
                    print(f"      ✅ Matches expected value: {expected_value}")
                else:
                    print(f"      ❌ Expected {expected_value}, got {param.value}")
                    all_passed = False
            print()
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Design parameter extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration_with_feature_tree():
    """Test integration with CAD generation"""
    print("🧪 Testing integration with feature tree...")
    
    # Simple box code
    code = """
import cadquery as cq

# Parameters
width = 50.0
height = 30.0
depth = 20.0

result = cq.Workplane("XY").box(width, height, depth)
"""
    
    try:
        from app.services.cad_generation_integration import CADGenerationWithFeatureTree
        from app.services.feature_tree_parser import parse_cadquery_code
        
        # Create a feature tree from the code
        tree = parse_cadquery_code(code, "test_project", "test_user")
        
        # Add design parameters
        integration = CADGenerationWithFeatureTree()
        integration._add_design_parameters_node(tree, code)
        
        print(f"✅ Feature tree created with {len(tree.nodes)} nodes")
        
        # Check for design parameters node
        design_node_found = False
        for node_id, node in tree.nodes.items():
            if node_id.endswith('_design_params'):
                design_node_found = True
                print(f"✅ Found design parameters node: {node.name}")
                print(f"   Parameters: {[p.name for p in node.parameters]}")
                
                # Check parameter values
                for param in node.parameters:
                    print(f"   📐 {param.name}: {param.value}")
        
        if not design_node_found:
            print("❌ No design parameters node found")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🚀 Testing Design Parameter Extraction\n")
    
    tests = [test_design_parameter_extraction, test_integration_with_feature_tree]
    passed = 0
    
    for test in tests:
        if test():
            passed += 1
        print("-" * 60)
    
    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 Design parameter extraction works correctly!")
        print("\n✅ This should provide meaningful parameters in the UI:")
        print("   • Parameters show user-friendly names like 'Outer Radius'")
        print("   • Values are actual numbers that users can edit")
        print("   • Changes map back to original variable names in code")
    else:
        print("⚠️  Design parameter extraction needs more work")