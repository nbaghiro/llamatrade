import { Info, Moon, Sun } from 'lucide-react';
import { useState } from 'react';

import { AppearancePicker } from '../../../components/settings/AppearancePicker';
import { AppearancePreview } from '../../../components/settings/AppearancePreview';
import { accentLabel } from '../../../components/settings/previewTheme';
import { useSessionRows } from '../../../components/shell/useSessionRows';
import { Segmented } from '../../../components/ui';
import { useResolvedTheme, useThemeStore } from '../../../store/theme';
import type { ThemeMode } from '../../../theme/accents';

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Controls on the left, a small Home in the chosen surface and accent on the right. */
export function AppearanceSection() {
  const resolved = useResolvedTheme();
  const darkSurface = useThemeStore((s) => s.darkSurface);
  const lightSurface = useThemeStore((s) => s.lightSurface);
  const darkAccent = useThemeStore((s) => s.darkAccent);
  const lightAccent = useThemeStore((s) => s.lightAccent);
  const rows = useSessionRows();
  const [preview, setPreview] = useState<ThemeMode>(resolved.mode);

  const surface = preview === 'dark' ? darkSurface : lightSurface;
  const accent = preview === 'dark' ? darkAccent : lightAccent;
  const lanes = rows.filter((r) => r.session.isActive).map((r) => r.name);

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="grid gap-5">
        <AppearancePicker both />
        <div className="flex items-start gap-2.5 rounded-[8px] border border-line-strong bg-sunk px-3 py-2.5 text-[12.5px] text-fg-2">
          <Info aria-hidden="true" className="mt-0.5 h-4 w-4 flex-none" />
          Gains stay green, losses red and warnings amber. Buttons stay ink.
        </div>
      </div>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <Segmented
            label="Preview"
            value={preview}
            onChange={setPreview}
            options={[
              {
                key: 'dark',
                label: (
                  <span className="inline-flex items-center gap-1.5">
                    <Moon aria-hidden="true" className="h-3.5 w-3.5" />
                    Dark preview
                  </span>
                ),
              },
              {
                key: 'light',
                label: (
                  <span className="inline-flex items-center gap-1.5">
                    <Sun aria-hidden="true" className="h-3.5 w-3.5" />
                    Light preview
                  </span>
                ),
              },
            ]}
          />
          <span className="ml-auto text-[12px] text-fg-3">
            {cap(surface)} with {accentLabel(preview, accent)}
          </span>
        </div>
        <AppearancePreview mode={preview} surface={surface} accent={accent} lanes={lanes} />
      </div>
    </div>
  );
}
