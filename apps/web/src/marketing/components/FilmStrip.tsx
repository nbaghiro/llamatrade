import { useLayoutEffect, useRef, type CSSProperties } from 'react';

import { useWidth } from '../../components/charts/useWidth';
import { REDUCED_MOTION, useMedia } from '../hooks/useMedia';
import { filmOpening, filmScrollFor, filmSize, filmStep } from '../lib/film';
import type { ScreenName } from '../screens/registry';

import { ScreenFrame } from './ScreenFrame';

export interface FilmFrame {
  screen: ScreenName;
  title: string;
  caption: string;
}

/** Captioned screens in a row, three at a time on wide screens, opening on the middle one. */
export function FilmStrip({ frames }: { frames: readonly FilmFrame[] }) {
  const [outer, width] = useWidth<HTMLDivElement>(0);
  const track = useRef<HTMLDivElement>(null);
  const reduce = useMedia(REDUCED_MOTION);
  const size = filmSize(width);

  useLayoutEffect(() => {
    if (!width || !track.current) return;
    track.current.scrollLeft = filmScrollFor(filmSize(width), filmOpening(frames.length));
  }, [width, frames.length]);

  const move = (dir: -1 | 1) =>
    track.current?.scrollBy({ left: dir * filmStep(size), behavior: reduce ? 'auto' : 'smooth' });

  const vars = {
    '--fw': `${size.frame}px`,
    '--gap': `${size.gap}px`,
    '--view': `${size.view}px`,
    '--pad': `${size.pad}px`,
  } as CSSProperties;

  return (
    <div ref={outer}>
      <div className="film" style={vars}>
        <div
          ref={track}
          className="film-track"
          style={{ paddingInline: size.trackPad }}
          role="group"
          aria-label="App screens"
        >
          {frames.map((f, i) => (
            <figure key={f.screen}>
              <ScreenFrame screen={f.screen} />
              <figcaption>
                <b>{String(i + 1).padStart(2, '0')}</b>
                {f.title}. {f.caption}
              </figcaption>
            </figure>
          ))}
        </div>
        <div className="film-nav">
          <button type="button" aria-label="Previous screen" onClick={() => move(-1)}>
            ←
          </button>
          <button type="button" aria-label="Next screen" onClick={() => move(1)}>
            →
          </button>
        </div>
      </div>
    </div>
  );
}
