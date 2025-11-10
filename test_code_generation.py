#!/usr/bin/env python3
"""
Test code regeneration to ensure valid Python syntax.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_code_regeneration():
    """Test that regenerated code has valid Python syntax"""
    print("🧪 Testing code regeneration syntax...")
    
    # Create a simple feature tree
    from app.services.feature_tree_parser import parse_cadquery_code
    from app.services.cad_generation_integration import CADGenerationIntegration
    from app.services.feature_tree_storage import InMemoryFeatureTreeStorage
    
    simple_code = """
import cadquery as cq

radius = 50.0
height = 10.0

result = cq.Workplane("XY").circle(radius).extrude(height)
"""
    
    try:
        # Parse the code
        tree = parse_cadquery_code(simple_code, "test_regen", "test_user")
        print(f"✅ Parsed code into feature tree with {len(tree.nodes)} nodes")
        
        # Store it in memory storage
        storage = InMemoryFeatureTreeStorage()
        storage.save_feature_tree(tree)
        
        # Create integration service
        integration = CADGenerationIntegration(storage)
        
        # Regenerate code
        regenerated_code = integration.regenerate_from_feature_tree("test_regen")
        print(f"✅ Regenerated code length: {len(regenerated_code)} characters")
        
        print("\n📋 Regenerated code:")
        print("-" * 40)
        print(regenerated_code)
        print("-" * 40)
        
        # Test syntax by compiling
        try:
            compile(regenerated_code, '<string>', 'exec')
            print("✅ Regenerated code has valid Python syntax!")
            return True
        except SyntaxError as e:
            print(f"❌ Syntax error in regenerated code: {e}")
            print(f"   Line {e.lineno}: {e.text}")
            return False
        
    except Exception as e:
        print(f"❌ Code regeneration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing Code Regeneration\n")
    
    if test_code_regeneration():
        print("\n🎉 Code regeneration works correctly!")
        print("Generated code has valid Python syntax that can be executed.")
    else:
        print("\n⚠️  Code regeneration has syntax issues")