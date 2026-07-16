import { ChevronDown } from 'lucide-react';
import { forwardRef } from 'react';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  options: SelectOption[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ options, placeholder, className = '', ...props }, ref) => {
    return (
      <div className="relative">
        <select
          ref={ref}
          className={`w-full px-3 py-2 pr-10 text-sm appearance-none border-2 border-ink bg-paper text-ink focus:border-orange-500 outline-none cursor-pointer ${className}`}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/50 pointer-events-none" />
      </div>
    );
  }
);

Select.displayName = 'Select';
