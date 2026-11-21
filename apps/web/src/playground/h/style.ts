import { useEffect, type CSSProperties } from 'react';

export const SERIF: CSSProperties = {
  fontFamily: "'Newsreader', 'Iowan Old Style', Georgia, serif",
  fontOpticalSizing: 'auto',
};

const FONT_HREF =
  'https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&display=swap';

/** Loads the serif used for headlines; the playground page only links Geist. */
export function useSerifFont() {
  useEffect(() => {
    if (document.querySelector(`link[href="${FONT_HREF}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = FONT_HREF;
    document.head.appendChild(link);
  }, []);
}

export const WRAP = 'mx-auto max-w-[1240px] px-4 md:px-10';
