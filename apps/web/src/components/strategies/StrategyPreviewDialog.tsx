import { useUIStore } from '../../store/ui';
import { Dialog } from '../ui';

import { TemplatePreview } from './TemplatePreview';

/** A template preview opened from elsewhere in the app. */
export default function StrategyPreviewDialog() {
  const open = useUIStore((s) => s.previewDialogOpen);
  const template = useUIStore((s) => s.previewTemplate);
  const close = useUIStore((s) => s.closePreviewDialog);
  return (
    <Dialog open={open && template !== null} onClose={close} width={720} title="Template">
      {template && <TemplatePreview template={template} showActions />}
    </Dialog>
  );
}
