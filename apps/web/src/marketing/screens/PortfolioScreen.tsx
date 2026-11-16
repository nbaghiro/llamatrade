import { LineChart } from '../../components/charts';
import { formatMoney } from '../../lib/format';
import { accountMonth, shortDate, SLEEVE_SPLIT } from '../data/illustrative';

import { AppNav, Figure, Panel, Status, Table, WeightBar } from './parts';

/** Account equity over one month against SPY, for the portfolio screen and the Home phone. */
export function AccountChart({ height, compact = false }: { height: number; compact?: boolean }) {
  const am = accountMonth();
  return (
    <LineChart
      label="Account equity over one month against SPY"
      dates={am.days}
      height={height}
      yTickCount={3}
      xTickCount={compact ? 2 : 4}
      series={[
        { values: am.benchmark, kind: 'bench' },
        { values: am.account, kind: 'main', area: true },
      ]}
      yFormat={(v) => `${(v / 1000).toFixed(1)}k`}
      xFormat={shortDate}
      base={100000}
      pad={{ l: 40 }}
      tooltip={(i) => (
        <>
          <b className="block font-medium text-fg-3">{shortDate(am.days[i])}</b>
          {formatMoney(am.account[i])}
        </>
      )}
    />
  );
}

export function PortfolioScreen() {
  return (
    <>
      <AppNav on="Portfolio" />
      <div className="app-main">
        <div className="hd">
          <div>
            <h3>Portfolio</h3>
            <div className="meta">Alpaca paper account · Nov 13 close</div>
          </div>
          <div className="acts">
            <span className="b">Add paper funds</span>
            <span className="b p">Deploy a strategy</span>
          </div>
        </div>
        <div className="kp pn">
          <Figure label="Total equity" value="$103,410.27" detail="book of record" />
          <Figure label="Today" value="+$895.40" detail="+0.87%" tone="gain" />
          <Figure label="Unallocated" value="$17,077.12" detail="16.5% of equity" />
          <Figure label="Sleeves" value="3" detail="2 running · 1 frozen" />
        </div>
        <div className="alert">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M10 2.5 18 17H2L10 2.5Z" />
            <path d="M10 8v4M10 14.2v.3" />
          </svg>
          <div>
            <b>Recession Radar is frozen</b>
            Alpaca reports 120 TLT shares and the ledger expects 167. New orders for this sleeve
            wait until the difference is resolved.
          </div>
          <span className="b">Review</span>
        </div>
        <div className="cols-portfolio">
          <Panel title="Sleeves" aside="allocation of equity">
            <div className="pn-b short">
              <WeightBar parts={SLEEVE_SPLIT} />
            </div>
            <Table
              columns={[
                { label: 'Sleeve' },
                { label: 'State' },
                { label: 'Market value', numeric: true },
                { label: 'Today', numeric: true },
                { label: 'Total', numeric: true },
              ]}
            >
              <tr>
                <td>All-Weather Portfolio</td>
                <td>
                  <Status state="running" />
                </td>
                <td className="n">35,982.55</td>
                <td className="n loss">−84.12</td>
                <td className="n gain">+982.55</td>
              </tr>
              <tr className="sel">
                <td>Recession Radar</td>
                <td>
                  <Status state="frozen" />
                </td>
                <td className="n">25,436.18</td>
                <td className="n gain">+112.40</td>
                <td className="n gain">+436.18</td>
              </tr>
              <tr>
                <td>Tech Momentum Rotation</td>
                <td>
                  <Status state="running" />
                </td>
                <td className="n">24,914.42</td>
                <td className="n gain">+867.12</td>
                <td className="n loss">−85.58</td>
              </tr>
              <tr>
                <td className="t3">Unallocated</td>
                <td />
                <td className="n">17,077.12</td>
                <td />
                <td />
              </tr>
              <tr className="tot">
                <td>Total equity</td>
                <td />
                <td className="n">103,410.27</td>
                <td className="n gain">+895.40</td>
                <td />
              </tr>
            </Table>
          </Panel>
          <Panel title="Account equity, 1 month" aside="vs SPY">
            <div className="pn-b">
              <AccountChart height={190} />
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
