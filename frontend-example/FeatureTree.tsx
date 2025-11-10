/**
 * Feature Tree Component for Makistry CAD System
 * 
 * This component displays the parametric feature tree for a CAD model,
 * allowing users to view and edit the modeling history.
 */
import React, { useState, useEffect } from 'react';
import { ChevronRight, ChevronDown, Edit, Trash2, Plus, Settings } from 'lucide-react';

// Types from the backend
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
}

interface FeatureTreeProps {
  projectId: string;
  onNodeSelect?: (nodeId: string) => void;
  onParameterUpdate?: (nodeId: string, parameterName: string, value: any) => void;
}

const FeatureTreeComponent: React.FC<FeatureTreeProps> = ({
  projectId,
  onNodeSelect,
  onParameterUpdate
}) => {
  const [tree, setTree] = useState<FeatureTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [editingParameter, setEditingParameter] = useState<{nodeId: string, paramName: string} | null>(null);

  // Fetch feature tree from API
  useEffect(() => {
    fetchFeatureTree();
  }, [projectId]);

  const fetchFeatureTree = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/feature-tree/${projectId}`);
      if (!response.ok) {
        throw new Error('Failed to fetch feature tree');
      }
      const data = await response.json();
      if (data.success) {
        setTree(data.tree);
      } else {
        throw new Error(data.message || 'Failed to load feature tree');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
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
    try {
      const response = await fetch(`/api/feature-tree/${projectId}/nodes/${nodeId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          parameter_changes: { [parameterName]: value }
        })
      });

      if (!response.ok) {
        throw new Error('Failed to update parameter');
      }

      const data = await response.json();
      if (data.success) {
        setTree(data.tree);
        onParameterUpdate?.(nodeId, parameterName, value);
      }
    } catch (err) {
      console.error('Failed to update parameter:', err);
    }
  };

  const renderParameter = (param: Parameter, nodeId: string) => {
    const isEditing = editingParameter?.nodeId === nodeId && editingParameter?.paramName === param.name;

    if (isEditing) {
      return (
        <div key={param.name} className="ml-4 mb-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {param.name} {param.units && `(${param.units})`}
          </label>
          <input
            type={param.type === 'integer' ? 'number' : param.type === 'float' ? 'number' : 'text'}
            step={param.type === 'float' ? 'any' : undefined}
            defaultValue={param.value}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
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
        className="ml-4 mb-1 flex items-center justify-between cursor-pointer hover:bg-gray-50 p-1 rounded"
        onClick={() => setEditingParameter({nodeId, paramName: param.name})}
      >
        <span className="text-sm text-gray-600">
          {param.name}: <span className="font-mono">{String(param.value)}</span>
          {param.units && <span className="text-gray-400"> {param.units}</span>}
        </span>
        <Edit className="w-3 h-3 text-gray-400" />
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
          className={`flex items-center py-1 px-2 hover:bg-gray-100 cursor-pointer ${
            isSelected ? 'bg-blue-100 border-l-2 border-blue-500' : ''
          } ${!node.is_valid ? 'bg-red-50' : ''}`}
          style={{ paddingLeft: `${level * 20 + 8}px` }}
          onClick={() => selectNode(nodeId)}
        >
          {hasChildren && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                toggleNode(nodeId);
              }}
              className="mr-1 p-1 rounded hover:bg-gray-200"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </button>
          )}
          
          {!hasChildren && <div className="w-6" />}
          
          <div className="flex items-center flex-1 min-w-0">
            <span
              className={`text-sm truncate ${
                !node.is_valid ? 'text-red-600' : 'text-gray-900'
              }`}
            >
              {node.name}
            </span>
            <span className="ml-2 text-xs text-gray-500 uppercase">
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
          <div className="bg-gray-50 border-l-2 border-blue-200 ml-4 py-2">
            <div className="text-xs font-medium text-gray-600 mb-2 px-2">Parameters</div>
            {node.parameters.map(param => renderParameter(param, nodeId))}
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
      <div className="p-4 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
        <p className="mt-2 text-gray-600">Loading feature tree...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center">
        <p className="text-red-600">Error: {error}</p>
        <button
          onClick={fetchFeatureTree}
          className="mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!tree) {
    return (
      <div className="p-4 text-center">
        <p className="text-gray-600">No feature tree available</p>
      </div>
    );
  }

  return (
    <div className="feature-tree h-full flex flex-col">
      {/* Header */}
      <div className="border-b border-gray-200 p-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium text-gray-900">{tree.name}</h3>
          <div className="flex items-center space-x-2">
            <button className="p-1 rounded hover:bg-gray-100" title="Add Feature">
              <Plus className="w-4 h-4" />
            </button>
            <button className="p-1 rounded hover:bg-gray-100" title="Settings">
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>
        <p className="text-sm text-gray-500">
          {Object.keys(tree.nodes).length} features • Version {tree.version}
        </p>
      </div>

      {/* Global Parameters */}
      {tree.global_parameters.length > 0 && (
        <div className="border-b border-gray-200 p-3">
          <h4 className="text-sm font-medium text-gray-700 mb-2">Global Parameters</h4>
          {tree.global_parameters.map(param => (
            <div key={param.name} className="text-sm text-gray-600 mb-1">
              {param.name}: {String(param.value)} {param.units}
            </div>
          ))}
        </div>
      )}

      {/* Feature Tree */}
      <div className="flex-1 overflow-auto">
        {tree.regeneration_order.map(nodeId => {
          const node = tree.nodes[nodeId];
          // Only render root-level nodes (those without parents in the current tree)
          const hasParentInTree = tree.regeneration_order.some(otherId => 
            otherId !== nodeId && tree.nodes[otherId]?.child_ids.includes(nodeId)
          );
          
          if (!hasParentInTree) {
            return renderNode(nodeId);
          }
          return null;
        })}
      </div>

      {/* Footer with regeneration info */}
      <div className="border-t border-gray-200 p-2 text-xs text-gray-500">
        Regeneration order: {tree.regeneration_order.length} operations
        {selectedNode && (
          <span className="ml-2">
            • Selected: {tree.nodes[selectedNode]?.name}
          </span>
        )}
      </div>
    </div>
  );
};

export default FeatureTreeComponent;