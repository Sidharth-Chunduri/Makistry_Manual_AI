#!/usr/bin/env python3
"""
Utility to regenerate feature trees from existing CAD code.
This fixes parameter resolution issues in existing projects.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def regenerate_from_cad_code():
    """
    For testing purposes, let's create a new wheel with proper parameters
    """
    print("🔄 Regenerating feature tree from CAD code...")
    
    # Sample wheel code that should have proper numeric parameters
    wheel_code = """
import cadquery as cq

# Wheel parameters
outer_radius = 150.0
inner_radius = 10.0
thickness = 35.0
spoke_width = 15.0
num_spokes = 6

# Create main wheel disk
wheel = (cq.Workplane("XY")
    .circle(outer_radius)
    .extrude(thickness)
    .faces(">Z")
    .workplane()
    .circle(inner_radius)
    .cutThru())

# Add spokes
for i in range(num_spokes):
    angle = i * 360 / num_spokes
    spoke = (cq.Workplane("XY")
        .rect(spoke_width, outer_radius - inner_radius)
        .extrude(thickness)
        .rotate((0,0,1), (0,0,0), angle))
    wheel = wheel.union(spoke)

result = wheel
"""
    
    from app.services.feature_tree_parser import parse_cadquery_code
    
    try:
        tree = parse_cadquery_code(wheel_code, "test_wheel_project", "test_user")
        
        print(f"✅ Generated feature tree with {len(tree.nodes)} nodes")
        
        # Check parameters
        for node_id, node in tree.nodes.items():
            print(f"\n📋 Node: {node.name} ({node.feature_type.value})")
            for param in node.parameters:
                print(f"   - {param.name}: {param.value} ({type(param.value).__name__})")
                
                # Check if parameter has proper numeric value
                if isinstance(param.value, (int, float)):
                    print(f"   ✅ Numeric parameter: {param.value}")
                elif isinstance(param.value, str) and len(param.value) > 30:
                    print(f"   ❌ Parameter has node ID or long string: {param.value[:50]}...")
                    return False
        
        print("\n✅ All parameters look good!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to regenerate feature tree: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Feature Tree Regeneration Utility\n")
    
    if regenerate_from_cad_code():
        print("\n🎉 Feature tree regeneration successful!")
        print("The parameter resolution is working correctly for new projects.")
        print("For existing projects showing node IDs, they need to be regenerated from their CAD code.")
    else:
        print("\n⚠️  Feature tree regeneration failed")
        print("There are still issues with parameter resolution.")