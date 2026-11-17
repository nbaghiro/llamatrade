/** A small "A" tile that stands for an Alpaca account beside its name. */
export function AlpacaMark({ size = 22 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.52) }}
      className="grid flex-none place-items-center rounded-[6px] bg-[#fcd535] font-bold leading-none text-[#111]"
    >
      A
    </span>
  );
}
