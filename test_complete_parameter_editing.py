#!/usr/bin/env python3
"""
Comprehensive test of the new parameter editing approach.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_complete_parameter_editing_flow():
    """Test the complete parameter editing flow"""
    print("🧪 Testing complete parameter editing flow...")
    
    # Sample CADQuery code
    sample_code = """
import cadquery as cq

# Parameters
outer_radius = 150.0
inner_radius = 10.0
thickness = 35.0

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
        # 1. Parse the code into a feature tree (this represents what happens when a design is created)
        from app.services.feature_tree_parser import parse_cadquery_code
        
        tree = parse_cadquery_code(sample_code, "test_project", "test_user")
        print(f"✅ Step 1: Parsed code into feature tree with {len(tree.nodes)} nodes")
        
        # Store the original code in the tree
        tree.generated_code = sample_code
        
        # 2. Display parameters (this represents what the UI shows)
        print("\n📋 Available parameters:")
        for node_id, node in tree.nodes.items():
            if node.parameters:
                print(f"   Node: {node.name}")
                for param in node.parameters:
                    print(f"     - {param.name}: {param.value} ({type(param.value).__name__})")
        
        # 3. Simulate editing a parameter (this represents what happens when user edits)
        from app.services.direct_parameter_editor import DirectParameterEditor
        from app.services.feature_tree_storage import InMemoryFeatureTreeStorage
        
        # Use in-memory storage for testing
        storage = InMemoryFeatureTreeStorage()
        storage.save_feature_tree(tree)
        
        editor = DirectParameterEditor(storage)
        
        # Find a node with numeric parameters
        target_node = None
        target_param = None
        for node in tree.nodes.values():
            for param in node.parameters:
                if isinstance(param.value, (int, float)) and param.value > 1:
                    target_node = node
                    target_param = param
                    break
            if target_node:
                break
        
        if not target_node:
            print("❌ No suitable parameter found for testing")
            return False
        
        print(f"\n🔧 Editing parameter: {target_param.name} = {target_param.value}")
        new_value = target_param.value * 1.5  # Increase by 50%
        print(f"   New value: {new_value}")
        
        # 4. Edit the parameter using direct editing
        modified_code, success = editor.edit_parameter(
            "test_project", target_node.id, target_param.name, new_value
        )
        
        if not success:
            print("❌ Parameter editing failed")
            return False
        
        print("✅ Step 2: Parameter edited successfully")
        
        # 5. Verify the code was modified correctly
        print("\n📋 Modified code:")
        print(modified_code)
        
        # 6. Verify syntax
        try:
            import ast
            ast.parse(modified_code)
            print("✅ Step 3: Modified code has valid syntax")
        except SyntaxError as e:
            print(f"❌ Syntax error in modified code: {e}")
            return False
        
        # 7. Verify the parameter value was actually changed
        if str(new_value) in modified_code:
            print("✅ Step 4: Parameter value correctly updated in code")
        else:
            print("❌ Parameter value not found in modified code")
            return False
        
        # 8. Test parameter extraction
        extracted_params = editor.extract_all_parameters("test_project")
        print(f"\n📊 Extracted parameters: {extracted_params}")
        
        if extracted_params:
            print("✅ Step 5: Parameter extraction working")
        else:
            print("❌ Parameter extraction failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Complete parameter editing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_syntax_edge_cases():
    """Test edge cases that might cause syntax errors"""
    print("\n🧪 Testing syntax edge cases...")
    
    edge_case_code = """
import cadquery as cq

# Edge case parameters
radius = 50.0
height = 10.0
angle = 45.0

# Complex chaining
result = (cq.Workplane("XY")
    .circle(radius)
    .extrude(height)
    .rotate((0,0,1), (0,0,0), angle))
"""
    
    try:
        from app.services.ast_parameter_modifier import modify_cadquery_parameters
        
        # Test multiple parameter changes
        changes = {
            'radius': 75.5,
            'height': 15.2,
            'angle': 90.0
        }
        
        modified_code, failed_params = modify_cadquery_parameters(edge_case_code, changes)
        
        if failed_params:
            print(f"❌ Failed to modify: {failed_params}")
            return False
        
        # Verify syntax
        import ast
        ast.parse(modified_code)
        
        print("✅ Edge case syntax test passed")
        return True
        
    except Exception as e:
        print(f"❌ Edge case test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Complete Parameter Editing Solution\n")
    
    tests = [test_complete_parameter_editing_flow, test_syntax_edge_cases]
    passed = 0
    
    for test in tests:
        if test():
            passed += 1
        print("-" * 60)
    
    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 Complete parameter editing solution works correctly!")
        print("\n✅ Key improvements:")
        print("   • AST-based parameter modification (no syntax errors)")
        print("   • Direct code editing (preserves structure)")
        print("   • Proper variable mapping")
        print("   • Reliable syntax validation")
        print("\nThe parameter editing feature is now ready for production! 🚀")
    else:
        print("⚠️  Some tests failed - need additional work")