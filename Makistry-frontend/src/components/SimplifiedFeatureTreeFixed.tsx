/**
 * Simplified Feature Tree Component with Categorized View
 * 
 * Groups technical CAD features into user-friendly categories:
 * - Foundation: Base sketches and primary shapes
 * - Modifications: Holes, cuts, additions  
 * - Finishing: Fillets, chamfers, appearance
 * - Patterns: Arrays, mirrors, repeats
 */
import React, { useState, useEffect } from 'react';
import { fetchFeatureTree, updateFeatureTreeNode } from '@/lib/api/feature-tree';
import { 
  ChevronRight, 
  ChevronDown, 
  Edit, 
  Building2,
  Wrench,
  Sparkles,
  Copy,
  Eye,
  EyeOff,
  Loader2,
  CheckCircle,
  AlertCircle
} from 'lucide-react';

// Types (reused from original component)
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
  dirty?: boolean;
  needs_full_regeneration?: boolean;
  last_good_artifact_id?: string;
}

interface SimplifiedFeatureTreeProps {
  projectId: string;
  onNodeSelect?: (nodeId: string) => void;
  onParameterUpdate?: (nodeId: string, parameterName: string, value: any) => void;
}

// Category definitions with icons and descriptions
const CATEGORIES = {
  foundation: {
    name: 'Foundation',
    icon: Building2,
    description: 'Base sketches and primary shapes',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200'
  },
  modifications: {
    name: 'Modifications', 
    icon: Wrench,
    description: 'Holes, cuts, and additions',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50', 
    borderColor: 'border-orange-200'
  },
  finishing: {
    name: 'Finishing',
    icon: Sparkles,
    description: 'Fillets, chamfers, and appearance',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200'
  },
  patterns: {
    name: 'Patterns',
    icon: Copy,
    description: 'Arrays, mirrors, and repeats',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200'
  }
};

// Parameter name mapping for user-friendly labels
const PARAMETER_NAME_MAP: Record<string, string> = {
  // Generic parameter mappings
  'arg_0': 'Distance',
  'arg_1': 'Width', 
  'arg_2': 'Height',
  'arg_3': 'Depth',
  'arg_4': 'Angle',
  'arg_5': 'Radius',
  'arg_6': 'Count',
  'arg_7': 'Offset',
  'arg_8': 'Scale',
  'arg_9': 'Rotation',
  
  // Common CAD parameters
  'distance': 'Distance',
  'length': 'Length',
  'width': 'Width',
  'height': 'Height',
  'depth': 'Depth',
  'radius': 'Radius',
  'diameter': 'Diameter',
  'angle': 'Angle',
  'rotation': 'Rotation',
  'scale': 'Scale Factor',
  'offset': 'Offset',
  'thickness': 'Thickness',
  'count': 'Count',
  'spacing': 'Spacing',
  
  // Extrude parameters
  'extrude_distance': 'Extrude Distance',
  'extrude_height': 'Height',
  'taper_angle': 'Taper Angle',
  'draft_angle': 'Draft Angle',
  
  // Revolve parameters
  'revolve_angle': 'Revolution Angle',
  'axis': 'Axis',
  'start_angle': 'Start Angle',
  'end_angle': 'End Angle',
  
  // Fillet/Chamfer parameters
  'fillet_radius': 'Fillet Radius',
  'chamfer_distance': 'Chamfer Distance',
  'chamfer_angle': 'Chamfer Angle',
  
  // Pattern parameters
  'pattern_count': 'Number of Copies',
  'pattern_spacing': 'Spacing',
  'linear_distance': 'Distance',
  'circular_angle': 'Angle Between',
  'array_count_x': 'Columns',
  'array_count_y': 'Rows',
  'array_spacing_x': 'Column Spacing',
  'array_spacing_y': 'Row Spacing',
  
  // Boolean parameters
  'union_type': 'Union Type',
  'subtract_type': 'Cut Type',
  'intersect_type': 'Intersection Type',
  
  // Sketch parameters
  'sketch_plane': 'Sketch Plane',
  'point_x': 'X Position',
  'point_y': 'Y Position',
  'point_z': 'Z Position',
  'center_x': 'Center X',
  'center_y': 'Center Y',
  'center_z': 'Center Z',
  
  // Shell parameters
  'shell_thickness': 'Wall Thickness',
  'shell_offset': 'Shell Offset',
  
  // Material/Appearance parameters
  'material': 'Material',
  'color': 'Color',
  'transparency': 'Transparency',
  'roughness': 'Surface Roughness',
  'metallic': 'Metallic',
  
  // Advanced parameters
  'tolerance': 'Tolerance',
  'precision': 'Precision',
  'smooth': 'Smooth',
  'keep_tools': 'Keep Tools',
  'merge_result': 'Merge Result'
};

