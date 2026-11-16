import type { ComponentType, ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { Popover } from './Popover';

export type MenuEntry =
  | { kind: 'link'; label: string; to: string; icon?: ComponentType<{ className?: string }> }
  | {
      kind: 'action';
      label: string;
      onSelect: () => void;
      icon?: ComponentType<{ className?: string }>;
    }
  | { kind: 'divider' };

interface MenuProps {
  trigger: Parameters<typeof Popover>[0]['trigger'];
  items: readonly MenuEntry[];
  header?: ReactNode;
  width?: number;
  label: string;
}

const ITEM =
  'flex w-full items-center gap-2.5 rounded-[6px] px-2 py-[7px] text-left text-[13px] text-fg-2 hover:bg-sunk hover:text-fg focus-visible:bg-sunk';

export function Menu({ trigger, items, header, width = 240, label }: MenuProps) {
  return (
    <Popover trigger={trigger} width={width} role="menu" label={label}>
      {(close) => (
        <>
          {header}
          <div className="grid p-1.5">
            {items.map((it, i) => {
              if (it.kind === 'divider') return <hr key={i} className="my-1.5 border-line" />;
              const Icon = it.icon;
              const body = (
                <>
                  {Icon && <Icon className="h-4 w-4 flex-none" />}
                  {it.label}
                </>
              );
              return it.kind === 'link' ? (
                <Link key={it.label} role="menuitem" to={it.to} onClick={close} className={ITEM}>
                  {body}
                </Link>
              ) : (
                <button
                  key={it.label}
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    close();
                    it.onSelect();
                  }}
                  className={ITEM}
                >
                  {body}
                </button>
              );
            })}
          </div>
        </>
      )}
    </Popover>
  );
}
