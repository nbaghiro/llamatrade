import { Pill } from '../ui/Pill';

/** Always visible: every figure in the beta is from an Alpaca paper account. */
export function PaperPill({ className = '' }: { className?: string }) {
  return (
    <Pill
      dot
      className={className}
      title="Paper trading. Orders go to Alpaca's paper environment and use no real money."
    >
      Paper
    </Pill>
  );
}
