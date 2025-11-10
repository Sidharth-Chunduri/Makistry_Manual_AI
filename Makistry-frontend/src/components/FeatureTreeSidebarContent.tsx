/**
 * Simplified Feature Tree Component for Sidebar
 * 
 * This is a streamlined version of the FeatureTree component designed
 * specifically for use in the collapsible sidebar.
 */
import React, { useState, useEffect } from 'react';
import { fetchFeatureTree, updateFeatureTreeNode, regenerateCADModel, createFeatureTreeNode } from '@/lib/api/feature-tree';
import { ChevronRight, ChevronDown, Edit, Settings, Plus, RefreshCw } from 'lucide-react';
import { ParameterInput } from './ParameterInput';

// Types from the backend (reused from main FeatureTree)
interface Parameter {
  name: string;
  value: any;
  type: 'float' | 'integer' | 'string' | 'boolean' | 'vector3d' | 'point3d' | 'angle' | 'length';
  description?: string;
  units?: string;
  min_value?: number;
  max_value?: number;
}

interface FeatureReference {
  feature_id: string;
  entity_type: string;
  entity_index?: number;
  selection_info?: any;
}

interface FeatureNode {
  id: string;
  name: string;
  feature_type: string;
  description?: string;
  parameters: Parameter[];
  parent_references: FeatureReference[];
  child_ids: string[];
  code_fragment?: string;
  is_valid: boolean;
  error_message?: string;
  visible: boolean;
  color?: string;
  transparency?: number;
}

interface FeatureTree {
  id: string;
  project_id: string;
  version: number;
  name: string;
  description?: string;
  root_node_id?: string;
  nodes: { [key: string]: FeatureNode };
  regeneration_order: string[];
  global_parameters: Parameter[];
  generated_code?: string;
  dirty: boolean;
  needs_full_regeneration?: boolean;
  last_good_artifact_id?: string;
}

interface FeatureTreeSidebarContentProps {
  projectId: string;
  onNodeSelect?: (nodeId: string) => void;
  onParameterUpdate?: (nodeId: string, parameterName: string, value: any) => void;
  onRegenerationSuccess?: () => void;
}

type SupportedFeatureType = 'fillet' | 'chamfer' | 'box' | 'extrude' | 'cylinder' | 'sphere' | 'cone' | 'revolve' | 'mirror' | 'pattern_linear';

interface FeatureTemplateParam {
  name: string;
  label: string;
  type: Parameter['type'];
  defaultValue: number | string;
  units?: string;
  description?: string;
}

interface FeatureTemplate {
  type: SupportedFeatureType;
  label: string;
  description: string;
  parameters: FeatureTemplateParam[];
  buildCodeFragment: (params: Record<string, any>) => string;
}

