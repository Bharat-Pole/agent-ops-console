import React from 'react';
import { cn } from '@/utils/cn';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  raised?: boolean;
  pad?: boolean;
}

export function Card({ raised, pad = true, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-card border border-border',
        raised ? 'bg-raised' : 'bg-surface',
        pad && 'p-4',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex items-start justify-between gap-3 mb-3', className)}>
      <div>
        <div className="text-[13px] font-semibold text-text-hi">{title}</div>
        {subtitle && <div className="text-xs text-text-low mt-0.5">{subtitle}</div>}
      </div>
      {action}
    </div>
  );
}
