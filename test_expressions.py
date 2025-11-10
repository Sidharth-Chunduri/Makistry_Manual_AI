#!/usr/bin/env python3
"""
Test arithmetic expressions in feature tree parsing.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.services.feature_tree_parser import parse_cadquery_code

def test_arithmetic_expressions():
    """Test that arithmetic expressions are properly resolved"""
    print("🧪 Testing arithmetic expressions...")
    
    test_code = """
import cadquery as cq

# Variables with arithmetic
radius = 150.0
width = radius / 5
height = 35.0
small_radius = radius - 140.0

# Create shape
result = (cq.Workplane("XY")
    .circle(radius)
    .extrude(height)
    .faces(">Z")
    .workplane()
    .circle(small_radius)
    .cutThru())
"""
    
    try:
        tree = parse_cadquery_code(test_code, "test_expressions", "test_user")
        
        print(f"✅ Parsed code into feature tree with {len(tree.nodes)} nodes")
        print(f"📊 Variable tracker: {tree.nodes}")
        
        # Check parameter values
        for node_id, node in tree.nodes.items():
            print(f"\n📋 Node: {node.name} ({node.feature_type.value})")
            for param in node.parameters:
                print(f"   - {param.name}: {param.value} ({type(param.value).__name__})")
                
                # Check if we have numeric values instead of expressions
                if isinstance(param.value, (int, float)):
                    print(f"   ✅ Numeric parameter: {param.value}")
                elif isinstance(param.value, str) and len(param.value) > 20:
                    print(f"   ❌ Parameter still has long string/ID: {param.value[:30]}...")
                    return False
        
        print("\n✅ All arithmetic expressions resolved properly!")
        return True
        
    except Exception as e:
        print(f"❌ Expression test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing Arithmetic Expression Resolution\n")
    
    if test_arithmetic_expressions():
        print("\n🎉 Arithmetic expressions work correctly!")
    else:
        print("\n⚠️  Arithmetic expression resolution needs more work")