const FEATURE_TEMPLATES: FeatureTemplate[] = [
  {
    type: 'fillet',
    label: 'Fillet',
    description: 'Round edges on the current solid',
    parameters: [
      { name: 'radius', label: 'Radius', type: 'float', defaultValue: 1.5, units: 'mm', description: 'Radius of the fillet (max 2mm for most geometries)' }
    ],
    buildCodeFragment: (params) => `.edges().fillet(${params.radius})`
  },
  {
    type: 'chamfer',
    label: 'Chamfer',
    description: 'Bevel edges on the current solid',
    parameters: [
      { name: 'distance', label: 'Distance', type: 'float', defaultValue: 1, units: 'mm', description: 'Distance of the chamfer' }
    ],
    buildCodeFragment: (params) => `.edges().chamfer(${params.distance})`
  },
  {
    type: 'extrude',
    label: 'Extrude',
    description: 'Create volume by extruding the selected profile',
    parameters: [
      { name: 'distance', label: 'Distance', type: 'float', defaultValue: 10, units: 'mm', description: 'Distance to extrude' }
    ],
    buildCodeFragment: (params) => `.extrude(${params.distance})`
  },
  {
    type: 'box',
    label: 'Box',
    description: 'Create a rectangular solid',
    parameters: [
      { name: 'width', label: 'Width', type: 'float', defaultValue: 10, units: 'mm', description: 'Width of the box' },
      { name: 'height', label: 'Height', type: 'float', defaultValue: 10, units: 'mm', description: 'Height of the box' },
      { name: 'depth', label: 'Depth', type: 'float', defaultValue: 10, units: 'mm', description: 'Depth of the box' }
    ],
    buildCodeFragment: (params) => `.box(${params.width}, ${params.height}, ${params.depth})`
  },
  {
    type: 'cylinder',
    label: 'Cylinder',
    description: 'Create a cylindrical solid',
    parameters: [
      { name: 'radius', label: 'Radius', type: 'float', defaultValue: 5, units: 'mm', description: 'Radius of the cylinder' },
      { name: 'height', label: 'Height', type: 'float', defaultValue: 20, units: 'mm', description: 'Height of the cylinder' }
    ],
    buildCodeFragment: (params) => `.cylinder(${params.radius}, ${params.height})`
  },
  {
    type: 'sphere',
    label: 'Sphere',
    description: 'Create a spherical solid',
    parameters: [
      { name: 'radius', label: 'Radius', type: 'float', defaultValue: 5, units: 'mm', description: 'Radius of the sphere' }
    ],
    buildCodeFragment: (params) => `.sphere(${params.radius})`
  },
  {
    type: 'cone',
    label: 'Cone',
    description: 'Create a conical solid',
    parameters: [
      { name: 'radius1', label: 'Bottom Radius', type: 'float', defaultValue: 5, units: 'mm', description: 'Radius at the bottom' },
      { name: 'radius2', label: 'Top Radius', type: 'float', defaultValue: 2, units: 'mm', description: 'Radius at the top' },
      { name: 'height', label: 'Height', type: 'float', defaultValue: 10, units: 'mm', description: 'Height of the cone' }
    ],
    buildCodeFragment: (params) => `.cone(${params.radius1}, ${params.radius2}, ${params.height})`
  },
  {
    type: 'revolve',
    label: 'Revolve',
    description: 'Revolve the selected profile around an axis',
    parameters: [
      { name: 'angle', label: 'Angle', type: 'angle', defaultValue: 360, units: 'degrees', description: 'Angle to revolve through' }
    ],
    buildCodeFragment: (params) => `.revolve(${params.angle})`
  },
  {
    type: 'mirror',
    label: 'Mirror',
    description: 'Mirror the solid across a plane',
    parameters: [
      { name: 'plane', label: 'Mirror Plane', type: 'string', defaultValue: 'XY', description: 'Plane to mirror across (XY, XZ, YZ)' }
    ],
    buildCodeFragment: (params) => `.mirror('${params.plane}')`
  },
  {
    type: 'pattern_linear',
    label: 'Linear Pattern',
    description: 'Create a linear pattern of the selected feature',
    parameters: [
      { name: 'distance', label: 'Distance', type: 'float', defaultValue: 10, units: 'mm', description: 'Distance between copies' },
      { name: 'count', label: 'Count', type: 'integer', defaultValue: 3, description: 'Number of copies' },
      { name: 'direction', label: 'Direction', type: 'string', defaultValue: 'X', description: 'Direction (X, Y, or Z)' }
    ],
    buildCodeFragment: (params) => `.rarray(${params.distance}, 0, 0, ${params.count}, 1, 1)`
  }
];