// Feature-specific parameter mappings
const FEATURE_PARAMETER_MAP: Record<string, Record<string, string>> = {
  'extrude': {
    'arg_0': 'Height',
    'arg_1': 'Taper Angle',
    'arg_2': 'Draft Angle'
  },
  'revolve': {
    'arg_0': 'Angle',
    'arg_1': 'Axis Direction',
    'arg_2': 'Start Angle'
  },
  'fillet': {
    'arg_0': 'Radius',
    'arg_1': 'Edge Selection',
    'arg_2': 'Blend Type'
  },
  'chamfer': {
    'arg_0': 'Distance',
    'arg_1': 'Angle',
    'arg_2': 'Edge Selection'
  },
  'hole': {
    'arg_0': 'Diameter',
    'arg_1': 'Depth',
    'arg_2': 'Position X',
    'arg_3': 'Position Y'
  },
  'linear_pattern': {
    'arg_0': 'Count',
    'arg_1': 'Spacing',
    'arg_2': 'Direction',
    'arg_3': 'Second Count',
    'arg_4': 'Second Spacing'
  },
  'circular_pattern': {
    'arg_0': 'Count',
    'arg_1': 'Angle',
    'arg_2': 'Center Point',
    'arg_3': 'Axis'
  },
  'box': {
    'arg_0': 'Length',
    'arg_1': 'Width', 
    'arg_2': 'Height'
  },
  'cylinder': {
    'arg_0': 'Radius',
    'arg_1': 'Height',
    'arg_2': 'Center X',
    'arg_3': 'Center Y'
  },
  'sphere': {
    'arg_0': 'Radius',
    'arg_1': 'Center X',
    'arg_2': 'Center Y',
    'arg_3': 'Center Z'
  },
  'shell': {
    'arg_0': 'Thickness',
    'arg_1': 'Offset Direction',
    'arg_2': 'Remove Faces'
  },
  'mirror': {
    'arg_0': 'Mirror Plane',
    'arg_1': 'Keep Original',
    'arg_2': 'Merge Result'
  }
};

// Feature type to category mapping
const FEATURE_CATEGORY_MAP: Record<string, keyof typeof CATEGORIES> = {
  // Foundation features
  'sketch': 'foundation',
  'extrude': 'foundation',
  'revolve': 'foundation',
  'sweep': 'foundation',
  'loft': 'foundation',
  'box': 'foundation',
  'cylinder': 'foundation',
  'sphere': 'foundation',
  'cone': 'foundation',
  'torus': 'foundation',
  
  // Modification features
  'cut': 'modifications',
  'hole': 'modifications', 
  'boolean_subtract': 'modifications',
  'boolean_union': 'modifications',
  'boolean_intersect': 'modifications',
  'shell': 'modifications',
  'offset': 'modifications',
  'trim': 'modifications',
  'split': 'modifications',
  
  // Finishing features
  'fillet': 'finishing',
  'chamfer': 'finishing',
  'draft': 'finishing',
  'texture': 'finishing',
  'appearance': 'finishing',
  'material': 'finishing',
  'surface_finish': 'finishing',
  
  // Pattern features
  'linear_pattern': 'patterns',
  'circular_pattern': 'patterns',
  'mirror': 'patterns',
  'array': 'patterns',
  'pattern': 'patterns',
  'duplicate': 'patterns',
  'copy': 'patterns'
};

