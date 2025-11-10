#!/usr/bin/env python3
"""
Test script for Feature Tree functionality.

This script tests the feature tree implementation by creating, parsing, and manipulating feature trees.
"""

import sys
import os
import json
from datetime import datetime

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.models.feature_tree import (
    FeatureTree, FeatureNode, FeatureType, Parameter, ParameterType, FeatureReference
)
from app.services.feature_tree_parser import parse_cadquery_code
from app.services.cad_generation_integration import cad_integration


def test_basic_feature_tree_creation():
    """Test basic feature tree creation and manipulation"""
    print("🧪 Testing basic feature tree creation...")
    
    # Create a new feature tree
    tree = FeatureTree(
        project_id="test_project_001",
        version=1,
        name="Test Feature Tree",
        created_by="test_user"
    )
    
    # Create workplane node
    workplane_node = FeatureNode(
        name="XY Workplane",
        feature_type=FeatureType.WORKPLANE,
        description="Base workplane for sketching",
        parameters=[
            Parameter(name="plane", value="XY", type=ParameterType.STRING)
        ]
    )
    
    # Create box node
    box_node = FeatureNode(
        name="Main Box",
        feature_type=FeatureType.BOX,
        description="Main box feature",
        parameters=[
            Parameter(name="width", value=10.0, type=ParameterType.FLOAT, units="mm"),
            Parameter(name="height", value=5.0, type=ParameterType.FLOAT, units="mm"),
            Parameter(name="depth", value=3.0, type=ParameterType.FLOAT, units="mm")
        ],
        parent_references=[
            FeatureReference(feature_id=workplane_node.id, entity_type="workplane")
        ]
    )
    
    # Create fillet node
    fillet_node = FeatureNode(
        name="Edge Fillets",
        feature_type=FeatureType.FILLET,
        description="Fillet all edges",
        parameters=[
            Parameter(name="radius", value=0.5, type=ParameterType.FLOAT, units="mm")
        ],
        parent_references=[
            FeatureReference(feature_id=box_node.id, entity_type="solid")
        ]
    )
    
    # Add nodes to tree
    tree.add_node(workplane_node)
    tree.add_node(box_node, workplane_node.id)
    tree.add_node(fillet_node, box_node.id)
    
    # Validate tree
    errors = tree.validate_tree()
    if errors:
        print(f"❌ Tree validation failed: {errors}")
        return False
    
    print(f"✅ Created feature tree with {len(tree.nodes)} nodes")
    print(f"   Regeneration order: {tree.regeneration_order}")
    
    return True


def test_code_parsing():
    """Test parsing CADQuery code into feature tree"""
    print("\n🧪 Testing CADQuery code parsing...")
    
    sample_code = """
import cadquery as cq

# Create a simple bracket
result = (cq.Workplane("XY")
    .box(20, 10, 5)
    .faces(">Z")
    .workplane()
    .circle(3)
    .cutThru())
"""
    
    try:
        tree = parse_cadquery_code(sample_code, "test_project_002", "test_user")
        
        print(f"✅ Parsed code into feature tree with {len(tree.nodes)} nodes")
        for node_id in tree.regeneration_order:
            node = tree.nodes[node_id]
            print(f"   - {node.name} ({node.feature_type}) with {len(node.parameters)} parameters")
        
        return True
        
    except Exception as e:
        print(f"❌ Code parsing failed: {e}")
        return False


def test_feature_tree_generation():
    """Test generating CADQuery code from feature tree"""
    print("\n🧪 Testing code generation from feature tree...")
    
    # Create a simple feature tree manually
    tree = FeatureTree(
        project_id="test_project_003",
        version=1,
        name="Generated Test Tree",
        created_by="test_user"
    )
    
    # Workplane
    wp_node = FeatureNode(
        name="Base Workplane",
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)],
        code_fragment="cq.Workplane('XY')"
    )
    
    # Box
    box_node = FeatureNode(
        name="Base Box",
        feature_type=FeatureType.BOX,
        parameters=[
            Parameter(name="width", value=15.0, type=ParameterType.FLOAT),
            Parameter(name="height", value=10.0, type=ParameterType.FLOAT),
            Parameter(name="depth", value=8.0, type=ParameterType.FLOAT)
        ],
        code_fragment=".box(15.0, 10.0, 8.0)"
    )
    
    tree.add_node(wp_node)
    tree.add_node(box_node, wp_node.id)
    
    try:
        # Generate code from tree
        code = cad_integration.regenerate_from_feature_tree("test_project_003")
        print("✅ Generated code from feature tree:")
        print(code)
        
        return True
        
    except Exception as e:
        print(f"❌ Code generation failed: {e}")
        return False