const FeatureTreeSidebarContent: React.FC<FeatureTreeSidebarContentProps> = ({
  projectId,
  onNodeSelect,
  onParameterUpdate,
  onRegenerationSuccess
}) => {
  const [tree, setTree] = useState<FeatureTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [editingParameter, setEditingParameter] = useState<{nodeId: string, paramName: string} | null>(null);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [showAddFunctionForm, setShowAddFunctionForm] = useState(false);
  const [newFunctionType, setNewFunctionType] = useState<SupportedFeatureType>('fillet');
  const [newFunctionName, setNewFunctionName] = useState('');
  const [newFunctionParams, setNewFunctionParams] = useState<Record<string, string>>({});
  const [newFunctionParentId, setNewFunctionParentId] = useState<string | null>(null);
  const [isCreatingFunction, setIsCreatingFunction] = useState(false);
  const [paramValidationErrors, setParamValidationErrors] = useState<Record<string, string>>({});

  const getFeatureTemplate = (type: SupportedFeatureType): FeatureTemplate => {
    return FEATURE_TEMPLATES.find(template => template.type === type) ?? FEATURE_TEMPLATES[0];
  };

  const buildDefaultParamValues = (template: FeatureTemplate): Record<string, string> => {
    const defaults: Record<string, string> = {};
    template.parameters.forEach(param => {
      defaults[param.name] = String(param.defaultValue ?? '');
    });
    return defaults;
  };

  const canNodeAcceptChildren = (nodeId: string, childFeatureType: SupportedFeatureType): boolean => {
    if (!tree || !tree.nodes[nodeId]) return false;
    
    const node = tree.nodes[nodeId];
    const nodeType = node.feature_type.toLowerCase();
    
    // Check if this node is used in a union/boolean operation later
    const isUsedInBoolean = tree.regeneration_order.some(laterNodeId => {
      const laterNode = tree.nodes[laterNodeId];
      return laterNode && 
             ['union', 'difference', 'intersection'].includes(laterNode.feature_type.toLowerCase()) &&
             laterNode.parent_references?.some(ref => ref.feature_id === nodeId);
    });
    
    // Define what types of children each node can accept
    switch (childFeatureType) {
      case 'fillet':
      case 'chamfer':
        // Fillets and chamfers should be applied to final geometry, not intermediate steps
        if (isUsedInBoolean) {
          return false; // Don't allow fillets on geometry that will be used in boolean operations
        }
        // Only allow on solid geometry that is NOT part of boolean operations
        return ['box', 'cylinder', 'sphere', 'extrude', 'revolve', 'cone', 'union', 'difference'].includes(nodeType);
      
      case 'extrude':
      case 'revolve':
        // Extrude/revolve need sketch profiles or workplanes
        return ['sketch', 'workplane'].includes(nodeType);
      
      case 'box':
      case 'cylinder':
      case 'sphere':
      case 'cone':
        // Basic shapes need workplanes
        return ['workplane'].includes(nodeType);
      
      case 'mirror':
      case 'pattern_linear':
        // Patterns and mirrors work on any solid
        return ['box', 'cylinder', 'sphere', 'extrude', 'revolve', 'cone', 'fillet', 'chamfer', 'union', 'difference'].includes(nodeType);
      
      default:
        return true; // Allow for unknown types
    }
  };

  const getValidParentNodes = (): Array<{id: string, name: string}> => {
    if (!tree) return [];
    
    return tree.regeneration_order
      .filter(nodeId => canNodeAcceptChildren(nodeId, newFunctionType))
      .map(nodeId => ({
        id: nodeId,
        name: tree.nodes[nodeId]?.name || nodeId
      }));
  };

  const getDefaultParentId = (): string | null => {
    if (!tree) return null;
    
    const validParents = getValidParentNodes();
    
    // If selected node is valid, use it
    if (selectedNode && validParents.some(p => p.id === selectedNode)) {
      return selectedNode;
    }
    
    // Otherwise use the last valid parent in regeneration order
    if (validParents.length > 0) {
      return validParents[validParents.length - 1].id;
    }
    
    return null;
  };

  const resetNewFunctionForm = (type: SupportedFeatureType = newFunctionType, preserveParent = false) => {
    const template = getFeatureTemplate(type);
    setNewFunctionType(template.type);
    setNewFunctionName(template.label);
    setNewFunctionParams(buildDefaultParamValues(template));
    setParamValidationErrors({}); // Clear validation errors
    if (!preserveParent) {
      setNewFunctionParentId(getDefaultParentId());
    }
  };

  // Fetch feature tree from API
  useEffect(() => {
    loadFeatureTree();
  }, [projectId]);

  const loadFeatureTree = async () => {
    if (!projectId || typeof projectId !== 'string') {
      setError('Invalid project ID');
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const data = await fetchFeatureTree(projectId);
      if (data.success) {
        setTree(data.tree);
      } else {
        throw new Error(data.message || 'Failed to load feature tree');
      }
    } catch (err: any) {
      if (err?.response?.status === 404) {
        setError('No feature tree exists yet. Generate a design first.');
      } else if (err?.response?.status === 500) {
        setError('Server error loading feature tree.');
      } else {
        setError(err instanceof Error ? err.message : 'Unknown error loading feature tree');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!showAddFunctionForm || !tree) {
      return;
    }
    if (newFunctionParentId && tree.nodes[newFunctionParentId]) {
      return;
    }
    setNewFunctionParentId(getDefaultParentId());
  }, [showAddFunctionForm, tree, selectedNode]);

  const toggleAddFunctionForm = () => {
    const nextState = !showAddFunctionForm;
    setShowAddFunctionForm(nextState);
    if (nextState) {
      resetNewFunctionForm(newFunctionType);
      setIsCreatingFunction(false);
      setError(null);
    }
  };

  const handleFunctionTypeChange = (type: SupportedFeatureType) => {
    resetNewFunctionForm(type, true);
  };

  const validateParameterValue = (paramName: string, value: string, paramType: Parameter['type']): string | null => {
    if (!value.trim()) {
      return 'Value is required';
    }

    try {
      if (paramType === 'integer') {
        const parsed = parseInt(value, 10);
        if (Number.isNaN(parsed)) return 'Must be a valid integer';
        if (parsed < 0) return 'Must be positive';
        if (paramName === 'count' && parsed > 20) return 'Count too large (max 20)';
      } else if (paramType === 'float' || paramType === 'length' || paramType === 'angle') {
        const parsed = parseFloat(value);
        if (Number.isNaN(parsed)) return 'Must be a valid number';
        if (parsed <= 0 && (paramType === 'length' || paramType === 'angle')) {
          return `${paramType === 'length' ? 'Length' : 'Angle'} must be positive`;
        }
        
        // Geometric constraints based on feature type
        if (newFunctionType === 'fillet' && paramName === 'radius') {
          if (parsed > 2) return 'Fillet radius too large (max 2mm for most geometries)';
          if (parsed < 0.1) return 'Fillet radius too small (min 0.1mm)';
        }
        if (newFunctionType === 'chamfer' && paramName === 'distance') {
          if (parsed > 5) return 'Chamfer distance too large (max 5mm recommended)';
          if (parsed < 0.1) return 'Chamfer distance too small (min 0.1mm)';
        }
        if (['width', 'height', 'depth', 'radius'].includes(paramName)) {
          if (parsed > 100) return 'Dimension too large (max 100mm)';
          if (parsed < 0.1) return 'Dimension too small (min 0.1mm)';
        }
        if (paramName === 'angle' && paramType === 'angle') {
          if (parsed > 360) return 'Angle too large (max 360°)';
        }
      } else if (paramType === 'string') {
        if (paramName === 'plane' && !['XY', 'XZ', 'YZ'].includes(value.toUpperCase())) {
          return 'Plane must be XY, XZ, or YZ';
        }
        if (paramName === 'direction' && !['X', 'Y', 'Z'].includes(value.toUpperCase())) {
          return 'Direction must be X, Y, or Z';
        }
      }
      return null;
    } catch (error) {
      return 'Invalid value';
    }
  };

  const handleNewFunctionParamChange = (paramName: string, value: string) => {
    setNewFunctionParams(prev => ({
      ...prev,
      [paramName]: value
    }));

    // Real-time validation
    const template = getFeatureTemplate(newFunctionType);
    const param = template.parameters.find(p => p.name === paramName);
    if (param) {
      const error = validateParameterValue(paramName, value, param.type);
      setParamValidationErrors(prev => ({
        ...prev,
        [paramName]: error || ''
      }));
    }
  };

  const parseValueForParameterType = (value: string, type: Parameter['type']) => {
    if (type === 'integer') {
      const parsed = parseInt(value, 10);
      if (Number.isNaN(parsed)) {
        throw new Error('Enter a valid integer value');
      }
      if (parsed < 0) {
        throw new Error('Value must be positive');
      }
      return parsed;
    }
    if (type === 'float' || type === 'length' || type === 'angle') {
      const parsed = parseFloat(value);
      if (Number.isNaN(parsed)) {
        throw new Error('Enter a valid number');
      }
      if (parsed <= 0 && (type === 'length' || type === 'angle')) {
        throw new Error(`${type === 'length' ? 'Length' : 'Angle'} must be positive`);
      }
      // Special validation for fillet radius
      if (newFunctionType === 'fillet' && parsed > 2) {
        throw new Error('Fillet radius too large (max 2mm for most geometries)');
      }
      if (newFunctionType === 'chamfer' && parsed > 10) {
        throw new Error('Chamfer distance too large (max 10mm for most geometries)');
      }
      return parsed;
    }
    if (type === 'boolean') {
      return value === 'true' || value === '1';
    }
    if (type === 'string' && value.trim() === '') {
      throw new Error('String value cannot be empty');
    }
    return value;
  };

  const handleCreateFunction = async () => {
    if (!projectId || typeof projectId !== 'string') {
      setError('Invalid project ID');
      return;
    }
    if (!tree) {
      setError('Load a feature tree before adding features');
      return;
    }

    const template = getFeatureTemplate(newFunctionType);
    
    // Check for validation errors first
    const hasValidationErrors = Object.values(paramValidationErrors).some(error => error);
    if (hasValidationErrors) {
      setError('Please fix validation errors before proceeding');
      return;
    }

    // Validate all required parameters
    const missingParams: string[] = [];
    const validationErrors: string[] = [];
    
    template.parameters.forEach(param => {
      const value = (newFunctionParams[param.name] ?? '').toString().trim();
      if (!value) {
        missingParams.push(param.label);
        return;
      }
      
      const error = validateParameterValue(param.name, value, param.type);
      if (error) {
        validationErrors.push(`${param.label}: ${error}`);
      }
    });

    if (missingParams.length > 0) {
      setError(`Missing required parameters: ${missingParams.join(', ')}`);
      return;
    }

    if (validationErrors.length > 0) {
      setError(`Validation errors: ${validationErrors.join('; ')}`);
      return;
    }

    // Check parent selection
    if (!newFunctionParentId) {
      setError('Please select a parent node to attach this feature to');
      return;
    }

    const validParents = getValidParentNodes();
    if (!validParents.some(p => p.id === newFunctionParentId)) {
      setError(`Selected parent cannot accept ${template.label.toLowerCase()} features`);
      return;
    }

    const paramValues: Record<string, any> = {};

    try {
      template.parameters.forEach(param => {
        const raw = (newFunctionParams[param.name] ?? '').toString().trim();
        paramValues[param.name] = parseValueForParameterType(raw, param.type);
      });
    } catch (err: any) {
      setError(err?.message ?? 'Unable to parse parameter values');
      return;
    }

    const parametersPayload: Parameter[] = template.parameters.map(param => ({
      name: param.name,
      value: paramValues[param.name],
      type: param.type,
      units: param.units
    }));

    const codeFragment = template.buildCodeFragment(paramValues);

    setIsCreatingFunction(true);
    try {
      const response = await createFeatureTreeNode(projectId, {
        name: newFunctionName || template.label,
        feature_type: template.type,
        parameters: parametersPayload,
        parent_id: newFunctionParentId,
        code_fragment: codeFragment.startsWith('.') ? codeFragment : `.${codeFragment}`
      });

      if (!response.success) {
        throw new Error(response.message || 'Failed to add feature');
      }

      if (response.tree) {
        setTree(response.tree);
      } else {
        await loadFeatureTree();
      }

      if (response.node) {
        setExpandedNodes(prev => {
          const next = new Set(prev);
          if (newFunctionParentId) {
            next.add(newFunctionParentId);
          }
          next.add(response.node.id);
          return next;
        });
        setSelectedNode(response.node.id);
        onNodeSelect?.(response.node.id);
      }

      setShowAddFunctionForm(false);
      setError(null);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to add feature');
    } finally {
      setIsCreatingFunction(false);
    }
  };

  const selectedTemplate = getFeatureTemplate(newFunctionType);

  const toggleNode = (nodeId: string) => {
    const newExpanded = new Set(expandedNodes);
    if (newExpanded.has(nodeId)) {
      newExpanded.delete(nodeId);
    } else {
      newExpanded.add(nodeId);
    }
    setExpandedNodes(newExpanded);
  };

  const selectNode = (nodeId: string) => {
    setSelectedNode(nodeId);
    onNodeSelect?.(nodeId);
  };

  const updateParameter = async (nodeId: string, parameterName: string, value: any) => {
    if (!projectId || typeof projectId !== 'string') {
      setError('Invalid project ID');
      return;
    }

    try {
      const data = await updateFeatureTreeNode(projectId, nodeId, { [parameterName]: value });
      if (data.success) {
        if (data.tree) {
          setTree(data.tree);
        } else {
          loadFeatureTree();
        }
        onParameterUpdate?.(nodeId, parameterName, value);
      } else {
        throw new Error(data.message || 'Failed to update parameter');
      }
    } catch (err) {
      console.error('Failed to update parameter:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const handleRegenerate = async () => {
    if (!projectId || typeof projectId !== 'string') {
      setError('Invalid project ID');
      return;
    }

    try {
      setIsRegenerating(true);
      setError(null);
      
      const data = await regenerateCADModel(projectId);
      if (data.success) {
        // Reload tree to get updated state (dirty = false, new artifact ID)
        await loadFeatureTree();
        // Notify parent component that regeneration succeeded so it can refresh artifacts
        // This will trigger the frontend to poll for the new CAD version and update the 3D display
        onRegenerationSuccess?.();
      } else {
        throw new Error(data.message || 'Failed to regenerate 3D model');
      }
    } catch (err) {
      console.error('Failed to regenerate model:', err);
      setError(err instanceof Error ? err.message : 'Unknown error regenerating model');
    } finally {
      setIsRegenerating(false);
    }
  };

  // Function to get meaningful parameter names based on feature type
  const getParameterDisplayName = (param: Parameter, featureType: string): string => {
    // If it's already a meaningful name, use it
    if (!param.name.startsWith('arg_')) {
      return param.name;
    }

    // Map arg_ parameters to meaningful names based on feature type
    const featureTypeUpper = featureType.toUpperCase();
    const argIndex = param.name.replace('arg_', '');

    switch (featureTypeUpper) {
      case 'EXTRUDE':
        if (argIndex === '0') return 'Distance';
        break;
      case 'BOX':
        if (argIndex === '0') return 'Width';
        if (argIndex === '1') return 'Height'; 
        if (argIndex === '2') return 'Depth';
        break;
      case 'CYLINDER':
        if (argIndex === '0') return 'Radius';
        if (argIndex === '1') return 'Height';
        break;
      case 'SPHERE':
        if (argIndex === '0') return 'Radius';
        break;
      case 'FILLET':
        if (argIndex === '0') return 'Radius';
        break;
      case 'CHAMFER':
        if (argIndex === '0') return 'Distance';
        break;
      case 'REVOLVE':
        if (argIndex === '0') return 'Angle';
        break;
      default:
        // For unknown types, try to infer from parameter type
        if (param.type === 'angle') return 'Angle';
        if (param.type === 'length') return 'Distance';
        break;
    }

    // Fallback to original name with better formatting
    return param.name.replace('arg_', 'Param ');
  };

  const renderParameterWithLabel = (param: Parameter, nodeId: string, featureType: string) => {
    const displayName = getParameterDisplayName(param, featureType);
    const paramWithDisplayName = { ...param, name: displayName };
    
    return (
      <ParameterInput
        key={param.name}
        parameter={paramWithDisplayName}
        nodeId={nodeId}
        onParameterChange={(nodeId, paramName, value) => {
          // Use original parameter name for API calls, not display name
          updateParameter(nodeId, param.name, value);
        }}
        isEditing={editingParameter?.nodeId === nodeId && editingParameter?.paramName === param.name}
        onEditToggle={(nodeId, paramName) => {
          // Use original parameter name for editing state
          const newEditingParam = editingParameter?.nodeId === nodeId && editingParameter?.paramName === param.name
            ? null
            : { nodeId, paramName: param.name };
          setEditingParameter(newEditingParam);
        }}
      />
    );
  };


  const renderNode = (nodeId: string, level = 0): React.ReactNode => {
    const node = tree?.nodes[nodeId];
    if (!node) return null;

    const hasChildren = node.child_ids.length > 0;
    const isExpanded = expandedNodes.has(nodeId);
    const isSelected = selectedNode === nodeId;

    return (
      <div key={nodeId} className="select-none">
        <div
          className={`flex items-center py-1 px-2 hover:bg-gray-100 cursor-pointer ${
            isSelected ? 'bg-blue-100 border-l-2 border-blue-500' : ''
          } ${!node.is_valid ? 'bg-red-50' : ''}`}
          style={{ paddingLeft: `${level * 16 + 8}px` }}
          onClick={() => selectNode(nodeId)}
        >
          {hasChildren && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                toggleNode(nodeId);
              }}
              className="mr-1 p-0.5 rounded hover:bg-gray-200"
            >
              {isExpanded ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
            </button>
          )}
          
          {!hasChildren && <div className="w-4" />}
          
          <div className="flex items-center flex-1 min-w-0">
            <span
              className={`text-xs truncate ${
                !node.is_valid ? 'text-red-600' : 'text-gray-900'
              }`}
            >
              {node.name}
            </span>
            <span className="ml-1 text-xs text-gray-400 uppercase">
              {node.feature_type.replace('_', ' ')}
            </span>
            {!node.visible && (
              <span className="ml-1 text-xs text-gray-400">(hidden)</span>
            )}
          </div>
          
          {!node.is_valid && (
            <span className="text-red-500 text-xs" title={node.error_message}>
              ⚠
            </span>
          )}
        </div>

        {isSelected && node.parameters.length > 0 && (
          <div className="bg-gray-50 border-l-2 border-blue-200 ml-3 py-2">
            <div className="text-xs font-medium text-gray-600 mb-2 px-2">Parameters</div>
            {node.parameters
              .filter(param => {
                // Only show editable parameters
                // Filter out internal parameters that shouldn't be user-editable
                if (param.name === 'method') return false; // Internal method names
                if (param.name === 'operation') return false; // Internal operation types
                if (param.type === 'string' && typeof param.value === 'string' && param.value.includes('.')) return false; // Method calls
                
                // Show arg_ parameters and meaningful named parameters
                if (param.name.startsWith('arg_')) return true; // These are the main operation parameters
                if (['width', 'height', 'depth', 'radius', 'distance', 'angle', 'length', 'size'].includes(param.name.toLowerCase())) return true;
                if (['float', 'integer', 'length', 'angle'].includes(param.type)) return true; // Numeric parameters
                
                return false; // Hide everything else by default
              })
              .map(param => renderParameterWithLabel(param, nodeId, node.feature_type))}
          </div>
        )}

        {isExpanded && hasChildren && (
          <div>
            {node.child_ids.map(childId => renderNode(childId, level + 1))}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="p-3 text-center">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500 mx-auto"></div>
        <p className="mt-2 text-xs text-gray-600">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3 text-center">
        <p className="text-xs text-red-600 mb-2">{error}</p>
        <button
          onClick={loadFeatureTree}
          className="text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!tree) {
    return (
      <div className="p-3 text-center">
        <p className="text-xs text-gray-600">No feature tree available</p>
      </div>
    );
  }

  return (
    <div className="feature-tree h-full flex flex-col">
      {/* Project info */}
      <div className="border-b border-gray-200 p-2">
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-medium text-gray-900 truncate">{tree.name}</h4>
              {tree.dirty && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800">
                  Needs Regen
                </span>
              )}
              {tree.needs_full_regeneration && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                  Structural Change
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500">
              {Object.keys(tree.nodes).length} features • v{tree.version}
            </p>
          </div>
          <div className="flex items-center space-x-1 ml-2">
            {(tree.dirty || tree.needs_full_regeneration) && (
              <button 
                onClick={handleRegenerate}
                disabled={isRegenerating}
                className="p-1 rounded hover:bg-blue-100 text-blue-600 disabled:opacity-50 disabled:cursor-not-allowed" 
                title="Regenerate 3D Model"
              >
                <RefreshCw className={`w-3 h-3 ${isRegenerating ? 'animate-spin' : ''}`} />
              </button>
            )}
            <button
              onClick={toggleAddFunctionForm}
              className={`p-1 rounded ${showAddFunctionForm ? 'bg-blue-100 text-blue-600' : 'hover:bg-gray-100'}`}
              title="Add Feature"
            >
              <Plus className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>

      {/* Global Parameters */}
      {tree.global_parameters.length > 0 && (
        <div className="border-b border-gray-200 p-2">
          <h5 className="text-xs font-medium text-gray-700 mb-1">Global Parameters</h5>
          {tree.global_parameters.map(param => (
            <div key={param.name} className="text-xs text-gray-600 mb-1 truncate">
              {param.name}: {String(param.value)} {param.units}
            </div>
          ))}
        </div>
      )}

      {showAddFunctionForm && (
        <div className="border-b border-gray-200 p-3 bg-gray-50">
          <div className="flex items-center justify-between mb-2">
            <h5 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Add Feature</h5>
            {tree.needs_full_regeneration && (
              <span className="text-[10px] text-purple-600 bg-purple-100 px-2 py-0.5 rounded">
                Will require regeneration
              </span>
            )}
          </div>
          <div className="space-y-3">
            <div>
              <label className="block text-[11px] font-medium text-gray-600 mb-1">
                Feature Type
              </label>
              <select
                value={newFunctionType}
                onChange={(e) => handleFunctionTypeChange(e.target.value as SupportedFeatureType)}
                className="w-full text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                {FEATURE_TEMPLATES.map(template => (
                  <option key={template.type} value={template.type}>
                    {template.label}
                  </option>
                ))}
              </select>
              <p className="text-[10px] text-gray-500 mt-1">
                {selectedTemplate.description}
              </p>
            </div>

            <div>
              <label className="block text-[11px] font-medium text-gray-600 mb-1">
                Feature Name
              </label>
              <input
                value={newFunctionName}
                onChange={(e) => setNewFunctionName(e.target.value)}
                placeholder={`${selectedTemplate.label} Feature`}
                className="w-full text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-gray-600 mb-1">
                Attach To
                <span className="text-red-500 ml-1">*</span>
              </label>
              <select
                value={newFunctionParentId ?? ''}
                onChange={(e) => setNewFunctionParentId(e.target.value ? e.target.value : null)}
                className="w-full text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                required
              >
                <option value="">Select parent node...</option>
                {getValidParentNodes().map(parent => (
                  <option key={parent.id} value={parent.id}>
                    {parent.name} ({tree.nodes[parent.id]?.feature_type.toUpperCase()})
                  </option>
                ))}
              </select>
              <p className="text-[10px] text-gray-500 mt-1">
                Only showing nodes that can accept {selectedTemplate.label.toLowerCase()} features
              </p>
            </div>

            <div className="grid grid-cols-1 gap-2">
              {selectedTemplate.parameters.map(param => {
                const hasError = paramValidationErrors[param.name];
                return (
                  <div key={param.name}>
                    <label className="block text-[11px] font-medium text-gray-600 mb-1">
                      {param.label}
                      {param.units && <span className="text-gray-400"> ({param.units})</span>}
                      <span className="text-red-500 ml-1">*</span>
                    </label>
                    <input
                      type={param.type === 'string' ? 'text' : 'number'}
                      step={param.type === 'integer' ? 1 : 'any'}
                      min={param.type === 'length' || param.type === 'angle' ? 0.01 : undefined}
                      value={newFunctionParams[param.name] ?? ''}
                      onChange={(e) => handleNewFunctionParamChange(param.name, e.target.value)}
                      placeholder={`Enter ${param.label.toLowerCase()}...`}
                      className={`w-full text-xs border rounded px-2 py-1 focus:outline-none focus:ring-1 ${
                        hasError 
                          ? 'border-red-500 focus:ring-red-500 bg-red-50' 
                          : 'border-gray-300 focus:ring-blue-400'
                      }`}
                      required
                    />
                    {hasError && (
                      <p className="text-[10px] text-red-600 mt-1 font-medium">{hasError}</p>
                    )}
                    {!hasError && param.description && (
                      <p className="text-[10px] text-gray-500 mt-1">{param.description}</p>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => setShowAddFunctionForm(false)}
                className="px-3 py-1 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateFunction}
                disabled={isCreatingFunction || Object.values(paramValidationErrors).some(error => error) || !newFunctionParentId}
                className="px-3 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isCreatingFunction ? 'Adding…' : 'Add Feature'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Feature Tree */}
      <div className="flex-1 overflow-auto">
        {tree.regeneration_order.map(nodeId => {
          const node = tree.nodes[nodeId];
          // Only render root-level nodes
          const hasParentInTree = tree.regeneration_order.some(otherId => 
            otherId !== nodeId && tree.nodes[otherId]?.child_ids.includes(nodeId)
          );
          
          if (!hasParentInTree) {
            return renderNode(nodeId);
          }
          return null;
        })}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-200 p-2 text-xs text-gray-500">
        {tree.regeneration_order.length} operations
        {selectedNode && (
          <div className="truncate mt-1">
            Selected: {tree.nodes[selectedNode]?.name}
          </div>
        )}
      </div>
    </div>
  );
};

export default FeatureTreeSidebarContent;
