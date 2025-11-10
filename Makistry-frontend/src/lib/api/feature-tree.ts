// src/lib/api/feature-tree.ts
import { api } from "@/lib/api";

// Backend model types (matching the Python models)
export interface Parameter {
  name: string;
  value: any;
  type: 'float' | 'integer' | 'string' | 'boolean' | 'vector3d' | 'point3d' | 'angle' | 'length';
  description?: string;
  units?: string;
  min_value?: number;
  max_value?: number;
}

export interface FeatureReference {
  feature_id: string;
  entity_type: string;
  entity_index?: number;
  selection_info?: any;
}

export interface FeatureNode {
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

export interface FeatureTree {
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
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface FeatureTreeResponse {
  success: boolean;
  tree: FeatureTree;
  message?: string;
}

// Fetch feature tree for a project
export async function fetchFeatureTree(projectId: string): Promise<FeatureTreeResponse> {
  const { data } = await api.get<FeatureTreeResponse>(`/feature-tree/${projectId}`);
  return data;
}

// Update a feature tree node parameters instantly (Command pattern)
export async function updateFeatureTreeNode(
  projectId: string, 
  nodeId: string, 
  parameterChanges: Record<string, any>
): Promise<{ 
  success: boolean; 
  message?: string; 
  tree?: FeatureTree; 
  node?: FeatureNode;
}> {
  const { data } = await api.patch<{ 
    success: boolean; 
    message?: string; 
    tree?: FeatureTree; 
    node?: FeatureNode;
  }>(
    `/feature-tree/${projectId}/nodes/${nodeId}`,
    { 
      parameter_changes: parameterChanges
    }
  );
  return data;
}

export interface FeatureTreeNodeResponse {
  success: boolean;
  node?: FeatureNode;
  tree?: FeatureTree;
  message?: string;
}

export interface CreateFeatureTreeNodePayload {
  name: string;
  feature_type: string;
  description?: string;
  parameters?: Parameter[];
  parent_references?: FeatureReference[];
  parent_id?: string | null;
  code_fragment?: string;
}

export async function createFeatureTreeNode(
  projectId: string,
  payload: CreateFeatureTreeNodePayload
): Promise<FeatureTreeNodeResponse> {
  const { data } = await api.post<FeatureTreeNodeResponse>(
    `/feature-tree/${projectId}/nodes`,
    payload
  );
  return data;
}

// Regenerate 3D CAD model from current parameters (Derivation pattern)
export async function regenerateCADModel(
  projectId: string
): Promise<{
  success: boolean;
  message?: string;
  artifact_id?: string;
  code_updated?: boolean;
}> {
  const { data } = await api.post<{
    success: boolean;
    message?: string;
    artifact_id?: string;
    code_updated?: boolean;
  }>(`/feature-tree/${projectId}/regenerate`);
  return data;
}
