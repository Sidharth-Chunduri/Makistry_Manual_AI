#!/usr/bin/env python3
"""
Test script for validating feature tree node addition logic.

This script tests the new validation system to ensure it prevents illegal node additions
that wouldn't affect the final model.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.models.feature_tree import (
    FeatureTree, FeatureNode, FeatureType, Parameter, ParameterType, FeatureReference
)
from app.services.feature_tree_validator import feature_tree_validator


def test_valid_workplane_addition():
    """Test that adding a workplane to an empty tree is valid"""
    print("🧪 Testing valid workplane addition...")
    
    tree = FeatureTree(
        project_id="test_001",
        version=1,
        name="Empty Tree",
        created_by="test_user"
    )
    
    workplane_node = FeatureNode(
        name="XY Workplane",
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
    )
    
    is_valid, errors = feature_tree_validator.validate_node_addition(tree, workplane_node)
    
    if is_valid:
        print("✅ Workplane addition correctly validated as valid")
        return True
    else:
        print(f"❌ Workplane addition incorrectly rejected: {errors}")
        return False


def test_invalid_extrude_without_sketch():
    """Test that adding an extrude without a sketch is invalid"""
    print("\n🧪 Testing invalid extrude without sketch...")
    
    tree = FeatureTree(
        project_id="test_002",
        version=1,
        name="Tree with Workplane",
        created_by="test_user"
    )
    
    # Add workplane first
    workplane = FeatureNode(
        name="XY Workplane",
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
    )
    tree.add_node(workplane)
    
    # Try to add extrude directly to workplane (should fail)
    extrude_node = FeatureNode(
        name="Invalid Extrude",
        feature_type=FeatureType.EXTRUDE,
        parameters=[Parameter(name="distance", value=10.0, type=ParameterType.FLOAT)],
        parent_references=[FeatureReference(feature_id=workplane.id, entity_type="feature")]
    )
    
    is_valid, errors = feature_tree_validator.validate_node_addition(tree, extrude_node, workplane.id)
    
    if not is_valid:
        print(f"✅ Extrude without sketch correctly rejected: {errors[0]}")
        return True
    else:
        print("❌ Extrude without sketch incorrectly allowed")
        return False


def test_valid_sketch_extrude_sequence():
    """Test that a proper sketch -> extrude sequence is valid"""
    print("\n🧪 Testing valid sketch -> extrude sequence...")
    
    tree = FeatureTree(
        project_id="test_003",
        version=1,
        name="Tree with Workplane",
        created_by="test_user"
    )
    
    # Add workplane
    workplane = FeatureNode(
        name="XY Workplane", 
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
    )
    tree.add_node(workplane)
    
    # Add sketch to workplane
    sketch = FeatureNode(
        name="Circle Sketch",
        feature_type=FeatureType.SKETCH,
        parameters=[Parameter(name="radius", value=5.0, type=ParameterType.FLOAT)],
        parent_references=[FeatureReference(feature_id=workplane.id, entity_type="feature")]
    )
    
    is_valid, errors = feature_tree_validator.validate_node_addition(tree, sketch, workplane.id)
    if not is_valid:
        print(f"❌ Sketch addition failed: {errors}")
        return False
    
    tree.add_node(sketch, workplane.id)
    
    # Add extrude to sketch
    extrude = FeatureNode(
        name="Cylinder Extrude",
        feature_type=FeatureType.EXTRUDE,
        parameters=[Parameter(name="distance", value=10.0, type=ParameterType.FLOAT)],
        parent_references=[FeatureReference(feature_id=sketch.id, entity_type="feature")]
    )
    
    is_valid, errors = feature_tree_validator.validate_node_addition(tree, extrude, sketch.id)
    
    if is_valid:
        print("✅ Valid sketch -> extrude sequence correctly validated")
        return True
    else:
        print(f"❌ Valid sequence incorrectly rejected: {errors}")
        return False


def test_boolean_operation_validation():
    """Test that boolean operations require two solids"""
    print("\n🧪 Testing boolean operation validation...")
    
    tree = FeatureTree(
        project_id="test_004",
        version=1,
        name="Tree with One Box",
        created_by="test_user"
    )
    
    # Add workplane and box
    workplane = FeatureNode(
        name="XY Workplane",
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
    )
    tree.add_node(workplane)
    
    box = FeatureNode(
        name="Box 1",
        feature_type=FeatureType.BOX,
        parameters=[
            Parameter(name="width", value=10.0, type=ParameterType.FLOAT),
            Parameter(name="height", value=10.0, type=ParameterType.FLOAT),
            Parameter(name="depth", value=10.0, type=ParameterType.FLOAT)
        ],
        parent_references=[FeatureReference(feature_id=workplane.id, entity_type="feature")]
    )
    tree.add_node(box, workplane.id)
    
    # Try to add union with only one solid (should fail)
    union_node = FeatureNode(
        name="Invalid Union",
        feature_type=FeatureType.UNION,
        parent_references=[FeatureReference(feature_id=box.id, entity_type="feature")]
    )
    
    is_valid, errors = feature_tree_validator.validate_node_addition(tree, union_node, box.id)
    
    if not is_valid and "requires 2 solid parents" in errors[0]:
        print("✅ Boolean operation with insufficient solids correctly rejected")
        return True
    else:
        print(f"❌ Boolean operation validation failed: valid={is_valid}, errors={errors}")
        return False


def test_circular_dependency_detection():
    """Test that circular dependencies are detected"""
    print("\n🧪 Testing circular dependency detection...")
    
    tree = FeatureTree(
        project_id="test_005",
        version=1,
        name="Tree for Circular Test",
        created_by="test_user"
    )
    
    # Add workplane and box
    workplane = FeatureNode(
        name="XY Workplane",
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
    )
    tree.add_node(workplane)
    
    box = FeatureNode(
        name="Box 1", 
        feature_type=FeatureType.BOX,
        parameters=[
            Parameter(name="width", value=10.0, type=ParameterType.FLOAT),
            Parameter(name="height", value=10.0, type=ParameterType.FLOAT),
            Parameter(name="depth", value=10.0, type=ParameterType.FLOAT)
        ],
        parent_references=[FeatureReference(feature_id=workplane.id, entity_type="feature")]
    )
    tree.add_node(box, workplane.id)
    
    # Try to create a circular dependency by referencing box from workplane
    circular_node = FeatureNode(
        name="Circular Node",
        feature_type=FeatureType.FILLET,
        parameters=[Parameter(name="radius", value=1.0, type=ParameterType.FLOAT)],
        parent_references=[FeatureReference(feature_id=box.id, entity_type="feature")]
    )
    
    # Artificially create circular reference for testing
    circular_node.id = workplane.id  # This should create a cycle
    
    is_valid, errors = feature_tree_validator.validate_node_addition(tree, circular_node)
    
    if not is_valid and "circular dependency" in str(errors).lower():
        print("✅ Circular dependency correctly detected")
        return True
    else:
        print(f"❌ Circular dependency not detected: valid={is_valid}, errors={errors}")
        return False


def test_suggestion_system():
    """Test that the suggestion system provides helpful alternatives"""
    print("\n🧪 Testing suggestion system...")
    
    tree = FeatureTree(
        project_id="test_006",
        version=1,
        name="Tree for Suggestions",
        created_by="test_user"
    )
    
    # Add workplane
    workplane = FeatureNode(
        name="XY Workplane",
        feature_type=FeatureType.WORKPLANE,
        parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
    )
    tree.add_node(workplane)
    
    # Get suggestions for workplane
    suggestions = feature_tree_validator.suggest_valid_additions(tree, workplane.id)
    
    # Should suggest sketch, box, cylinder, sphere
    suggested_types = [s['type'] for s in suggestions]
    expected_types = ['sketch', 'box', 'cylinder', 'sphere']
    
    if all(t in suggested_types for t in expected_types):
        print(f"✅ Suggestion system working: {suggested_types}")
        return True
    else:
        print(f"❌ Suggestion system incomplete: got {suggested_types}, expected {expected_types}")
        return False


def main():
    """Run all validation tests"""
    print("🚀 Running Feature Tree Node Validation Tests\n")
    
    tests = [
        test_valid_workplane_addition,
        test_invalid_extrude_without_sketch,
        test_valid_sketch_extrude_sequence,
        test_boolean_operation_validation,
        test_circular_dependency_detection,
        test_suggestion_system
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
            import traceback
            traceback.print_exc()
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All validation tests passed!")
        print("\n📋 Summary of implemented validation:")
        print("- ✅ Prevents invalid parent-child relationships")
        print("- ✅ Detects nodes that won't affect the final model")
        print("- ✅ Validates boolean operations have sufficient inputs")
        print("- ✅ Detects circular dependencies")
        print("- ✅ Provides helpful suggestions for valid node types")
        return 0
    else:
        print("⚠️  Some validation tests failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)