const SimplifiedFeatureTreeFixed: React.FC<SimplifiedFeatureTreeProps> = ({
  projectId,
  onNodeSelect,
  onParameterUpdate
}) => {
  const [tree, setTree] = useState<FeatureTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['foundation']));
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [editingParameter, setEditingParameter] = useState<{nodeId: string, paramName: string} | null>(null);
  const [updatingParameter, setUpdatingParameter] = useState<{nodeId: string, paramName: string} | null>(null);
  const [lastUpdateResult, setLastUpdateResult] = useState<{
    success: boolean;
    message: string;
    executionValid?: boolean;
  } | null>(null);

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

  const getCategoryForFeature = (featureType: string): keyof typeof CATEGORIES => {
    return FEATURE_CATEGORY_MAP[featureType.toLowerCase()] || 'modifications';
  };

  const getFriendlyParameterName = (paramName: string, featureType: string): string => {
    // First, try feature-specific mapping
    const featureMap = FEATURE_PARAMETER_MAP[featureType.toLowerCase()];
    if (featureMap && featureMap[paramName]) {
      return featureMap[paramName];
    }
    
    // Then try general parameter mapping
    if (PARAMETER_NAME_MAP[paramName]) {
      return PARAMETER_NAME_MAP[paramName];
    }
    
    // If no mapping found, make the parameter name more readable
    return paramName
      .replace(/arg_(\d+)/, 'Parameter $1')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase()); // Title case
  };

  const toggleCategory = (categoryKey: string) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(categoryKey)) {
      newExpanded.delete(categoryKey);
    } else {
      newExpanded.add(categoryKey);
    }
    setExpandedCategories(newExpanded);
  };

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

    // Set updating state
    setUpdatingParameter({ nodeId, paramName: parameterName });
    setLastUpdateResult(null);
    setError(null);

    try {
      const data = await updateFeatureTreeNode(projectId, nodeId, { [parameterName]: value }, {
        regenerateCode: true,
        validateExecution: true
      });
      
      if (data.success) {
        // Update the tree with the new data
        if (data.tree) {
          setTree(data.tree);
        } else {
          await loadFeatureTree();
        }
        
        // Set success result with execution status
        setLastUpdateResult({
          success: true,
          message: data.message || 'Parameter updated successfully',
          executionValid: data.execution_valid
        });
        
        // Call the callback
        onParameterUpdate?.(nodeId, parameterName, value);
        
        // Auto-clear success message after 3 seconds
        setTimeout(() => {
          setLastUpdateResult(null);
        }, 3000);
        
      } else {
        throw new Error(data.message || 'Failed to update parameter');
      }
    } catch (err: any) {
      console.error('Failed to update parameter:', err);
      
      // Extract detailed error message
      let errorMessage = 'Unknown error updating parameter';
      if (err?.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      
      setLastUpdateResult({
        success: false,
        message: errorMessage
      });
      
      // Auto-clear error message after 5 seconds
      setTimeout(() => {
        setLastUpdateResult(null);
      }, 5000);
    } finally {
      setUpdatingParameter(null);
    }
  };

  const renderParameter = (param: Parameter, nodeId: string) => {
    const node = tree?.nodes[nodeId];
    const featureType = node?.feature_type || '';
    const friendlyName = getFriendlyParameterName(param.name, featureType);
    const isEditing = editingParameter?.nodeId === nodeId && editingParameter?.paramName === param.name;
    const isUpdating = updatingParameter?.nodeId === nodeId && updatingParameter?.paramName === param.name;

    if (isEditing) {
      return (
        <div key={param.name} className="ml-3 mb-2">
          <label className="block text-xs font-medium text-gray-700 mb-1">
            {friendlyName} {param.units && `(${param.units})`}
            <span className="ml-2 font-normal text-gray-500">
              Current: <span className="font-mono text-gray-700">{String(param.value)}</span>
            </span>
          </label>
          <div className="relative">
            {param.type === 'boolean' ? (
              <select
                defaultValue={String(param.value)}
                className={`w-full px-2 py-1 border border-gray-300 rounded text-xs ${
                  isUpdating ? 'bg-gray-50' : ''
                }`}
                disabled={isUpdating}
                onBlur={(e) => {
                  const value = e.target.value === 'true';
                  updateParameter(nodeId, param.name, value);
                  setEditingParameter(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.currentTarget.blur();
                  }
                  if (e.key === 'Escape') {
                    setEditingParameter(null);
                  }
                }}
                autoFocus
              >
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : (
              <input
                type={param.type === 'integer' ? 'number' : param.type === 'float' ? 'number' : 'text'}
                step={param.type === 'float' ? 'any' : undefined}
                defaultValue={String(param.value)}
                placeholder={`Enter new value (current: ${String(param.value)})`}
                className={`w-full px-2 py-1 border border-gray-300 rounded text-xs ${
                  isUpdating ? 'bg-gray-50' : ''
                }`}
                disabled={isUpdating}
                onBlur={(e) => {
                  let value: any = e.target.value;
                  if (param.type === 'integer') value = parseInt(value);
                  if (param.type === 'float') value = parseFloat(value);
                  
                  updateParameter(nodeId, param.name, value);
                  setEditingParameter(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.currentTarget.blur();
                  }
                  if (e.key === 'Escape') {
                    setEditingParameter(null);
                  }
                }}
                onFocus={(e) => {
                  // Select all text when focusing for easier editing
                  e.target.select();
                }}
                autoFocus
              />
            )}
            {isUpdating && (
              <div className="absolute right-2 top-1/2 transform -translate-y-1/2">
                <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
              </div>
            )}
          </div>
        </div>
      );
    }

    return (
      <div
        key={param.name}
        className={`ml-3 mb-1 flex items-center justify-between cursor-pointer hover:bg-gray-50 p-1 rounded ${
          isUpdating ? 'bg-blue-50' : ''
        }`}
        onClick={() => !isUpdating && setEditingParameter({nodeId, paramName: param.name})}
        title={`Parameter: ${param.name}${param.description ? ` - ${param.description}` : ''}`}
      >
        <span className="text-xs text-gray-600 truncate">
          {friendlyName}: <span className="font-mono">{String(param.value)}</span>
          {param.units && <span className="text-gray-400"> {param.units}</span>}
        </span>
        <div className="flex items-center space-x-1">
          {isUpdating ? (
            <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
          ) : (
            <Edit className="w-3 h-3 text-gray-400 flex-shrink-0" />
          )}
        </div>
      </div>
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
          className={`flex items-center py-1.5 px-2 hover:bg-gray-100 cursor-pointer rounded ${
            isSelected ? 'bg-blue-100 border-l-2 border-blue-500' : ''
          } ${!node.is_valid ? 'bg-red-50' : ''}`}
          style={{ marginLeft: `${level * 12}px` }}
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
              className={`text-sm truncate font-medium ${
                !node.is_valid ? 'text-red-600' : 'text-gray-900'
              }`}
            >
              {node.name}
            </span>
            {!node.visible && (
              <EyeOff className="ml-2 w-3 h-3 text-gray-400" title="Hidden" />
            )}
          </div>
          
          {!node.is_valid && (
            <span className="text-red-500 text-xs ml-2" title={node.error_message}>
              ⚠
            </span>
          )}
        </div>

        {isSelected && node.parameters.length > 0 && (
          <div className="bg-gray-50 border-l-2 border-blue-200 ml-4 py-2 mt-1 rounded-r">
            <div className="text-xs font-medium text-gray-600 mb-2 px-2">Parameters</div>
            {node.parameters.map(param => renderParameter(param, nodeId))}
          </div>
        )}

        {isExpanded && hasChildren && (
          <div className="mt-1">
            {node.child_ids.map(childId => renderNode(childId, level + 1))}
          </div>
        )}
      </div>
    );
  };

  // Group features by category
  const groupedFeatures = React.useMemo(() => {
    if (!tree) return {};

    const groups: Record<string, string[]> = {
      foundation: [],
      modifications: [],
      finishing: [],
      patterns: []
    };

    // Group root-level features by category
    tree.regeneration_order.forEach(nodeId => {
      const node = tree.nodes[nodeId];
      if (!node) return;

      // Only include root-level nodes
      const hasParentInTree = tree.regeneration_order.some(otherId => 
        otherId !== nodeId && tree.nodes[otherId]?.child_ids.includes(nodeId)
      );
      
      if (!hasParentInTree) {
        const category = getCategoryForFeature(node.feature_type);
        groups[category].push(nodeId);
      }
    });

    return groups;
  }, [tree]);

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
    <div className="simplified-feature-tree h-full flex flex-col">
      {/* Header */}
      <div className="border-b border-gray-200 p-3">
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-medium text-gray-900 truncate">{tree.name}</h4>
            <p className="text-xs text-gray-500">
              {Object.keys(tree.nodes).length} features • v{tree.version}
            </p>
          </div>
        </div>
      </div>

      {/* Global Parameters */}
      {tree.global_parameters.length > 0 && (
        <div className="border-b border-gray-200 p-3">
          <h5 className="text-xs font-medium text-gray-700 mb-2">Global Parameters</h5>
          {tree.global_parameters.map(param => (
            <div key={param.name} className="text-xs text-gray-600 mb-1 truncate">
              {param.name}: {String(param.value)} {param.units}
            </div>
          ))}
        </div>
      )}

      {/* Update Status Feedback */}
      {lastUpdateResult && (
        <div className={`border-b border-gray-200 p-3 ${
          lastUpdateResult.success ? 'bg-green-50' : 'bg-red-50'
        }`}>
          <div className="flex items-center space-x-2">
            {lastUpdateResult.success ? (
              <CheckCircle className="w-4 h-4 text-green-600" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-600" />
            )}
            <div className="flex-1 min-w-0">
              <p className={`text-xs font-medium ${
                lastUpdateResult.success ? 'text-green-800' : 'text-red-800'
              }`}>
                {lastUpdateResult.message}
              </p>
              {lastUpdateResult.success && lastUpdateResult.executionValid !== undefined && (
                <p className={`text-xs ${
                  lastUpdateResult.executionValid ? 'text-green-600' : 'text-orange-600'
                }`}>
                  {lastUpdateResult.executionValid ? 
                    'Model executed successfully' : 
                    'Model validation pending'
                  }
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Categorized Features */}
      <div className="flex-1 overflow-auto">
        {Object.entries(CATEGORIES).map(([categoryKey, category]) => {
          const featuresInCategory = groupedFeatures[categoryKey] || [];
          if (featuresInCategory.length === 0) return null;

          const isExpanded = expandedCategories.has(categoryKey);
          const IconComponent = category.icon;

          return (
            <div key={categoryKey} className="mb-2">
              {/* Category Header */}
              <div
                className={`flex items-center justify-between p-2 cursor-pointer border rounded-lg mx-2 ${
                  category.bgColor
                } ${category.borderColor} hover:shadow-sm transition-shadow`}
                onClick={() => toggleCategory(categoryKey)}
              >
                <div className="flex items-center space-x-2">
                  <IconComponent className={`w-4 h-4 ${category.color}`} />
                  <div>
                    <span className={`text-sm font-medium ${category.color}`}>
                      {category.name}
                    </span>
                    <p className="text-xs text-gray-500">{category.description}</p>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-xs text-gray-500 bg-white px-2 py-1 rounded">
                    {featuresInCategory.length}
                  </span>
                  {isExpanded ? (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  )}
                </div>
              </div>

              {/* Category Content */}
              {isExpanded && (
                <div className="mt-2 mx-2">
                  {featuresInCategory.map(nodeId => renderNode(nodeId))}
                </div>
              )}
            </div>
          );
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

export default SimplifiedFeatureTreeFixed;
