/**
 * Enhanced Parameter Input Component
 * Applies CADAM insights for better parameter editing experience
 */
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { ChevronUp, ChevronDown, Edit } from 'lucide-react';
import styles from './ParameterInput.module.css';

interface Parameter {
  name: string;
  value: any;
  type: 'float' | 'integer' | 'string' | 'boolean' | 'vector3d' | 'point3d' | 'angle' | 'length';
  description?: string;
  units?: string;
  min_value?: number;
  max_value?: number;
}

interface ParameterInputProps {
  parameter: Parameter;
  nodeId: string;
  onParameterChange: (nodeId: string, paramName: string, value: any) => void;
  isEditing: boolean;
  onEditToggle: (nodeId: string, paramName: string) => void;
}

export const ParameterInput: React.FC<ParameterInputProps> = ({
  parameter,
  nodeId,
  onParameterChange,
  isEditing,
  onEditToggle
}) => {
  const [localValue, setLocalValue] = useState(parameter.value);
  const [validationError, setValidationError] = useState<string | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync local value with parameter value when it changes externally
  useEffect(() => {
    setLocalValue(parameter.value);
  }, [parameter.value]);

  // Debounced parameter update (200ms like CADAM)
  const debouncedUpdate = useCallback(
    (value: any) => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      debounceTimerRef.current = setTimeout(() => {
        onParameterChange(nodeId, parameter.name, value);
      }, 200);
    },
    [nodeId, parameter.name, onParameterChange]
  );

  // Cleanup debounce timer
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const validateValue = (value: any): { isValid: boolean; error?: string; parsedValue?: any } => {
    try {
      let parsedValue = value;
      
      if (parameter.type === 'integer') {
        parsedValue = parseInt(value, 10);
        if (isNaN(parsedValue)) {
          return { isValid: false, error: 'Must be a valid integer' };
        }
      } else if (parameter.type === 'float' || parameter.type === 'length' || parameter.type === 'angle') {
        parsedValue = parseFloat(value);
        if (isNaN(parsedValue)) {
          return { isValid: false, error: 'Must be a valid number' };
        }
      } else if (parameter.type === 'boolean') {
        parsedValue = value === 'true' || value === true;
      }

      // Check min/max constraints
      if (typeof parsedValue === 'number' && parameter.min_value !== undefined && parsedValue < parameter.min_value) {
        return { isValid: false, error: `Must be at least ${parameter.min_value}` };
      }
      if (typeof parsedValue === 'number' && parameter.max_value !== undefined && parsedValue > parameter.max_value) {
        return { isValid: false, error: `Must be at most ${parameter.max_value}` };
      }

      return { isValid: true, parsedValue };
    } catch (error) {
      return { isValid: false, error: 'Invalid value' };
    }
  };

  const handleInputChange = (value: string) => {
    setLocalValue(value);
    
    const validation = validateValue(value);
    if (validation.isValid) {
      setValidationError(null);
      debouncedUpdate(validation.parsedValue);
    } else {
      setValidationError(validation.error || 'Invalid value');
    }
  };

  const handleSliderChange = (value: number) => {
    setLocalValue(value);
    setValidationError(null);
    debouncedUpdate(value);
  };

  // Calculate slider range for numeric parameters
  const getSliderRange = () => {
    const isNumeric = parameter.type === 'float' || parameter.type === 'integer' || 
                     parameter.type === 'length' || parameter.type === 'angle';
    
    if (!isNumeric) return null;

    const currentValue = typeof parameter.value === 'number' ? parameter.value : 0;
    
    // Use explicit bounds if provided, otherwise create reasonable defaults
    let minValue: number;
    let maxValue: number;
    
    if (parameter.min_value !== undefined && parameter.max_value !== undefined) {
      minValue = parameter.min_value;
      maxValue = parameter.max_value;
    } else if (parameter.type === 'length') {
      // For lengths, always start from 0.1 and go up to reasonable maximum
      minValue = 0.1;
      maxValue = Math.max(currentValue * 3, 100);
    } else if (parameter.type === 'angle') {
      // For angles, common range is 0-360 degrees
      minValue = 0;
      maxValue = 360;
    } else {
      // For other numeric types, create range around current value
      minValue = parameter.min_value ?? Math.min(0, currentValue * 0.1);
      maxValue = parameter.max_value ?? Math.max(currentValue * 2, currentValue + 100);
    }
    
    return { min: minValue, max: maxValue, step: parameter.type === 'integer' ? 1 : 0.1 };
  };

  const sliderRange = getSliderRange();
  const canUseSlider = sliderRange && (
    parameter.type === 'length' || 
    parameter.type === 'angle' || 
    parameter.max_value !== undefined || 
    parameter.min_value !== undefined
  );

  if (isEditing) {
    return (
      <div className="ml-3 mb-3 p-2 bg-gray-50 rounded border">
        <label className="block text-xs font-medium text-gray-700 mb-1">
          {parameter.name}
          {parameter.units && <span className="text-gray-500"> ({parameter.units})</span>}
          {parameter.description && <span className="text-gray-500 italic"> - {parameter.description}</span>}
        </label>
        
        {parameter.type === 'boolean' ? (
          <select
            value={localValue.toString()}
            onChange={(e) => handleInputChange(e.target.value)}
            className="w-full px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-blue-500"
          >
            <option value="true">True</option>
            <option value="false">False</option>
          </select>
        ) : canUseSlider ? (
          <div className="space-y-2">
            <input
              ref={inputRef}
              type="range"
              min={sliderRange.min}
              max={sliderRange.max}
              step={sliderRange.step}
              value={typeof localValue === 'number' ? localValue : 0}
              onChange={(e) => handleSliderChange(parseFloat(e.target.value))}
              className={`w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer ${styles.slider}`}
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>{sliderRange.min}</span>
              <span className="font-mono font-medium text-gray-900">{localValue}</span>
              <span>{sliderRange.max}</span>
            </div>
            <input
              type="number"
              value={localValue}
              onChange={(e) => handleInputChange(e.target.value)}
              step={sliderRange.step}
              className="w-full px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-blue-500"
              placeholder="Enter value..."
            />
          </div>
        ) : (
          <input
            ref={inputRef}
            type={parameter.type === 'integer' || parameter.type === 'float' || 
                  parameter.type === 'length' || parameter.type === 'angle' ? 'number' : 'text'}
            step={parameter.type === 'float' || parameter.type === 'length' || parameter.type === 'angle' ? 'any' : undefined}
            value={localValue}
            onChange={(e) => handleInputChange(e.target.value)}
            className={`w-full px-2 py-1 border rounded text-xs focus:ring-2 ${
              validationError ? 'border-red-500 focus:ring-red-500' : 'border-gray-300 focus:ring-blue-500'
            }`}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                onEditToggle(nodeId, parameter.name);
              }
              if (e.key === 'Escape') {
                setLocalValue(parameter.value);
                setValidationError(null);
                onEditToggle(nodeId, parameter.name);
              }
            }}
            autoFocus
          />
        )}
        
        {validationError && (
          <p className="mt-1 text-xs text-red-600">{validationError}</p>
        )}
        
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => onEditToggle(nodeId, parameter.name)}
            className="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 focus:ring-2 focus:ring-blue-500"
          >
            Done
          </button>
          <button
            onClick={() => {
              setLocalValue(parameter.value);
              setValidationError(null);
              onEditToggle(nodeId, parameter.name);
            }}
            className="px-2 py-1 text-xs bg-gray-500 text-white rounded hover:bg-gray-600"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="ml-3 mb-1 flex items-center justify-between cursor-pointer hover:bg-gray-50 p-1 rounded group"
      onClick={() => onEditToggle(nodeId, parameter.name)}
    >
      <span className="text-xs text-gray-600 truncate">
        {parameter.name}: <span className="font-mono font-medium">{String(parameter.value)}</span>
        {parameter.units && <span className="text-gray-400"> {parameter.units}</span>}
      </span>
      <Edit className="w-3 h-3 text-gray-400 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
    </div>
  );
};