import React from 'react';

// Section 2.3 — every module page = PageHeader (title, description, primary action) + content.
export function PageHeader({
  title,
  description,
  action,
  badges,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  badges?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-title font-semibold text-text-hi">{title}</h1>
          {badges}
        </div>
        {description && <p className="mt-1 max-w-3xl text-[13px] text-text-mid">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
