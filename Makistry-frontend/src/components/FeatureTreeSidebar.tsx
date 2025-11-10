import React from 'react';
import { ChevronLeft, ChevronRight, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import FeatureTreeSidebarContent from '@/components/FeatureTreeSidebarContent';

interface FeatureTreeSidebarProps {
  projectId: string | null;
  isVisible: boolean;
  onToggle: () => void;
  onRegenerationSuccess?: () => void;
}

export const FeatureTreeSidebar: React.FC<FeatureTreeSidebarProps> = ({
  projectId,
  isVisible,
  onToggle,
  onRegenerationSuccess,
}) => {
  return (
    <div className="relative h-full">
      {/* Sidebar */}
      <div
        className={`
          bg-white border-l border-gray-200 transition-all duration-300 ease-in-out
          ${isVisible ? 'w-80' : 'w-0'}
          flex flex-col h-full overflow-hidden shadow-lg
        `}
      >
        {isVisible && (
          <>
            {/* Sidebar Header */}
            <div className="flex items-center justify-between p-3 border-b border-gray-200 bg-gray-50">
              <div className="flex items-center space-x-2">
                <Settings className="w-4 h-4 text-gray-600" />
                <div>
                  <span className="font-medium text-gray-900">Design Steps</span>
                  <p className="text-xs text-gray-500">How your design was built</p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={onToggle}
                className="h-8 w-8 p-0 hover:bg-gray-200"
                title="Close Feature Tree"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>

            {/* Sidebar Content */}
            <div className="flex-1 overflow-hidden">
              {projectId ? (
                <FeatureTreeSidebarContent 
                  projectId={projectId} 
                  onRegenerationSuccess={onRegenerationSuccess}
                />
              ) : (
                <div className="p-4 text-center text-gray-600">
                  <Settings className="w-8 h-8 mx-auto mb-2 text-gray-400" />
                  <p className="text-sm">No project available</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Toggle Button (when sidebar is hidden) */}
      {!isVisible && (
        <div className="absolute top-4 right-4 z-10">
          <Button
            variant="outline"
            size="sm"
            onClick={onToggle}
            className="h-9 w-9 p-0 bg-white shadow-md hover:shadow-lg transition-shadow"
            title="Open Feature Tree"
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
};