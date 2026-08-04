import React from 'react';
import { cn } from '@/utils/cn';

type Variant = 'primary' | 'new' | 'ghost' | 'danger' | 'subtle' | 'outline';
type Size = 'tiny' | 'sm' | 'md';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: React.ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:brightness-110 border border-transparent',
  new: 'bg-accent-new text-white hover:brightness-110 border border-transparent font-semibold',
  ghost: 'bg-transparent text-text-mid hover:bg-raised hover:text-text-hi border border-transparent',
  outline: 'bg-transparent text-text-hi hover:bg-raised border border-border-strong',
  subtle: 'bg-raised text-text-hi hover:brightness-125 border border-border',
  danger: 'bg-err text-white hover:brightness-110 border border-transparent',
};

const SIZES: Record<Size, string> = {
  tiny: 'h-6 px-2 text-[11px] gap-1 rounded',
  sm: 'h-8 px-3 text-[13px] gap-1.5 rounded-control',
  md: 'h-9 px-4 text-[13px] gap-2 rounded-control',
};

export function Button({
  variant = 'subtle',
  size = 'sm',
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center font-medium transition select-none focus-ring',
        VARIANTS[variant],
        SIZES[size],
        disabled && 'opacity-45 cursor-not-allowed pointer-events-none',
        className,
      )}
      disabled={disabled}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
}
