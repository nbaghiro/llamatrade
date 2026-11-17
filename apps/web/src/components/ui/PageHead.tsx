import { ChevronRight } from 'lucide-react';
import { Fragment, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { useDocumentTitle } from '../../hooks/useDocumentTitle';

export interface Crumb {
  label: ReactNode;
  to?: string;
}

interface PageHeadProps {
  title: ReactNode;
  /** The browser tab title, when `title` is not plain text. */
  documentTitle?: string;
  /** The line under the title. */
  sub?: ReactNode;
  crumbs?: readonly Crumb[];
  /** Badges and state beside the title, e.g. a Paper badge and "Running". */
  badges?: ReactNode;
  /** The account scope, beside what it filters (mode2 A). */
  scope?: ReactNode;
  /** Buttons at the right; the main one is `.btn-primary`. */
  actions?: ReactNode;
  /** An amber line under the title when something needs the person. */
  attention?: ReactNode;
  className?: string;
}

/** The top of every page: crumbs, title with badges, a line under it, then scope and actions. */
export function PageHead({
  title,
  documentTitle,
  sub,
  crumbs,
  badges,
  scope,
  actions,
  attention,
  className = '',
}: PageHeadProps) {
  useDocumentTitle(documentTitle ?? (typeof title === 'string' ? title : undefined));
  return (
    <header
      className={`mb-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between ${className}`}
    >
      <div className="min-w-0">
        {crumbs && crumbs.length > 0 && (
          <nav
            aria-label="Breadcrumb"
            className="mb-1.5 flex items-center gap-1.5 text-[12.5px] text-fg-3"
          >
            {crumbs.map((c, i) => (
              <Fragment key={i}>
                {i > 0 && <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />}
                {c.to ? (
                  <Link to={c.to} className="hover:text-fg">
                    {c.label}
                  </Link>
                ) : (
                  <span className="text-fg-2">{c.label}</span>
                )}
              </Fragment>
            ))}
          </nav>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="m-0 text-[26px] font-semibold leading-tight tracking-[-0.03em] text-fg md:text-[28px]">
            {title}
          </h1>
          {badges}
        </div>
        {sub && <div className="mt-1 text-[13px] text-fg-2">{sub}</div>}
        {attention && <div className="mt-1.5">{attention}</div>}
      </div>
      {(scope || actions) && (
        <div className="flex flex-wrap items-center gap-2 md:flex-none md:justify-end">
          {scope}
          {actions}
        </div>
      )}
    </header>
  );
}
