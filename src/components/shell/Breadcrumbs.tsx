import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="mb-3 flex items-center gap-1 text-[12px] text-text-low">
      {items.map((c, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight size={12} />}
          {c.to ? (
            <Link to={c.to} className="hover:text-text-mid">
              {c.label}
            </Link>
          ) : (
            <span className="text-text-mid">{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
