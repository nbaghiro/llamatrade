/** Design sizes of the screen art and how a frame scales them to fit. */

export const WINDOW_WIDTH = 1200;
export const WINDOW_APP_HEIGHT = 760;
export const WINDOW_BAR = 34;
/** The window's 1px border, top and bottom. */
const WINDOW_BORDER = 2;

export const PHONE_WIDTH = 412;
export const PHONE_HEIGHT = 844;

export interface DesignSize {
  width: number;
  height: number;
}

export function windowSize(
  width = WINDOW_WIDTH,
  appHeight = WINDOW_APP_HEIGHT,
  bar = true
): DesignSize {
  return { width, height: appHeight + WINDOW_BORDER + (bar ? WINDOW_BAR : 0) };
}

export const PHONE_SIZE: DesignSize = { width: PHONE_WIDTH, height: PHONE_HEIGHT };

/** Scale and rendered height of a design-size screen inside a host of `hostWidth`. */
export function fitFrame(hostWidth: number, design: DesignSize): { scale: number; height: number } {
  if (hostWidth <= 0 || design.width <= 0) return { scale: 0, height: 0 };
  const scale = hostWidth / design.width;
  return { scale, height: design.height * scale };
}

export interface StackLayout {
  /** Height of the centre window. */
  main: number;
  /** Bottom edge of the tilted windows behind it; 0 when they are hidden. */
  backs: number;
  phone: number;
  phoneTop: number;
  height: number;
}

/**
 * The hero stack: a backtest window at 46% width (100% on small screens), editor and portfolio
 * windows at 40% behind it and two phones overlapping its lower edge.
 */
export function stackLayout(width: number, small: boolean): StackLayout {
  const win = windowSize();
  const main = fitFrame(small ? width : width * 0.46, win).height;
  const backs = small ? 0 : 40 + fitFrame(width * 0.4, win).height;
  const phone = fitFrame(width * (small ? 0.26 : 0.1), PHONE_SIZE).height;
  const phoneTop = main - phone * (small ? 0.42 : 0.62);
  return {
    main,
    backs,
    phone,
    phoneTop,
    height: Math.max(main, phoneTop + phone, backs) + 16,
  };
}
