# Real prices in the marketing ticker

The tape at the top of the marketing site shows ten ETFs with hard-coded prices, labelled
"Illustrative prices · IEX". This note covers what it would take to show real prices, what
the licences allow, and a recommended setup. A working prototype is in `.scratchpad/design-languages/ticker-live.html`,
fed by `ticker-data.js`, with the publisher sketched in the appendix below.

All terms pages below were read on 2026-11-15. Where a page shows its own date, it is given.

## Recommendation

Show **end-of-day closing prices** from a vendor whose contract explicitly allows public
website display, labelled "As of Fri, Nov 13 close" with the vendor's attribution in the tape.
A scheduled job fetches the closes after each session and publishes one small `ticker.json`
to LlamaTrade's existing public static bucket. The page reads that file, keeps the last good
copy in the browser, and falls back to values baked in at build time.

The cheapest self-serve vendor that says it allows external display is **Twelve Data Venture
at $149 a month**. Before paying, get written confirmation that Venture covers US ETF prices on
a public marketing page without the separate US Equities Add-On (two of its pages disagree).
Tiingo's redistribution bundle, $250 a month for start-ups, is the fallback.

LlamaTrade's own Alpaca data should not feed the tape. Alpaca says its API data cannot be
redistributed, on any plan.

Until a licence is signed, the current "Illustrative prices" label is the correct state.

## What the licences allow

### Alpaca

