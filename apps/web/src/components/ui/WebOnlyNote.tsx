import { Info } from 'lucide-react';

/** On a phone, strategies and backtests are read-only (phone-nav2 D); this says where to edit. */
export function WebOnlyNote({
  what = 'Editing strategies',
  className = '',
}: {
  what?: string;
  className?: string;
}) {
  return (
    <div
      className={`flex items-start gap-2.5 rounded-[10px] border border-line bg-sunk px-3.5 py-3 text-[13px] text-fg-2 md:hidden ${className}`}
    >
      <Info aria-hidden="true" className="mt-0.5 h-4 w-4 flex-none text-fg-3" />
      <span>{what} is on the web, on a wider screen.</span>
    </div>
  );
}
