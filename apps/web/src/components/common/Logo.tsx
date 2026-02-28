interface LogoProps {
  size?: number;
  showText?: boolean;
}

export default function Logo({ size = 28, showText = false }: LogoProps) {
  const gradientId = `logoGradient-${Math.random().toString(36).substr(2, 9)}`;

  return (
    <div className="flex items-center gap-2.5">
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        className="flex-shrink-0"
      >
        {/* Background */}
        <rect width="32" height="32" rx="8" fill={`url(#${gradientId})`} />

        {/* Line chart 1 - slight uptrend */}
        <path
          d="M4 28 L8 26 L12 24 L16 22 L20 20 L24 21 L28 18"
          fill="none"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeOpacity="0.7"
        />

        {/* Line chart 2 - medium uptrend */}
        <path
          d="M4 28 L8 24 L12 20 L16 18 L20 14 L24 16 L28 10"
          fill="none"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeOpacity="0.7"
        />

        {/* Line chart 3 - strong uptrend */}
        <path
          d="M4 28 L8 22 L12 18 L16 12 L20 10 L24 8 L28 4"
          fill="none"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeOpacity="0.7"
        />

        {/* End dots */}
        <circle cx="28" cy="18" r="1.5" fill="white" fillOpacity="0.7" />
        <circle cx="28" cy="10" r="1.5" fill="white" fillOpacity="0.7" />
        <circle cx="28" cy="4" r="1.5" fill="white" fillOpacity="0.7" />

        <defs>
          <linearGradient
            id={gradientId}
            x1="0"
            y1="0"
            x2="32"
            y2="32"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#6D28D9" />
            <stop offset="0.33" stopColor="#2563EB" />
            <stop offset="0.66" stopColor="#059669" />
            <stop offset="1" stopColor="#047857" />
          </linearGradient>
        </defs>
      </svg>

      {showText && <span className="text-base font-semibold text-gray-900 dark:text-gray-100">LlamaTrade</span>}
    </div>
  );
}
