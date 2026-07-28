import React from 'react';
import { Inbox } from 'lucide-react';

// Section 14 #15 — empty states everywhere data can be empty, with a CTA.
export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  message?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-border bg-surface/50 px-6 py-14 text-center">
      <div className="mb-3 text-text-low">{icon ?? <Inbox size={28} />}</div>
      <div className="text-[14px] font-semibold text-text-hi">{title}</div>
      {message && <div className="mt-1 max-w-md text-[13px] text-text-mid">{message}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