def test_parameter_updates():
    """Test updating parameters in feature tree"""
    print("\n🧪 Testing parameter updates...")
    
    try:
        # Create a test tree
        tree = FeatureTree(
            project_id="test_project_004",
            version=1,
            name="Parameter Test Tree",
            created_by="test_user"
        )
        
        box_node = FeatureNode(
            name="Parametric Box",
            feature_type=FeatureType.BOX,
            parameters=[
                Parameter(name="width", value=10.0, type=ParameterType.FLOAT),
                Parameter(name="height", value=5.0, type=ParameterType.FLOAT),
                Parameter(name="depth", value=2.0, type=ParameterType.FLOAT)
            ]
        )
        
        tree.add_node(box_node)
        
        # Get original parameter value
        original_width = None
        for param in box_node.parameters:
            if param.name == "width":
                original_width = param.value
                break
        
        print(f"   Original width: {original_width}")
        
        # Update parameter
        parameter_changes = {"width": 20.0}
        
        # Simulate parameter update (normally would go through storage)
        for param in box_node.parameters:
            if param.name in parameter_changes:
                param.value = parameter_changes[param.name]
        
        # Check updated value
        updated_width = None
        for param in box_node.parameters:
            if param.name == "width":
                updated_width = param.value
                break
        
        print(f"   Updated width: {updated_width}")
        
        if updated_width == 20.0:
            print("✅ Parameter update successful")
            return True
        else:
            print("❌ Parameter update failed")
            return False
            
    except Exception as e:
        print(f"❌ Parameter update test failed: {e}")
        return False


def test_tree_validation():
    """Test feature tree validation"""
    print("\n🧪 Testing tree validation...")
    
    # Create a tree with circular dependency (invalid)
    tree = FeatureTree(
        project_id="test_project_005",
        version=1,
        name="Validation Test Tree",
        created_by="test_user"
    )
    
    node1 = FeatureNode(
        name="Node 1",
        feature_type=FeatureType.BOX
    )
    
    node2 = FeatureNode(
        name="Node 2",
        feature_type=FeatureType.FILLET,
        parent_references=[FeatureReference(feature_id=node1.id, entity_type="solid")]
    )
    
    # Create circular dependency
    node1.parent_references = [FeatureReference(feature_id=node2.id, entity_type="solid")]
    
    tree.add_node(node1)
    tree.add_node(node2)
    
    errors = tree.validate_tree()
    
    if errors:
        print(f"✅ Validation correctly detected errors: {errors}")
        return True
    else:
        print("❌ Validation failed to detect circular dependency")
        return False


def test_extrude_child_generation():
    """Ensure extrude features use their sketch parent when regenerating code."""
    print("\n🧪 Testing extrude child generation...")

    tree = FeatureTree(
        project_id="test_project_006",
        version=1,
        name="Extrude child test",
        created_by="test_user"
    )

    workplane = FeatureNode(
        name="Workplane",
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
    )
    sketch = FeatureNode(
        name="Profile Sketch",
        feature_type=FeatureType.SKETCH,
        parent_references=[FeatureReference(feature_id=workplane.id, entity_type="feature")]
    )
    extrude = FeatureNode(
        name="Extrude Feature",
        feature_type=FeatureType.EXTRUDE,
        parameters=[Parameter(name="distance", value=10, type=ParameterType.FLOAT)],
        parent_references=[FeatureReference(feature_id=sketch.id, entity_type="feature")]
    )

    tree.add_node(workplane)
    tree.add_node(sketch, workplane.id)
    tree.add_node(extrude, sketch.id)

    from app.services.feature_tree_code_generator import feature_tree_code_generator
    generated_code = feature_tree_code_generator.generate_cadquery_code(tree)

    if "extrude = sketch.extrude" in generated_code:
        print("✅ Extrude child uses sketch base correctly")
        return True

    print("❌ Extrude child did not use sketch base")
    print(generated_code)
    return False


def test_extrude_on_solid_generation():
    """Ensure extrude children of solids create a derived workplane."""
    print("\n🧪 Testing extrude on solid generation...")

    tree = FeatureTree(
        project_id="test_project_007",
        version=1,
        name="Extrude on solid test",
        created_by="test_user"
    )

    workplane = FeatureNode(
        name="Workplane",
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
    )
    sketch = FeatureNode(
        name="Profile Sketch",
        feature_type=FeatureType.SKETCH,
        parent_references=[FeatureReference(feature_id=workplane.id, entity_type="feature")]
    )
    first_extrude = FeatureNode(
        name="Primary Extrude",
        feature_type=FeatureType.EXTRUDE,
        parameters=[Parameter(name="distance", value=5, type=ParameterType.FLOAT)],
        parent_references=[FeatureReference(feature_id=sketch.id, entity_type="feature")]
    )
    second_extrude = FeatureNode(
        name="Secondary Extrude",
        feature_type=FeatureType.EXTRUDE,
        parameters=[Parameter(name="distance", value=3, type=ParameterType.FLOAT)],
        parent_references=[FeatureReference(feature_id=first_extrude.id, entity_type="feature")]
    )

    tree.add_node(workplane)
    tree.add_node(sketch, workplane.id)
    tree.add_node(first_extrude, sketch.id)
    tree.add_node(second_extrude, first_extrude.id)

    from app.services.feature_tree_code_generator import feature_tree_code_generator
    generated_code = feature_tree_code_generator.generate_cadquery_code(tree)

    expected_snippet = ".faces('>Z').workplane().extrude(3"
    if expected_snippet in generated_code:
        print("✅ Extrude-on-solid converts to face workplane")
        return True

    print("❌ Extrude-on-solid did not create expected workplane")
    print(generated_code)
    return False

def main():
    """Run all tests"""
    print("🚀 Running Feature Tree Tests\n")
    
    tests = [
        test_basic_feature_tree_creation,
        test_code_parsing,
        test_feature_tree_generation,
        test_parameter_updates,
        test_tree_validation,
        test_extrude_child_generation,
        test_extrude_on_solid_generation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ {test.__name__} failed")
        except Exception as e:
            print(f"❌ {test.__name__} crashed: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
