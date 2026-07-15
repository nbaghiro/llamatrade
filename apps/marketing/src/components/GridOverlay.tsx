/**
 * GridOverlay — the fixed 12-column ink hairline grid behind the whole page
 * (6 columns under 720px, handled in CSS).
 */
export function GridOverlay() {
  return (
    <div className="grid-overlay" aria-hidden="true">
      <div className="cols">
        {Array.from({ length: 12 }, (_, i) => (
          <span key={i} />
        ))}
      </div>
    </div>
  );
}