- The free Basic plan is real-time IEX only. Algo Trader Plus ($99 a month) adds all US
  exchanges. Free accounts can query SIP history at least 15 minutes old, and there is a
  `delayed_sip` feed. ([About Market Data API](https://docs.alpaca.markets/docs/about-market-data-api),
  updated 2026-10-06; [Market Data FAQ](https://docs.alpaca.markets/docs/market-data-faq),
  updated 2026-09-21)
- None of that is licensed for display to others. Alpaca's support page says: "Unfortunately,
  you cannot redistribute Alpaca API data." ([support article](https://alpaca.markets/support/redistribute-alpaca-api),
  November 2022)
- The NYSE subscriber agreement Alpaca passes through says "Subscriber shall not furnish Market
  Data to any other person or entity", and limits "Nonprofessional" to a person's own
  non-business use. ([NYSE Market Data Display Services Agreement](https://files.alpaca.markets/disclosures/library/NYSE+Market+Data+Display+Services+Agreement.pdf),
  last update March 4, 2013)
- Alpaca's general terms page returned 404, so its full terms could not be checked. Broker API
  plans are aimed at platforms, but no page says they allow logged-out public display.

So the age of the data doesn't help here. Closes or delayed prices taken from Alpaca are still
Alpaca data.

### Exchange rules

The ten ETFs list on two venues: SPY, VTI, GLD, XLK and IWM on NYSE Arca (CTA, Tape B), and QQQ,
TLT, SMH, BND and VGLT on Nasdaq (UTP, Tape C). The listings come from the brief and were not
re-checked.

| Data | Rule today | Source |
|---|---|---|
| Real-time | Needs per-user subscriber agreements or entitlements. IEX requires each data user to have "their own unique username and password". Not workable on a logged-out page. | [IEX Market Data Policies](https://www.iex.io/documents/iex-market-data-policies), September 2026 |
| 15-min delayed, CTA | "display unit fees do not apply" to delayed ticker displays, but anyone redistributing must sign the vendor agreement with NYSE. | [CTA delayed data policy](https://ctaplan.com/publicdocs/ctaplan/Policy_Delayed_Market_Data.pdf), February 2016 |
| 15-min delayed, UTP | External Delayed Redistributor fee of $250 a month plus $250 a year admin. | [UTP Data Policies](https://utpplan.com/DOC/Datapolicies.pdf), October 2026 |
| 15-min delayed, IEX | No agreement and no fee, but it must come through another data subscriber, and the display and access-control rules still apply. | IEX policies above; [IEX fee schedule](https://www.iex.io/resources/trading/fee-schedule), effective November 1, 2026 |
| End of day | UTP: "End-of-Day Usage is not currently fee liable", and vendors need no agreement from recipients. Nasdaq: no prior approval for end-of-day on uncontrolled products. No current CTA wording was found. | UTP above; [Nasdaq data policies](https://www.nasdaqtrader.com/content/AdministrationSupport/Policy/USEquitiesandOptionsDataPolicies.pdf), v2.6 |

From **April 1, 2027** the CT Plan replaces CTA and UTP. "Delayed and end-of-day redistribution
is not fee liable on any Tape but still must be explicitly licensed." Existing customers must
sign new agreements by March 1, 2027. ([CT Plan fees](https://consolidatedtape.com/fees);
[CT Plan site](https://www.consolidatedtape.com/); [CT Plan Policies v1.2](https://cdn.databp.com/tenants/datact/CT-Plan-Policies.pdf),
29 September 2026)

In practice a vendor with a public-display licence holds these exchange agreements, and
LlamaTrade follows the vendor's display rules. End-of-day data is the least restricted, which
is why it is the recommendation. 15-minute delayed data is cheap at the exchange level but adds
redistributor paperwork until April 2027.

### Vendors

Every free tier checked is personal, internal or evaluation use only. None gives a key that is
safe to put in a browser, so all of them need a server-side fetch.

| Vendor | Free tier | Cheapest plan with public display | Per month | Attribution |
|---|---|---|---|---|
| Twelve Data | Real-time US, 800 calls a day, "Internal non-display usage" | Venture, "External display data" | $149 (confirm US Equities Add-On) | "Data provided by Twelve Data", dofollow link, near the data |
| Tiingo | IEX real-time and EOD, internal and personal only | Redistribution bundle (EOD and IEX), by email | $250 start-up | None found |
| Massive (Polygon) | EOD, 5 calls a minute, personal | Stocks Business, plus $499 for delayed full market | $2,499 | Vendor-required notices |
| Financial Modeling Prep | EOD, 250 calls a day, personal | Data Display and Licensing Agreement | Not published | None found |
| EODHD | EOD and delayed, 20 calls a day, personal | Custom or Enterprise; the $399 tier is internal only | Quote | None found |
| Finnhub | 60 calls a minute, personal | Commercial plan with redistribution | Quote | None stated |
| Alpha Vantage | 25 calls a day, personal | By contact | Quote | None found |
| Nasdaq Data Link | Per dataset | Per publisher | Not verified | Not verified |
| IEX Cloud | Retired August 31, 2024 | | | |
| Yahoo, Stooq | Unofficial | Yahoo's terms forbid commercial reuse; Stooq's terms could not be read. Neither sends CORS headers. | | |

Pages and dates:
[Twelve Data pricing](https://twelvedata.com/pricing) (no date), [terms](https://twelvedata.com/terms)
(January 1, 2026), support articles on US equities (9935903,
August 18, 2026), commercial use (5332349, October 22, 2026) and attribution (12647398, January 12, 2026);
[Tiingo pricing](https://www.tiingo.com/about/pricing) and [IEX product](https://www.tiingo.com/products/iex-api) (no dates);
[Massive pricing](https://massive.com/pricing?product=stocks) (no date) and business terms (October 6, 2026);
[FMP pricing](https://site.financialmodelingprep.com/pricing-plans) and terms (August 1, 2023);
[EODHD pricing](https://eodhd.com/pricing) (no date); [Finnhub terms](https://finnhub.io/terms-of-service) (no date);
[Alpha Vantage terms](https://www.alphavantage.co/terms_of_service/) (no date).

## What LlamaTrade already has

- **market-data service** (`services/market-data`): Alpaca snapshots (`latest_trade`,
  `daily_bar`, `prev_daily_bar`), IEX feed only, cached in Redis for 15 seconds with
  single-flight fills, plus a server-side NYSE calendar with holidays and early closes in
  `market_calendar.py`. It speaks Connect only, sits behind the fail-closed `AuthMiddleware`, and
  is a ClusterIP service with no ingress path. The only public routes in the stack are auth's
  login and OAuth suffixes.
- **Marketing site**: `apps/web` builds a standalone static marketing bundle
  (`vite.marketing.config.ts`) for a Render static site, and the same page renders at `/` in the
  app. There is no server behind the static build.
- **Storage**: `infrastructure/terraform/storage.tf` already has a public
  `llamatrade-${env}-static` bucket.

A small public cached endpoint could technically be added to market-data, but it would
redistribute Alpaca data and open the first anonymous path on an authenticated service. A
scheduled job that writes a static file avoids both. It has no request-time surface, needs no
Redis, and costs nothing to serve.

## How the tape behaves

| Situation | What the tape shows |
|---|---|
| Weekday after 4:30 pm ET, weekends, holidays | "Market closed · As of Fri, Nov 13 close" and the close-to-close change |
| During the session, with end-of-day data | "Market open · As of Fri, Nov 13 close" (the previous close stays until today's close is published) |
| During the session, with delayed data (optional later) | "Market open · Delayed 15 min · 2:41 pm ET" |
| Delayed data that stopped updating | The label falls back to "As of 12:41 pm ET", so it never claims to be current |
| Publisher or bucket down | The browser's last good copy, or the build-time copy, with its own correct "As of" label |

Change colours are the only green and red: `--a-gain` and `--a-loss` from the session site. An
unchanged price is grey. Prices are always ink. The open dot uses the accent.

The label and attribution appear in both copies of the scrolling run, so with the 80-second loop
they pass at least every 40 seconds. That meets the "at least every 90 seconds" rule that IEX,
UTP and Nasdaq set for delay messages in tickers. The tape pauses on hover so the attribution
link can be clicked.

Once real data is live, the footer line "Figures are illustrative" should be scoped to the
product screenshots, since the tape would no longer be illustrative.

## Cost

| Option | Monthly | Licensing risk | Freshness |
|---|---|---|---|
| Keep illustrative prices | $0 | None | Not real |
| Twelve Data Venture, end of day | $149, plus pennies for the job and bucket | Low once the add-on question is answered in writing | Previous close |
| Same vendor, 15-minute delayed | $149, plus a possible UTP delayed redistributor fee of $250 until April 2027 unless the vendor's licence covers it | Low to medium | 15 minutes |
| Tiingo redistribution bundle | $250 | Low, by email agreement | Close or delayed |
| Massive Business with delayed add-on | $2,998 plus exchange fees | Low | 15 minutes |
| Alpaca data | $0 or $99 | High: Alpaca says it cannot be redistributed | Any |

## What Naib needs to decide or sign up for

1. **Whether real prices are worth $149 a month** on a marketing page, against keeping the
   illustrative label.
2. **End of day or delayed.** End of day is recommended: simpler licensing, two job runs a day,
   and the tape reads the same on weekends.
3. **Vendor confirmation in writing.** Ask Twelve Data whether Venture covers US ETF prices on a
   public, logged-out marketing page without the US Equities Add-On, the exact attribution
   wording, and whether their licence covers the CTA/UTP delayed redistributor obligations if
   delayed data is chosen. If the answer is no or more expensive, ask Tiingo the same.
4. **Sign up** for the chosen plan and store the key as a secret. Nothing was signed up for here.
5. **Optional:** ask Alpaca sales whether a written redistribution addendum exists for public
   display. If it does and is cheap, the existing market-data stack could feed the publisher.

## Prototype

- `ticker-live.html`: the tape in the session site's style, light and dark, with four
  scenarios (weekend close, open and delayed, stalled refresh, endpoint down). It fetches
  `ticker-mock-closed.json` and builds the open-session cases in memory. The prices are mock
  values and the attribution reads "Mock data for the prototype". Serve the folder over HTTP to
  try it, for example `python3 -m http.server` in this directory.
- `ticker-data.js`: fetch with a 5-second timeout, schema check, last good copy in
  `localStorage` (wrapped in try/catch), build-time fallback, market-aware refresh (60 seconds
  while open, up to 15 minutes while closed, paused while the tab is hidden), and the labels
  above.
- The appendix: the JSON contract, the publisher job and schedule, hosting, and a
  request-time variant.

Checked in headless Chrome at 1280 and 390 pixels in both modes: labels and colours are correct
in each scenario, there is no horizontal page scroll, and there are no script errors.

### Not verified

- Whether Twelve Data Venture needs the US Equities Add-On for this use, and its price.
- Whether the CTA $1,000 a month redistribution charge applies to a delayed-only redistributor.
- How IEX and UTP access-control rules apply to delayed data on an anonymous page.
- Current CTA and NYSE wording on end-of-day data.
- FMP, Finnhub, Alpha Vantage, EODHD and Nasdaq Data Link display prices.
- Alpaca's full terms (the page returned 404).


---

## Appendix: the publisher job, sketched


This is a sketch for review. Nothing here is in LlamaTrade's services yet, and it should not
be added until a data licence is in place (see the sections above).

The marketing tape reads one small JSON document. A scheduled job builds it from a licensed
vendor and publishes it as a static file, so the site never calls the vendor and no key
reaches the browser. The same builder can sit behind a request-time endpoint instead; that
variant is at the end.

## The JSON contract

`ticker-data.js` validates this shape and `ticker-mock-closed.json` is an example of it.

```json
{
  "version": 1,
  "generated_at": "2026-11-13T21:31:04Z",
  "as_of": "2026-11-13T21:00:00Z",
  "basis": "close",
  "delay_minutes": null,
  "session_date": "2026-11-13",
  "market": {
    "is_open": false,
    "next_open": "2026-11-16T14:30:00Z",
    "next_close": "2026-11-16T21:00:00Z"
  },
  "source": {
    "provider": "Twelve Data",
    "feed": "eod",
    "attribution": "Data provided by Twelve Data",
    "url": "https://twelvedata.com/"
  },
  "quotes": [
    { "symbol": "SPY", "price": 682.14, "prev_close": 679.29, "change": 2.85, "change_pct": 0.42 }
  ]
}
```

| Field | Meaning |
|---|---|
| `as_of` | Time the prices describe. For `close` it is the session close; for `delayed` it is the time of the delayed print. The page builds its label from this, so old values stay correctly described. |
| `basis` | `close` (end of day), `delayed` (15 minutes) or `realtime`. Only `close` and `delayed` are in scope. |
| `session_date` | The New York trading date the prices belong to. |
| `market` | Open or closed now, with the next open and close in UTC. Holidays and early closes come from the NYSE calendar. |
| `source` | Attribution text and link, exactly as the vendor requires. The page shows it in the tape. |
| `quotes` | One row per symbol, in display order. `change` and `change_pct` are against the previous session's close. |

## Builder

Python, async, in the style of the existing services. The vendor call is isolated so a
different licensed provider only changes `_fetch_quotes`. Field names are from Twelve Data's
`/quote` docs (fetched 2026-11-15); check them and the batch syntax against a real response
before relying on this.

```python
"""Build and publish the marketing ticker snapshot."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

logger = logging.getLogger(__name__)

SYMBOLS = ("SPY", "QQQ", "VTI", "TLT", "GLD", "SMH", "XLK", "IWM", "BND", "VGLT")
QUOTE_URL = "https://api.twelvedata.com/quote"
ATTRIBUTION = {
    "provider": "Twelve Data",
    "attribution": "Data provided by Twelve Data",
    "url": "https://twelvedata.com/",
}


@dataclass(frozen=True)
class Session:
    is_open: bool
    session_date: date
    close_at: datetime
    next_open: datetime
    next_close: datetime


async def _fetch_quotes(client: httpx.AsyncClient, api_key: str, eod: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for symbol in SYMBOLS:
        resp = await client.get(
            QUOTE_URL,
            params={"symbol": symbol, "eod": str(eod).lower()},
            headers={"Authorization": f"apikey {api_key}"},
        )
        resp.raise_for_status()
        q = resp.json()
        price = float(q["close"])
        prev = float(q["previous_close"])
        if price <= 0 or prev <= 0:
            raise ValueError(f"implausible quote for {symbol}")
        rows.append(
            {
                "symbol": symbol,
                "price": round(price, 2),
                "prev_close": round(prev, 2),
                "change": round(price - prev, 2),
                "change_pct": round((price - prev) / prev * 100, 2),
            }
        )
    return rows


async def build_snapshot(api_key: str, session: Session, basis: str) -> dict[str, object]:
    """Return the ticker document; raises if any symbol is missing so a partial tape is never published."""
    async with httpx.AsyncClient(timeout=10) as client:
        quotes = await _fetch_quotes(client, api_key, eod=basis == "close")
    now = datetime.now(UTC)
    as_of = session.close_at if basis == "close" else now.replace(second=0, microsecond=0)
    return {
        "version": 1,
        "generated_at": now.isoformat(),
        "as_of": as_of.isoformat(),
        "basis": basis,
        "delay_minutes": 15 if basis == "delayed" else None,
        "session_date": session.session_date.isoformat(),
        "market": {
            "is_open": session.is_open,
            "next_open": session.next_open.isoformat(),
            "next_close": session.next_close.isoformat(),
        },
        "source": {**ATTRIBUTION, "feed": "eod" if basis == "close" else "delayed"},
        "quotes": quotes,
    }


async def publish(doc: dict[str, object], bucket: str, max_age: int) -> None:
    """Upload ticker.json to the public static bucket with a short cache lifetime."""
    body = json.dumps(doc, separators=(",", ":")).encode()
    # google-cloud-storage is sync; wrap in asyncio.to_thread in the real job.
    ...  # blob.cache_control = f"public, max-age={max_age}"; blob.upload_from_string(body, "application/json")
```

`Session` comes from `services/market-data/src/market_calendar.py`, which already knows NYSE
holidays and early closes. Moving the pure calendar functions into `libs/common` would let the
job use them without importing a service. The job does not need Alpaca at all.

### Failure handling

- Any vendor error, timeout or missing symbol fails the run and nothing is uploaded. The last
  good `ticker.json` stays in the bucket, and the page keeps its own last good copy too.
- A sanity check against the stored document rejects a move of more than 20% on any symbol
  (likely a bad print or a split the vendor has not adjusted yet) and logs it for review.
- The run logs with a template plus fields and opens its own root span, per `.docs/telemetry.md`.

## Schedule

End of day, which is the recommended first step:

| When (New York) | What |
|---|---|
| 16:30 on trading days, 13:30 on early-close days | Fetch with `eod=true`, publish `basis: "close"`, `max-age=300`. |
| 20:00 on trading days | Same again, to pick up any late corrections. |

Weekends and holidays need no run: the Friday document already says "As of Fri close" and
carries Monday's `next_open`. Ten symbols twice a day is 20 vendor credits a day.

Fifteen-minute delayed, if that is chosen later: every minute from 09:45 to 16:15, publish
`basis: "delayed"` with `max-age=60`, then the end-of-day runs above. That is 10 credits a minute and about
3,900 a day for ten symbols; check this against the Venture plan's limits before choosing it.

## Hosting

- **Job:** a Kubernetes CronJob next to the existing workloads, or Cloud Scheduler with a
  Cloud Run job. It needs one secret (`TWELVEDATA_API_KEY`) through External Secrets.
- **File:** `llamatrade-${env}-static/ticker/ticker.json` in the existing public static bucket
  (`infrastructure/terraform/storage.tf`). The bucket needs a CORS rule allowing `GET` from the
  marketing origin, or the file can be served from the marketing domain through a rewrite.
- **Page:** `LTTicker.mount(tape, { url: "https://…/ticker/ticker.json", fallback: BUILT_IN })`.
  `BUILT_IN` is written at marketing build time from the current `ticker.json`, so a fresh deploy
  never shows an empty tape.

No service gains a public route, and the authenticated market-data service is untouched.

## Request-time variant

If a request-time endpoint is preferred (for example to add more symbols on demand), the same
`build_snapshot` sits behind `GET /ticker` on a small public service, with the result cached in
Redis under `ticker:v1` for 60 seconds while open and until the next open while closed, a
single-flight lock so a burst of visitors makes one vendor call, and the last good document
returned with `Cache-Control: max-age=60` when the vendor fails. It should not be a public path
on market-data: that service is behind the fail-closed `AuthMiddleware`, has no ingress, and its
data comes from Alpaca, which cannot be redistributed.
