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
  EyeOff
} from 'lucide-react';

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
} as const;

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

const SimplifiedFeatureTree: React.FC<SimplifiedFeatureTreeProps> = ({
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

  const renderParameter = (param: Parameter, nodeId: string) => {
    const isEditing = editingParameter?.nodeId === nodeId && editingParameter?.paramName === param.name;

    if (isEditing) {
      return (
        <div key={param.name} className="ml-3 mb-2">
          <label className="block text-xs font-medium text-gray-700 mb-1">
            {param.name} {param.units && `(${param.units})`}
          </label>
          <input
            type={param.type === 'integer' ? 'number' : param.type === 'float' ? 'number' : 'text'}
            step={param.type === 'float' ? 'any' : undefined}
            defaultValue={param.value}
            className="w-full px-2 py-1 border border-gray-300 rounded text-xs"
            onBlur={(e) => {
              let value = e.target.value;
              if (param.type === 'integer') value = parseInt(value);
              if (param.type === 'float') value = parseFloat(value);
              if (param.type === 'boolean') value = value === 'true';
              
              updateParameter(nodeId, param.name, value);
              setEditingParameter(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.currentTarget.blur();
              }
            }}
            autoFocus
          />
        </div>
      );
    }

    return (
      <div
        key={param.name}
        className="ml-3 mb-1 flex items-center justify-between cursor-pointer hover:bg-gray-50 p-1 rounded"
        onClick={() => setEditingParameter({nodeId, paramName: param.name})}
      >
        <span className="text-xs text-gray-600 truncate">
          {param.name}: <span className="font-mono">{String(param.value)}</span>
          {param.units && <span className="text-gray-400"> {param.units}</span>}
        </span>
        <Edit className="w-3 h-3 text-gray-400 flex-shrink-0" />
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

export default SimplifiedFeatureTree;
