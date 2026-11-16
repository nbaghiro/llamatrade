import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

import {
  fitFrame,
  PHONE_SIZE,
  windowSize,
  WINDOW_APP_HEIGHT,
  WINDOW_WIDTH,
  type DesignSize,
} from '../lib/frame';
import { EditorScreen } from '../screens/EditorScreen';
import { PHONES, SCREENS, type PhoneName, type ScreenName } from '../screens/registry';

function useHostWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function Fit({
  design,
  className = '',
  style,
  children,
}: {
  design: DesignSize;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const [ref, width] = useHostWidth();
  const { scale, height } = fitFrame(width, design);
  return (
    <div
      ref={ref}
      className={`mk-frame ${className}`}
      style={{
        ...style,
        height: width ? height : undefined,
        aspectRatio: width ? undefined : `${design.width} / ${design.height}`,
      }}
      aria-hidden="true"
    >
      <div
        className="mk-frame-in"
        style={{
          width: design.width,
          transform: `scale(${scale})`,
          visibility: width ? undefined : 'hidden',
        }}
      >
        {children}
      </div>
    </div>
  );
}

/** A design-size app window scaled to fit its host, with an optional window bar. Decorative. */
export function ScreenFrame({
  screen,
  width = WINDOW_WIDTH,
  appHeight = WINDOW_APP_HEIGHT,
  bar = true,
  level,
  className,
  style,
}: {
  screen: ScreenName;
  width?: number;
  appHeight?: number;
  bar?: boolean;
  /** Editor level, for the editor screen. */
  level?: number;
  className?: string;
  style?: CSSProperties;
}) {
  const { title, Component } = SCREENS[screen];
  const design = windowSize(width, appHeight, bar);
  return (
    <Fit design={design} className={className} style={style}>
      <div className="win" style={{ width: design.width }}>
        {bar && (
          <div className="win-bar">
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
            <span className="ttl">{title}</span>
          </div>
        )}
        <div className="app" style={{ height: appHeight }}>
          {screen === 'editor' ? <EditorScreen level={level} /> : <Component />}
        </div>
      </div>
    </Fit>
  );
}

/** A phone at its design size, scaled to fit its host. Decorative. */
export function PhoneFrame({
  phone,
  className,
  style,
}: {
  phone: PhoneName;
  className?: string;
  style?: CSSProperties;
}) {
  const Component = PHONES[phone];
  return (
    <Fit design={PHONE_SIZE} className={className} style={style}>
      <div className="phone" style={{ width: PHONE_SIZE.width }}>
        <div className="scr">
          <div className="app mob">
            <Component />
          </div>
        </div>
      </div>
    </Fit>
  );
}
