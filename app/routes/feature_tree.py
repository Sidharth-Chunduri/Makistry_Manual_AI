"""
Feature Tree API routes for Makistry.

Provides RESTful endpoints for managing CAD feature trees.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel
import asyncio

logger = logging.getLogger(__name__)

from app.models.feature_tree import (
    FeatureTree, FeatureNode, FeatureType, Parameter, ParameterType, FeatureReference
)
from app.services.feature_tree_storage import feature_tree_storage
from app.services.auth import get_current_user
from app.services.cad_generation_integration import cad_integration
from app.utils.parameter_validation import validate_parameter_changes
from app.agents.code_creation_aws import generate_cadquery


router = APIRouter(prefix="/feature-tree", tags=["feature-tree"])


# Request/Response models
class CreateTreeRequest(BaseModel):
    project_id: str
    name: Optional[str] = "Feature Tree"


class CreateNodeRequest(BaseModel):
    name: str
    feature_type: FeatureType
    description: Optional[str] = None
    parameters: List[Parameter] = []
    parent_references: List[FeatureReference] = []
    parent_id: Optional[str] = None
    code_fragment: Optional[str] = None


class UpdateNodeRequest(BaseModel):
    parameter_changes: Dict[str, Any]
    # regenerate_code removed - use separate /regenerate endpoint instead


class ReorderNodesRequest(BaseModel):
    new_order: List[str]


class TreeResponse(BaseModel):
    success: bool
    tree: Optional[FeatureTree] = None
    message: Optional[str] = None


class NodeResponse(BaseModel):
    success: bool
    node: Optional[FeatureNode] = None
    tree: Optional[FeatureTree] = None
    message: Optional[str] = None
    generated_code: Optional[str] = None
    execution_valid: Optional[bool] = None
    execution_result: Optional[str] = None


class VersionsResponse(BaseModel):
    success: bool
    versions: List[Dict[str, Any]] = []


class ValidNodeSuggestionsResponse(BaseModel):
    success: bool
    suggestions: List[Dict[str, str]] = []
    message: Optional[str] = None


@router.post("/create", response_model=TreeResponse)
async def create_feature_tree(
    request: CreateTreeRequest,
    user=Depends(get_current_user)
):
    """Create a new feature tree for a project"""
    try:
        user_id = user["sub"]
        tree = feature_tree_storage.create_feature_tree(
            project_id=request.project_id,
            user_id=user_id,
            name=request.name
        )
        return TreeResponse(success=True, tree=tree)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}", response_model=TreeResponse)
async def get_feature_tree(
    project_id: str,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Get feature tree for a project"""
    try:
        tree = feature_tree_storage.get_feature_tree(project_id, version)
        if not tree:
            raise HTTPException(status_code=404, detail=f"Feature tree not found for project {project_id}")
        
        return TreeResponse(success=True, tree=tree)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error in get_feature_tree for project {project_id}: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{project_id}/versions", response_model=VersionsResponse)
