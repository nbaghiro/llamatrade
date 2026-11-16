import { DEFAULT_LEVEL, EDITOR_LEVELS, type TreeItem } from '../data/editorLevels';

import { AppNav, Code, Panel, WeightBar } from './parts';

function Tree({ items }: { items: readonly TreeItem[] }) {
  return (
    <>
      {items.map((item, i) =>
        item.kind === 'asset' ? (
          <div key={i} className={`asset ${item.muted ? 't3' : ''}`}>
            <b className="sym">{item.sym}</b>
            <span className={item.muted ? undefined : 't2'}>{item.name}</span>
            <WeightBar parts={[{ shade: item.shade, weight: item.weight || 1 }]} />
            <span className="tnum text-right">{item.weight.toFixed(1)}%</span>
          </div>
        ) : (
          <div key={i}>
            <div className={`node ${item.state ?? ''}`}>
              <span>
                <span className="kw">{item.keyword}</span>
                {item.label}
              </span>
              {item.noteStyle === 'text' ? (
                <span className="t3">{item.note}</span>
              ) : (
                <span className={item.noteStyle === 'chip-ok' ? 'chip ok' : 'chip'}>
                  {item.note}
                </span>
              )}
            </div>
            {item.children && (
              <div className={`kids ${item.children.on ? 'on' : ''}`}>
                <Tree items={item.children.items} />
              </div>
            )}
          </div>
        )
      )}
    </>
  );
}

export function EditorScreen({ level = DEFAULT_LEVEL }: { level?: number }) {
  const L = EDITOR_LEVELS[level] ?? EDITOR_LEVELS[DEFAULT_LEVEL];
  return (
    <>
      <AppNav on="Strategies" />
      <div className="app-main">
        <div className="hd">
          <div>
            <h3>{L.name}</h3>
            <div className="meta">{L.meta}</div>
          </div>
          <div className="acts">
            <span className="b">Blocks</span>
            <span className="b">Save version</span>
            <span className="b p">Backtest</span>
          </div>
        </div>
        <div className="cols-2">
          <Panel title="Blocks" aside="evaluated at Nov 13 close">
            <div className="pn-b tree">
              <Tree items={L.tree} />
            </div>
          </Panel>
          <div className="vgrid content-start">
            <Panel title="Source" aside="0 problems">
              <Code lines={L.code} />
            </Panel>
            <Panel title="Would hold today" aside={<span className="tnum">Nov 13</span>}>
              <div className="pn-b">
                <WeightBar parts={L.hold} />
                <div className="leg mt-2">
                  {L.hold.map((h) => (
                    <span key={h.sym}>
                      <i className={`sw ${h.shade}`} />
                      <b className="sym">{h.sym}</b> <span className="tnum">{h.weight}%</span>
                    </span>
                  ))}
                </div>
                <div className="needs">
                  {L.needs.map(([a, b]) => (
                    <div key={a}>
                      <span className="lbl">{a}</span>
                      <div className="tnum mt-0.5">{b}</div>
                    </div>
                  ))}
                </div>
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </>
  );
}
