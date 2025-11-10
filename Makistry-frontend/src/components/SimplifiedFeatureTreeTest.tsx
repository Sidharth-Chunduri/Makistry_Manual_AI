import React from 'react';
import { Building2, Wrench, Sparkles, Copy } from 'lucide-react';

interface TestProps {
  projectId: string;
}

const SimplifiedFeatureTreeTest: React.FC<TestProps> = ({ projectId }) => {
  return (
    <div className="p-4">
      <h3 className="text-lg font-medium mb-4">Test Simplified Feature Tree</h3>
      <div className="space-y-2">
        <div className="flex items-center space-x-2 p-2 bg-blue-50 rounded">
          <Building2 className="w-4 h-4 text-blue-600" />
          <span>Foundation</span>
        </div>
        <div className="flex items-center space-x-2 p-2 bg-orange-50 rounded">
          <Wrench className="w-4 h-4 text-orange-600" />
          <span>Modifications</span>
        </div>
        <div className="flex items-center space-x-2 p-2 bg-purple-50 rounded">
          <Sparkles className="w-4 h-4 text-purple-600" />
          <span>Finishing</span>
        </div>
        <div className="flex items-center space-x-2 p-2 bg-green-50 rounded">
          <Copy className="w-4 h-4 text-green-600" />
          <span>Patterns</span>
        </div>
      </div>
      <p className="text-sm text-gray-500 mt-4">Project ID: {projectId}</p>
    </div>
  );
};

export default SimplifiedFeatureTreeTest;