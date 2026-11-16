import { AppearancePicker } from '../../../components/settings/AppearancePicker';
import { Panel } from '../parts';

export function AppearanceSection() {
  return (
    <Panel title="Appearance" aside="Saved on this device">
      <div className="px-3.5 py-4">
        <AppearancePicker />
      </div>
      <p className="m-0 border-t border-line px-3.5 py-2.5 text-xs text-fg-3">
        Light and dark show the same figures. Your choice is kept in this browser only, so another
        device starts from its own setting.
      </p>
    </Panel>
  );
}
