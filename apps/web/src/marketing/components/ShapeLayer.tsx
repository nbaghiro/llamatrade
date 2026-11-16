import { useId } from 'react';

import type { Shape, ShapeGroup } from '../lib/shapes';

const PAINT = { ink: 'var(--p-art-ink)', accent: 'rgb(var(--p-acc))' } as const;

/** Renders art groups as one decorative SVG. Groups take their colour from `paint` or CSS. */
export function ShapeLayer({
  width,
  height,
  groups,
  inheritColor = false,
}: {
  width: number;
  height: number;
  groups: readonly ShapeGroup[];
  /** Leave colour to CSS (the hero art) instead of the ink and accent paints. */
  inheritColor?: boolean;
}) {
  const gradient = `mk-fade-${useId().replace(/:/g, '')}`;
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.6" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      {groups.map((g, i) => (
        <g
          key={i}
          className={g.className}
          opacity={g.opacity}
          style={inheritColor ? undefined : { color: PAINT[g.paint] }}
        >
          {g.shapes.map((s, k) => (
            <ShapeEl key={k} shape={s} gradient={gradient} />
          ))}
        </g>
      ))}
    </svg>
  );
}

function ShapeEl({ shape, gradient }: { shape: Shape; gradient: string }) {
  switch (shape.kind) {
    case 'line':
      return (
        <line
          x1={shape.x1}
          x2={shape.x2}
          y1={shape.y1}
          y2={shape.y2}
          stroke="currentColor"
          strokeWidth={shape.width ?? 1}
          strokeDasharray={shape.dash}
        />
      );
    case 'rect':
      return (
        <rect
          x={shape.x}
          y={shape.y}
          width={shape.w}
          height={shape.h}
          rx={shape.rx}
          fill={shape.fill === 'hollow' ? 'none' : 'currentColor'}
          fillOpacity={shape.fill === 'tint' ? shape.opacity : undefined}
          stroke={shape.fill === 'tint' ? undefined : 'currentColor'}
        />
      );
    case 'path': {
      const fill = shape.fill ?? 'none';
      return (
        <path
          d={shape.d}
          className={shape.draw ? 'draw' : undefined}
          fill={
            fill === 'none' ? 'none' : fill === 'gradient' ? `url(#${gradient})` : 'currentColor'
          }
          fillOpacity={fill === 'tint' ? shape.opacity : undefined}
          opacity={fill === 'gradient' ? shape.opacity : undefined}
          stroke={fill === 'none' ? 'currentColor' : undefined}
          strokeWidth={fill === 'none' ? (shape.width ?? 1) : undefined}
          strokeDasharray={shape.dash}
        />
      );
    }
    case 'text':
      return (
        <text
          x={shape.x}
          y={shape.y}
          textAnchor={shape.anchor}
          fontSize={shape.size}
          fontStyle={shape.italic ? 'italic' : undefined}
          fontFamily="var(--font-mono)"
          fill="currentColor"
        >
          {shape.text}
        </text>
      );
  }
}