async def list_tree_versions(
    project_id: str,
    user=Depends(get_current_user)
):
    """List all versions of feature trees for a project"""
    try:
        versions = feature_tree_storage.list_versions(project_id)
        return VersionsResponse(success=True, versions=versions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/nodes", response_model=NodeResponse)
async def add_node(
    project_id: str,
    request: CreateNodeRequest,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Add a new node to the feature tree"""
    try:
        node = FeatureNode(
            name=request.name,
            feature_type=request.feature_type,
            description=request.description,
            parameters=request.parameters,
            parent_references=request.parent_references,
            code_fragment=request.code_fragment
        )
        
        tree = feature_tree_storage.add_node_to_tree(
            project_id=project_id,
            node=node,
            parent_id=request.parent_id,
            version=version
        )
        
        return NodeResponse(success=True, node=node, tree=tree)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{project_id}/nodes/{node_id}", response_model=TreeResponse)
async def remove_node(
    project_id: str,
    node_id: str,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Remove a node from the feature tree"""
    try:
        tree = feature_tree_storage.remove_node_from_tree(
            project_id=project_id,
            node_id=node_id,
            version=version
        )
        
        return TreeResponse(success=True, tree=tree, message=f"Node {node_id} removed")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{project_id}/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    project_id: str,
    node_id: str,
    request: UpdateNodeRequest,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Update a node's parameters instantly (Command pattern) - no CAD regeneration"""
    try:
        # Get the current tree
        tree = feature_tree_storage.get_feature_tree(project_id, version)
        if not tree:
            raise HTTPException(status_code=404, detail=f"Feature tree not found for project {project_id}")
        
        # Validate node exists
        if node_id not in tree.nodes:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found in tree")
        
        node = tree.nodes[node_id]
        
        # Validate parameter changes
        validation_errors = validate_parameter_changes(node, request.parameter_changes)
        if validation_errors:
            raise HTTPException(status_code=400, detail=f"Parameter validation failed: {', '.join(validation_errors)}")
        
        # INSTANT UPDATE: Apply parameter changes only
        updated_tree = feature_tree_storage.update_node_in_tree(
            project_id=project_id,
            node_id=node_id,
            parameter_changes=request.parameter_changes,
            version=version
        )
        
        # Mark tree as dirty (needs regeneration)
        updated_tree.dirty = True
        feature_tree_storage.save_feature_tree(updated_tree)
        
        updated_node = updated_tree.nodes.get(node_id)
        
        return NodeResponse(
            success=True,
            node=updated_node,
            tree=updated_tree,
            message="Parameters updated successfully - 3D model needs regeneration"
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _feature_tree_to_brainstorm(tree: FeatureTree) -> Dict[str, Any]:
    """Convert a feature tree back to brainstorm format for LLM regeneration"""
    
    # Extract design parameters from the tree
    design_components = []
    key_features = []
    key_functionalities = []
    optimal_geometry = {}
    
    # Get design parameters node if it exists (look for node name containing "design" or "param")
    design_params_node = None
    for node_id, node in tree.nodes.items():
        if ("design_params" in node_id.lower() or 
            "design_params" in node.name.lower() or 
            ("design" in node.name.lower() and "param" in node.name.lower())):
            design_params_node = node
            logger.info(f"Found design parameters node: {node.name} with {len(node.parameters)} parameters")
            break
    
    # Extract parameter values for optimal_geometry
    if design_params_node:
        for param in design_params_node.parameters:
            if param.name in ['outer_diameter', 'hub_diameter', 'mounting_hole_diameter', 'width', 'height', 'length', 'thickness', 'radius']:
                optimal_geometry[param.name] = f"{param.value} mm"
    
    # Analyze nodes to infer design components and features
    for node_id, node in tree.nodes.items():
        if node.feature_type == FeatureType.BOX:
            design_components.append("Rectangular body")
            key_features.append("Rectangular profile")
            key_functionalities.append("Structural support")
        elif node.feature_type == FeatureType.CYLINDER:
            design_components.append("Cylindrical body")  
            key_features.append("Cylindrical profile")
            key_functionalities.append("Rotational movement")
        elif node.feature_type == FeatureType.SPHERE:
            design_components.append("Spherical body")
            key_features.append("Spherical profile") 
            key_functionalities.append("Smooth surface")
        elif node.feature_type == FeatureType.EXTRUDE:
            design_components.append("Extruded feature")
            key_features.append("Extended geometry")
            key_functionalities.append("Volume creation")
        elif node.feature_type == FeatureType.SKETCH:
            # Infer sketch type from parameters or name
            if "circle" in node.name.lower():
                design_components.append("Circular profile")
                key_features.append("Circular cross-section")
            elif "rect" in node.name.lower():
                design_components.append("Rectangular profile")  
                key_features.append("Rectangular cross-section")
            else:
                design_components.append("Profile sketch")
                key_features.append("Custom profile")
        elif "hole" in node.name.lower():
            design_components.append("Mounting hole")
            key_features.append("Central mounting hole")
            key_functionalities.append("Attachment point")
    
    # Remove duplicates while preserving order
    design_components = list(dict.fromkeys(design_components))
    key_features = list(dict.fromkeys(key_features))
    key_functionalities = list(dict.fromkeys(key_functionalities))
    
    # Generate project name and description based on components
    project_name = "Custom Design"
    design_one_liner = f"A functional design with {', '.join(design_components[:3])}"
    
    # Create the brainstorm format
    brainstorm = {
        "project_name": project_name,
        "key_features": key_features if key_features else ["Custom geometry"],
        "key_functionalities": key_functionalities if key_functionalities else ["Functional design"],
        "design_components": design_components if design_components else ["Main body"],
        "optimal_geometry": optimal_geometry if optimal_geometry else {"length": "100 mm", "width": "50 mm", "height": "25 mm"},
        "design_one_liner": design_one_liner
    }
    
    return brainstorm


@router.post("/{project_id}/regenerate")
async def regenerate_cad_model(
    project_id: str,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """
    Custom endpoint that mimics the chat cad_edit route exactly.
    This is called by the UI when a feature tree parameter is edited.
    """
    logger.info(f"[REGENERATE] Starting regeneration using chat cad_edit pattern for project_id={project_id}")
    
    try:
        # Get required imports (same as chat)
        from app.main import _sandbox_flow, get_artifact_for_version
        from app.services import storage
        from app.services.cadam_style_parameter_extractor import CADAMStyleParameterExtractor
        
        user_id = user["sub"] if isinstance(user, dict) else user.user_id
        session_id = f"feature_tree_regen_{project_id}"
        
        # Get the current tree
        tree = feature_tree_storage.get_feature_tree(project_id, version)
        if not tree:
            raise HTTPException(status_code=404, detail=f"Feature tree not found for project {project_id}")
        
        if not tree.dirty:
            return {
                "success": True,
                "message": "Model is already up to date",
                "artifact_id": tree.last_good_artifact_id
            }
        
        requires_full_regen = getattr(tree, "needs_full_regeneration", False)
        
        # === EXACT SAME PATTERN AS chat cad_edit ===
        
        # 1. Get current CAD code (like chat gets doc = get_artifact_for_version)
        doc = get_artifact_for_version(project_id, "cad_code", None)  # Get latest
        if requires_full_regen:
            logger.info("Full feature tree regeneration required. Generating CADQuery code from tree.")
            new_code = cad_integration.regenerate_from_feature_tree(project_id, version)
        else:
            if not doc and tree.generated_code:
                # If no artifact exists but tree has code, use tree code
                current_code = tree.generated_code
            elif doc:
                current_code = doc["data"]["code"]
            else:
                # No code exists, generate from scratch
                logger.info("No existing code found, generating from feature tree")
                brainstorm = _feature_tree_to_brainstorm(tree)
                current_code, usage_stats = generate_cadquery(brainstorm)
            
            # 2. "Edit" the code based on feature tree parameters (instead of using edit_cadquery)
            logger.info("Applying CADAM-style parameter updates to existing code")
            new_code = current_code
            
            # Find design parameters node and apply updates
            design_params_node = None
            for node_id, node in tree.nodes.items():
                if ("design_params" in node_id.lower() or 
                    "design_params" in node.name.lower() or 
                    ("design" in node.name.lower() and "param" in node.name.lower())):
                    design_params_node = node
                    break
            
            if design_params_node:
                logger.info(f"Found design parameters node with {len(design_params_node.parameters)} parameters")
                extractor = CADAMStyleParameterExtractor()
                
                # Update each parameter in the code
                for param in design_params_node.parameters:
                    if param.original_variable_name:
                        logger.info(f"Updating {param.original_variable_name} = {param.value}")
                        new_code = extractor.update_parameter_in_code(
                            new_code, 
                            param.original_variable_name, 
                            param.value
                        )
        
        # 3. Get next version and store artifact (EXACT same as chat cad_edit)
        new_cad_ver = storage.next_version(project_id, "cad_code")
        storage.put_artifact(
            project_id, user_id, session_id,
            art_type="cad_code", version=new_cad_ver,
            data={"code": new_code}, parent_id=doc.get("id") if doc else None
        )
        logger.info(f"Stored CAD code artifact version {new_cad_ver}")
        
        # 4. Run STL pipeline in worker thread (EXACT same as chat cad_edit)
        sandbox_task = asyncio.create_task(asyncio.to_thread(
            _sandbox_flow,
            project_id,
            session_id,
            user_id,
            new_code,
            new_cad_ver,
            "stl",
            False,  # add_message=False (we don't want chat message for feature tree regen)
        ))
        
        # 5. Wait for sandbox task to complete (EXACT same as chat cad_edit)
        while not sandbox_task.done():
            await asyncio.sleep(0.1)  # Similar to chat's keepalive pattern
        
        # Propagate any exception (like chat does)
        await sandbox_task
        
        logger.info(f"Completed _sandbox_flow for version {new_cad_ver}")
        
        # 6. Update tree state 
        tree.generated_code = new_code
        tree.dirty = False
        if hasattr(tree, "needs_full_regeneration"):
            tree.needs_full_regeneration = False
        tree.last_good_artifact_id = f"cad_file_{new_cad_ver}_{project_id}"
        feature_tree_storage.save_feature_tree(tree)
        
        logger.info("Feature tree regeneration completed using chat cad_edit pattern")
        
        return {
            "success": True,
            "message": "Parameter changes applied - 3D model updated successfully",
            "artifact_id": tree.last_good_artifact_id,
            "cad_version": new_cad_ver,
            "code_regenerated": True,
            "pipeline_mode": "exact_same_as_chat_cad_edit"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REGENERATE] Failed: {e}")
        import traceback
        logger.error(f"[REGENERATE] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/reorder", response_model=TreeResponse)
async def reorder_nodes(
    project_id: str,
    request: ReorderNodesRequest,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Reorder the regeneration sequence of nodes"""
    try:
        tree = feature_tree_storage.reorder_nodes(
            project_id=project_id,
            new_order=request.new_order,
            version=version
        )
        
        return TreeResponse(success=True, tree=tree, message="Nodes reordered successfully")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/version", response_model=TreeResponse)
async def create_new_version(
    project_id: str,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Create a new version of the feature tree"""
    try:
        user_id = user["sub"]
        
        # Get the base tree
        base_tree = feature_tree_storage.get_feature_tree(project_id, version)
        if not base_tree:
            raise HTTPException(status_code=404, detail="Base feature tree not found")
        
        new_tree = feature_tree_storage.create_new_version(base_tree, user_id)
        return TreeResponse(success=True, tree=new_tree)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/validate", response_model=Dict[str, Any])
async def validate_tree(
    project_id: str,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Validate the feature tree structure"""
    try:
        tree = feature_tree_storage.get_feature_tree(project_id, version)
        if not tree:
            raise HTTPException(status_code=404, detail="Feature tree not found")
        
        errors = tree.validate_tree()
        return {
            "success": True,
            "is_valid": len(errors) == 0,
            "errors": errors,
            "node_count": len(tree.nodes),
            "root_node_id": tree.root_node_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/generate-code")
async def generate_code_from_tree(
    project_id: str,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Generate CADQuery code from the feature tree"""
    try:
        tree = feature_tree_storage.get_feature_tree(project_id, version)
        if not tree:
            raise HTTPException(status_code=404, detail="Feature tree not found")
        
        # Validate tree first
        errors = tree.validate_tree()
        if errors:
            raise HTTPException(status_code=400, detail=f"Tree validation failed: {errors}")
        
        # Generate code by concatenating code fragments in regeneration order
        code_fragments = []
        code_fragments.append("import cadquery as cq")
        code_fragments.append("")
        
        for node_id in tree.regeneration_order:
            node = tree.nodes[node_id]
            if node.code_fragment:
                code_fragments.append(f"# Feature: {node.name} ({node.feature_type})")
                code_fragments.append(node.code_fragment)
                code_fragments.append("")
        
        # Ensure we have a result variable
        if "result = " not in "\n".join(code_fragments):
            # Find the last solid-creating operation and assign it to result
            for node_id in reversed(tree.regeneration_order):
                node = tree.nodes[node_id]
                if node.feature_type in [FeatureType.EXTRUDE, FeatureType.REVOLVE, FeatureType.BOX, 
                                       FeatureType.CYLINDER, FeatureType.SPHERE]:
                    code_fragments.append(f"result = {node_id}")
                    break
        
        generated_code = "\n".join(code_fragments)
        
        # Update the tree with generated code
        tree.generated_code = generated_code
        feature_tree_storage.save_feature_tree(tree)
        
        return {
            "success": True,
            "code": generated_code,
            "node_count": len(tree.nodes),
            "code_length": len(generated_code)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/suggest-nodes", response_model=ValidNodeSuggestionsResponse)
async def suggest_valid_nodes(
    project_id: str,
    parent_id: Optional[str] = Query(None, description="Parent node ID to suggest children for"),
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Get suggestions for valid node types that can be added to the tree"""
    try:
        tree = feature_tree_storage.get_feature_tree(project_id, version)
        if not tree:
            raise HTTPException(status_code=404, detail="Feature tree not found")
        
        from app.services.feature_tree_validator import feature_tree_validator
        suggestions = feature_tree_validator.suggest_valid_additions(tree, parent_id)
        
        message = None
        if parent_id and parent_id in tree.nodes:
            parent_node = tree.nodes[parent_id]
            message = f"Suggestions for adding children to '{parent_node.name}' ({parent_node.feature_type.value})"
        elif not parent_id:
            message = "General suggestions for adding nodes to the feature tree"
        
        return ValidNodeSuggestionsResponse(
            success=True,
            suggestions=suggestions,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{project_id}")
async def delete_feature_tree(
    project_id: str,
    version: Optional[int] = Query(None),
    user=Depends(get_current_user)
):
    """Delete feature tree(s) for a project"""
    try:
        deleted = feature_tree_storage.delete_feature_tree(project_id, version)
        if deleted:
            return {"success": True, "message": "Feature tree deleted"}
        else:
            raise HTTPException(status_code=404, detail="Feature tree not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
