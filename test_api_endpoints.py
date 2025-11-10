#!/usr/bin/env python3
"""
Test script to verify API endpoints are working after validation changes.
"""

import sys
import os
import json

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.models.feature_tree import (
    FeatureTree, FeatureNode, FeatureType, Parameter, ParameterType, FeatureReference
)
from app.services.feature_tree_storage import feature_tree_storage
from app.services.feature_tree_validator import feature_tree_validator


def test_feature_tree_creation():
    """Test that feature trees can still be created without issues"""
    print("🧪 Testing feature tree creation...")
    
    try:
        # Create a new feature tree
        tree = feature_tree_storage.create_feature_tree(
            project_id="test_api_001",
            user_id="test_user",
            name="API Test Tree"
        )
        
        print(f"✅ Feature tree created successfully: {tree.id}")
        return True
        
    except Exception as e:
        print(f"❌ Feature tree creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_valid_node_addition():
    """Test that valid nodes can still be added"""
    print("\n🧪 Testing valid node addition...")
    
    try:
        # Get or create a test tree
        tree = feature_tree_storage.get_feature_tree("test_api_002")
        if not tree:
            tree = feature_tree_storage.create_feature_tree(
                project_id="test_api_002",
                user_id="test_user",
                name="Node Addition Test"
            )
        
        # Add a valid workplane
        workplane = FeatureNode(
            name="Test Workplane",
            feature_type=FeatureType.WORKPLANE,
            parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
        )
        
        updated_tree = feature_tree_storage.add_node_to_tree(
            project_id="test_api_002",
            node=workplane
        )
        
        print(f"✅ Valid node added successfully. Tree now has {len(updated_tree.nodes)} nodes")
        return True
        
    except Exception as e:
        print(f"❌ Valid node addition failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_invalid_node_rejection():
    """Test that invalid nodes are properly rejected with helpful messages"""
    print("\n🧪 Testing invalid node rejection...")
    
    try:
        # Get or create a test tree with workplane
        tree = feature_tree_storage.get_feature_tree("test_api_003")
        if not tree:
            tree = feature_tree_storage.create_feature_tree(
                project_id="test_api_003",
                user_id="test_user",
                name="Rejection Test"
            )
            
            # Add workplane first
            workplane = FeatureNode(
                name="Base Workplane",
                feature_type=FeatureType.WORKPLANE,
                parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
            )
            tree = feature_tree_storage.add_node_to_tree(
                project_id="test_api_003",
                node=workplane
            )
        
        # Try to add invalid extrude without sketch (should fail)
        invalid_extrude = FeatureNode(
            name="Invalid Extrude",
            feature_type=FeatureType.EXTRUDE,
            parameters=[Parameter(name="distance", value=10.0, type=ParameterType.FLOAT)],
            parent_references=[FeatureReference(
                feature_id=list(tree.nodes.keys())[0],  # Reference the workplane
                entity_type="feature"
            )]
        )
        
        try:
            feature_tree_storage.add_node_to_tree(
                project_id="test_api_003",
                node=invalid_extrude,
                parent_id=list(tree.nodes.keys())[0]
            )
            print("❌ Invalid node was incorrectly allowed")
            return False
            
        except ValueError as e:
            error_msg = str(e)
            if "Invalid node addition" in error_msg and "extrude cannot be created from workplane" in error_msg:
                print("✅ Invalid node correctly rejected with helpful message")
                if "Suggested alternatives" in error_msg:
                    print("✅ Suggestions provided")
                return True
            else:
                print(f"❌ Unexpected error message: {error_msg}")
                return False
        
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_suggestions_endpoint():
    """Test that suggestions work correctly"""
    print("\n🧪 Testing suggestions system...")
    
    try:
        # Create test tree with workplane
        tree = feature_tree_storage.get_feature_tree("test_api_004")
        if not tree:
            tree = feature_tree_storage.create_feature_tree(
                project_id="test_api_004",
                user_id="test_user",
                name="Suggestions Test"
            )
            
            workplane = FeatureNode(
                name="Test Workplane",
                feature_type=FeatureType.WORKPLANE,
                parameters=[Parameter(name="plane", value="XY", type=ParameterType.STRING)]
            )
            tree = feature_tree_storage.add_node_to_tree(
                project_id="test_api_004",
                node=workplane
            )
        
        # Get suggestions for the workplane
        workplane_id = list(tree.nodes.keys())[0]
        suggestions = feature_tree_validator.suggest_valid_additions(tree, workplane_id)
        
        expected_types = ['sketch', 'box', 'cylinder', 'sphere']
        suggested_types = [s['type'] for s in suggestions]
        
        if all(t in suggested_types for t in expected_types):
            print(f"✅ Suggestions working correctly: {suggested_types}")
            return True
        else:
            print(f"❌ Incomplete suggestions: got {suggested_types}, expected {expected_types}")
            return False
        
    except Exception as e:
        print(f"❌ Suggestions test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_design_parameter_bypass():
    """Test that design parameter nodes can still be added (bypass validation)"""
    print("\n🧪 Testing design parameter node bypass...")
    
    try:
        # Create a design parameter node (like the system would)
        design_node = FeatureNode(
            id="test_project_design_params",
            name="Design Parameters",
            feature_type=FeatureType.SKETCH,  # Special case
            parameters=[
                Parameter(name="outer_radius", value=50.0, type=ParameterType.FLOAT),
                Parameter(name="inner_radius", value=10.0, type=ParameterType.FLOAT)
            ]
        )
        
        tree = feature_tree_storage.get_feature_tree("test_api_005")
        if not tree:
            tree = feature_tree_storage.create_feature_tree(
                project_id="test_api_005",
                user_id="test_user",
                name="Design Parameter Test"
            )
        
        # This should work because design parameter nodes bypass validation
        updated_tree = feature_tree_storage.add_node_to_tree(
            project_id="test_api_005",
            node=design_node
        )
        
        print(f"✅ Design parameter node added successfully (validation bypassed)")
        return True
        
    except Exception as e:
        print(f"❌ Design parameter bypass failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all API endpoint tests"""
    print("🚀 Running API Endpoint Tests After Validation Implementation\n")
    
    tests = [
        test_feature_tree_creation,
        test_valid_node_addition,
        test_invalid_node_rejection,
        test_suggestions_endpoint,
        test_design_parameter_bypass
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
        print("🎉 All API endpoint tests passed!")
        print("\n✅ Summary:")
        print("- Feature tree creation still works")
        print("- Valid node additions work")
        print("- Invalid node additions are properly rejected with helpful messages")
        print("- Suggestion system provides helpful alternatives")
        print("- Design parameter nodes can bypass validation (for system use)")
        print("\n👌 The validation system is working correctly and not breaking existing functionality!")
        return 0
    else:
        print("⚠️  Some API endpoint tests failed")
        print("\n🔍 This suggests the validation system may be too strict or has bugs")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)