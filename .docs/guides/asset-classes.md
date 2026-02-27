# Asset Classes Reference

Comprehensive guide to tradeable asset classes: what they are, how they're traded, and which strategies work best for each.

---

## Quick Comparison

| Asset Class     | Liquidity         | Volatility  | Leverage | Trading Hours  | Settlement  | Min Capital |
| --------------- | ----------------- | ----------- | -------- | -------------- | ----------- | ----------- |
| **Equities**    | High (large caps) | Medium      | 2-4x     | Exchange hours | T+1         | $100+       |
| **Options**     | Medium            | High        | Built-in | Exchange hours | T+1         | $2,000+     |
| **Futures**     | Very High         | Medium-High | 10-20x   | Near 24h       | Daily mark  | $5,000+     |
| **Forex**       | Highest           | Low-Medium  | 50-500x  | 24h Sun-Fri    | T+2         | $100+       |
| **Crypto**      | Medium            | Very High   | 1-125x   | 24/7           | Instant     | $10+        |
| **Bonds**       | Low-Medium        | Low         | 10-20x   | Exchange hours | T+1         | $1,000+     |
| **ETFs**        | High              | Varies      | 2-4x     | Exchange hours | T+1         | $100+       |
| **CFDs**        | High              | Varies      | 5-30x    | Near 24h       | No delivery | $200+       |
| **Commodities** | Medium            | High        | 10-20x   | Near 24h       | Varies      | $5,000+     |

### Asset Class Risk/Return Spectrum

```
                          RISK / RETURN SPECTRUM

    Low Risk                                              High Risk
    Low Return                                            High Return
        │                                                      │
        ▼                                                      ▼
    ┌───────┐  ┌───────┐  ┌────────┐  ┌───────┐  ┌───────┐  ┌───────┐
    │ Bonds │──│ ETFs  │──│Equities│──│Futures│──│Options│──│Crypto │
    │       │  │       │  │        │  │       │  │       │  │       │
    │ 2-5%  │  │ 7-10% │  │ 8-12%  │  │10-20% │  │20-50% │  │50%+   │
    └───────┘  └───────┘  └────────┘  └───────┘  └───────┘  └───────┘
        │          │          │          │          │          │
        │          │          │          │          │          │
    Stability  Diversified  Growth    Leverage   Leverage  Speculation
    Income     Exposure     Capital   Both ways  + Decay   24/7
```

### Trading Hours Overview

```
                    GLOBAL TRADING HOURS (ET)

    │ 12am  3am   6am   9am   12pm  3pm   6pm   9pm  12am
    │   │     │     │     │     │     │     │     │     │
────┼───┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴───
    │
EQUITIES         ┌─────────────────┐
(US)             │   9:30am-4pm    │
                 └─────────────────┘

FUTURES  ──────────────────────────────────────────────────
(ES,NQ)         (Nearly 24h, brief breaks)

FOREX    ──────────────────────────────────────────────────
                (24h Sun 5pm - Fri 5pm)

CRYPTO   ══════════════════════════════════════════════════
                (24/7/365, never closes)

BONDS            ┌─────────────────┐
(Cash)           │  8am - 5pm ET   │
                 └─────────────────┘
```

---

## 1. Equities (Stocks)

### What It Is

Stocks represent fractional ownership in a company. When you buy a share, you own a tiny piece of that company's assets, earnings, and voting rights. Stock prices are driven by company performance, earnings growth, market sentiment, and macroeconomic factors.

### Key Characteristics

```
Ownership:     Fractional ownership of company
Dividends:     May pay quarterly dividends
Voting:        Common shares have voting rights
Price driver:  Company earnings, growth, sentiment
```

### Types of Equities

| Type                | Description                                            | Examples          |
| ------------------- | ------------------------------------------------------ | ----------------- |
| **Common Stock**    | Standard ownership with voting rights                  | AAPL, GOOGL, MSFT |
| **Preferred Stock** | Fixed dividend, no voting, priority in liquidation     | BAC-PL            |
| **ADRs**            | Foreign stocks traded on US exchanges                  | BABA, TSM, NVO    |
| **REITs**           | Real estate investment trusts (90% income distributed) | VNQ, SPG, O       |
| **SPACs**           | Special purpose acquisition companies                  | Varies            |

### Market Structure

```
Primary Exchanges:  NYSE, NASDAQ, LSE, TSE, HKEX
Regular Hours:      9:30 AM - 4:00 PM ET (US)
Pre-market:         4:00 AM - 9:30 AM ET
After-hours:        4:00 PM - 8:00 PM ET
Tick size:          $0.01 (penny increments)
Settlement:         T+1 (trade date + 1 business day)
```

### How It's Traded

**Order Types:**

- Market orders: Immediate execution at best available price
- Limit orders: Execute only at specified price or better
- Stop orders: Trigger when price reaches threshold
- Stop-limit: Combines stop trigger with limit execution

**Data Levels:**

```
Level 1:       Bid, Ask, Last, Volume
Level 2:       Full order book depth (all bids/asks)
Time & Sales:  Every executed trade with timestamp
```

### Key Metrics

- **Market Cap** = Share Price × Shares Outstanding
- **P/E Ratio** = Price / Earnings Per Share
- **EPS** = Net Income / Shares Outstanding
- **Dividend Yield** = Annual Dividend / Price
- **Beta** = Volatility relative to market

### Best Strategies for Equities

| Strategy             | Why It Works                                           | Time Horizon    |
| -------------------- | ------------------------------------------------------ | --------------- |
| **Momentum**         | Stocks trend due to earnings cycles and sentiment      | Days to weeks   |
| **Mean Reversion**   | Short-term overreaction creates bounce opportunities   | Hours to days   |
| **Pairs Trading**    | Related stocks maintain spread relationship            | Days to weeks   |
| **Factor Investing** | Value, momentum, quality factors have persistent alpha | Weeks to months |
| **Earnings Plays**   | Predictable volatility around announcements            | Event-driven    |
| **Dividend Capture** | Buy before ex-date, capture dividend, sell after       | Days            |

### Considerations

- High liquidity in large caps (AAPL, MSFT), thin in small caps
- Extended hours have wider spreads and lower liquidity
- Corporate actions (splits, dividends) affect historical data
- Short selling requires locating/borrowing shares
- Pattern Day Trader rule: $25,000 minimum for US accounts making 4+ day trades/week

---

## 2. Options

### What It Is

Options are contracts giving the right (not obligation) to buy or sell an underlying asset at a specific price (strike) by a specific date (expiration). A **call** gives the right to buy; a **put** gives the right to sell. Options provide leverage, hedging, and income generation capabilities.

### Key Characteristics

```
Premium:       Price paid for the option contract
Strike:        Price at which option can be exercised
Expiration:    Date when option expires worthless if OTM
Contract size: 100 shares per contract (standard)
```

### Option Types

| Type         | Exercise                   | Common In               |
| ------------ | -------------------------- | ----------------------- |
| **American** | Any time before expiration | US equities             |
| **European** | Only at expiration         | Index options, FX       |
| **Weekly**   | Expires each Friday        | High-volume underlyings |
| **LEAPS**    | Long-term (1-3 years)      | Stock replacement       |

### Moneyness

```
ITM (In The Money):
  Call: Stock Price > Strike (has intrinsic value)
  Put:  Stock Price < Strike (has intrinsic value)

ATM (At The Money):
  Stock Price ≈ Strike (most time value, highest gamma)

OTM (Out of The Money):
  Call: Stock Price < Strike (only time value)
  Put:  Stock Price > Strike (only time value)
```

### The Greeks

| Greek         | Measures                  | Range     | Practical Meaning                                  |
| ------------- | ------------------------- | --------- | -------------------------------------------------- |
| **Delta (Δ)** | Price sensitivity         | -1 to +1  | $0.50 delta = option moves $0.50 per $1 stock move |
| **Gamma (Γ)** | Delta's rate of change    | 0+        | How fast delta changes; highest ATM near expiry    |
| **Theta (Θ)** | Time decay per day        | Usually - | Options lose value daily; accelerates near expiry  |
| **Vega (ν)**  | IV sensitivity            | 0+        | Higher IV = higher option prices                   |
| **Rho (ρ)**   | Interest rate sensitivity | Varies    | Mostly matters for LEAPS                           |

```
GREEKS VISUALIZATION

                    OPTION PRICE
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
    ┌───────┐       ┌────────┐       ┌───────┐
    │ Delta │       │ Theta  │       │ Vega  │
    │       │       │        │       │       │
    │ Stock │       │ Time   │       │  IV   │
    │ moves │       │ decay  │       │change │
    └───────┘       └────────┘       └───────┘

    Most important ◄─────────────► Least important
```

### Market Structure

```
Exchanges:     CBOE, ISE, PHLX, AMEX, BOX
Contract size: 100 shares per contract
Expiration:    Weekly (Fri), Monthly (3rd Fri), Quarterly, LEAPS
Settlement:    Physical delivery (equity) or cash (index)
Assignment:    Random selection among short holders
```

### How It's Traded

**Options Chain:**

```
              CALLS                    PUTS
Strike   Bid    Ask    IV      Bid    Ask    IV
$95     $6.20  $6.40  28%     $0.80  $0.95  32%
$100    $2.50  $2.65  25%     $2.10  $2.25  26%  ← ATM
$105    $0.70  $0.85  27%     $5.30  $5.50  29%
```

**Execution:**

- Wider bid-ask spreads than underlying stock
- Liquidity concentrated at ATM strikes and near-term expirations
- Multi-leg orders (spreads) may get better fills than legging in

### Best Strategies for Options

| Strategy              | Market View                          | Risk/Reward                       |
| --------------------- | ------------------------------------ | --------------------------------- |
| **Covered Call**      | Neutral to mildly bullish            | Limited upside, income            |
| **Cash-Secured Put**  | Bullish, want to buy stock           | Premium income, obligation to buy |
| **Iron Condor**       | Range-bound, low volatility          | Defined risk, limited profit      |
| **Straddle/Strangle** | Big move expected, direction unknown | Unlimited profit, premium at risk |
| **Vertical Spread**   | Directional with defined risk        | Capped profit/loss                |
| **Calendar Spread**   | Expecting time decay, stable price   | Profit from theta differential    |
| **Butterfly**         | Pinpoint price target at expiration  | Low cost, high reward if correct  |

### Considerations

- Leverage is built in (control 100 shares for fraction of cost)
- Time decay works against long options
- Implied volatility (IV) affects pricing significantly
- IV crush after earnings can hurt long options even if direction is right
- Assignment risk for short options (especially near ex-dividend dates)
- Complex tax treatment for options trades

---

## 3. Futures

### What It Is

Futures are standardized contracts obligating the buyer to purchase (or seller to sell) an asset at a predetermined price on a future date. Unlike options, futures are binding obligations. They're used for hedging commercial risk and speculation.

### Key Characteristics

```
Obligation:     Must buy/sell at expiration (binding contract)
Leverage:       High (5-20% initial margin)
Mark-to-market: Daily settlement of gains/losses to margin account
Expiration:     Specific delivery months (quarterly for financials)
```

### Types of Futures

| Category           | Examples                            | Characteristics            |
| ------------------ | ----------------------------------- | -------------------------- |
| **Equity Index**   | ES (S&P 500), NQ (Nasdaq), YM (Dow) | Cash settled, most liquid  |
| **Commodities**    | CL (Crude), GC (Gold), ZC (Corn)    | Physical delivery possible |
| **Interest Rates** | ZN (10Y Note), ZB (30Y Bond)        | Rate expectations          |
| **Currencies**     | 6E (EUR/USD), 6J (JPY/USD)          | Physical delivery          |
| **Crypto**         | BTC, ETH futures (CME)              | Cash settled, regulated    |

### Popular Contracts

| Contract         | Symbol | Tick Size | Tick Value | Margin   |
| ---------------- | ------ | --------- | ---------- | -------- |
| E-mini S&P 500   | ES     | 0.25      | $12.50     | ~$12,000 |
| Micro E-mini S&P | MES    | 0.25      | $1.25      | ~$1,200  |
| E-mini Nasdaq    | NQ     | 0.25      | $5.00      | ~$16,000 |
| Crude Oil        | CL     | $0.01     | $10.00     | ~$8,000  |
| Gold             | GC     | $0.10     | $10.00     | ~$9,000  |

### Futures Pricing

```
Theoretical Price:
  F = S × e^((r - d) × t)

Where:
  F = futures price
  S = spot price
  r = risk-free rate
  d = dividend yield (or convenience yield for commodities)
  t = time to expiration

Basis = Futures - Spot

Contango:      Futures > Spot (normal, cost of carry)
Backwardation: Futures < Spot (supply shortage, convenience yield)
```

```
CONTANGO vs BACKWARDATION

CONTANGO (Normal)                    BACKWARDATION (Supply shortage)

Price                                Price
  │                                    │
  │              Jun ●                 │  Spot ●
  │          May ●                     │       ╲
  │      Apr ●                         │        ╲
  │  Mar ●                             │    Mar  ●
  │ Spot ●                             │          ╲
  │                                    │       Apr ●
  │                                    │             ╲
  │                                    │          May ●
  └────────────────▶                   └────────────────▶
     Time to expiry                       Time to expiry

Futures ABOVE spot                   Futures BELOW spot
Rolling long = LOSS                  Rolling long = PROFIT
(sell low, buy high)                 (sell high, buy low)

Storage costs drive contango         Scarcity drives backwardation
```

### Rolling Contracts

```
Futures expire quarterly (Mar, Jun, Sep, Dec for financials)
Must roll to next contract before expiration

Roll process:
  1. Close position in expiring contract
  2. Open same position in next month contract
  3. Roll cost = price difference between contracts

Roll dates: Typically 1-2 weeks before expiration
Volume shifts to next contract around roll date
```

### How It's Traded

```
Trading hours:    Sunday 6pm - Friday 5pm ET (23h/day)
                  Brief halt 4:15-4:30pm and 5:00-6:00pm ET
Settlement:       Daily mark-to-market
Margin types:     Initial (to open), Maintenance (minimum balance)
Margin call:      Account below maintenance = add funds or liquidate
```

### Best Strategies for Futures

| Strategy            | Why It Works                                | Notes                     |
| ------------------- | ------------------------------------------- | ------------------------- |
| **Trend Following** | Strong trends in commodities and currencies | Turtle Trading origin     |
| **Spread Trading**  | Calendar spreads (front vs back month)      | Lower margin, lower risk  |
| **Mean Reversion**  | Index futures revert intraday               | ES mean reversion popular |
| **Momentum**        | Cross-asset momentum                        | Managed futures approach  |
| **Arbitrage**       | Spot vs futures, cross-exchange             | Requires speed            |
| **Carry Trade**     | Roll yield in backwardated markets          | Long-term                 |

### Considerations

- Very high leverage amplifies gains AND losses
- Margin calls can force liquidation at worst times
- Near 24-hour trading requires automation for risk management
- Must manage roll dates to avoid delivery (especially commodities)
- Extremely liquid (ES trades billions in notional daily)

---

## 4. Forex (Foreign Exchange)

### What It Is

Forex is the exchange of one currency for another. It's the largest financial market in the world (~$7 trillion daily volume). Currencies are always quoted in pairs (EUR/USD = how many USD to buy 1 EUR). The market is decentralized (OTC), operating through a network of banks, brokers, and electronic platforms.

### Key Characteristics

```
Pairs:         Always quoted as base/quote (EUR/USD)
Decentralized: No central exchange (OTC market)
Size:          Largest market (~$7 trillion daily)
Leverage:      Very high (50:1 to 500:1 available)
```

### Major Currency Pairs

| Pair        | Name       | Characteristics                           |
| ----------- | ---------- | ----------------------------------------- |
| **EUR/USD** | Euro       | Most traded, tightest spreads (0.5-1 pip) |
| **USD/JPY** | Dollar-Yen | Asian session active, safe haven flows    |
| **GBP/USD** | Cable      | Volatile, news-sensitive                  |
| **USD/CHF** | Swissie    | Safe haven, low volatility                |
| **AUD/USD** | Aussie     | Commodity correlated, risk sentiment      |
| **USD/CAD** | Loonie     | Oil correlated                            |
| **NZD/USD** | Kiwi       | Carry trade popular, dairy prices         |

**Cross Pairs** (no USD): EUR/GBP, EUR/JPY, GBP/JPY, AUD/NZD
**Exotic Pairs**: USD/TRY, USD/ZAR, USD/MXN (wider spreads, higher volatility)

### Pricing Conventions

```
EUR/USD = 1.0850
  Base currency: EUR (what you're buying/selling)
  Quote currency: USD (what you're paying with)
  Means: 1 EUR costs 1.0850 USD

Pip:  Smallest standard price increment
      0.0001 for most pairs (fourth decimal)
      0.01 for JPY pairs (second decimal)

Lot sizes:
  Standard lot:  100,000 units of base currency
  Mini lot:      10,000 units
  Micro lot:     1,000 units
```

### Trading Sessions

```
          5pm   8pm   11pm  2am   5am   8am   11am  2pm   5pm
           |     |     |     |     |     |     |     |     |
Sydney:    ██████████████████████
Tokyo:           ████████████████████████
London:                            ████████████████████████
New York:                                      ████████████████████

Most active: London-New York overlap (8am - 12pm ET)
             Tightest spreads, highest volume
```

### Key Drivers

- **Interest rate differentials**: Higher rates attract capital
- **Economic data**: GDP, employment, inflation, trade balance
- **Central bank policy**: Fed, ECB, BOJ, BOE decisions
- **Risk sentiment**: Risk-on (buy AUD, NZD) vs risk-off (buy JPY, CHF)
- **Geopolitics**: Elections, trade wars, conflicts

### How It's Traded

```
Spot market:   Immediate exchange (T+2 settlement)
Forwards:      Future exchange at agreed rate
Swaps:         Exchange now, reverse later
Futures:       Standardized contracts (CME)

Retail brokers: OANDA, FXCM, Interactive Brokers
Spreads:       0.5-1 pip majors, 3-10 pips exotics
Rollover:      Overnight positions incur swap cost/credit
```

### Best Strategies for Forex

| Strategy            | Why It Works                                  | Time Horizon       |
| ------------------- | --------------------------------------------- | ------------------ |
| **Carry Trade**     | Earn interest differential between currencies | Weeks to months    |
| **Trend Following** | Currencies trend due to economic cycles       | Days to weeks      |
| **News Trading**    | High-impact events move currencies quickly    | Minutes to hours   |
| **Range Trading**   | Many pairs range-bound during quiet sessions  | Hours              |
| **Breakout**        | London open/session overlaps create breakouts | Hours              |
| **Scalping**        | Tight spreads allow many small profits        | Seconds to minutes |

### Considerations

- Extremely high liquidity means tight spreads on majors
- Leverage of 50:1+ amplifies gains AND losses significantly
- Swap/rollover costs for overnight positions can add up
- News releases (NFP, FOMC) cause extreme volatility spikes
- 24-hour market means gaps are rare (except weekends)
- Counterparty risk with retail brokers

---

## 5. Cryptocurrencies

### What It Is

Digital currencies using blockchain technology and cryptography. Bitcoin, the first cryptocurrency, was created in 2009. Unlike traditional currencies, most cryptocurrencies are decentralized with no central authority. The market operates 24/7/365 with high volatility.

### Key Characteristics

```
Decentralized:   No central authority (mostly)
24/7 trading:    Never closes, no weekends
Volatile:        10-20% daily moves not uncommon
Fragmented:      Many exchanges, price variations
Custody:         Self-custody possible (not with stocks)
```

### Major Cryptocurrencies

| Asset        | Ticker | Category        | Characteristics                           |
| ------------ | ------ | --------------- | ----------------------------------------- |
| **Bitcoin**  | BTC    | Store of value  | Digital gold, most liquid, ~50% of market |
| **Ethereum** | ETH    | Smart contracts | DeFi platform, programmable money         |
| **Tether**   | USDT   | Stablecoin      | Pegged to $1, trading pair liquidity      |
| **BNB**      | BNB    | Exchange token  | Binance ecosystem utility                 |
| **Solana**   | SOL    | Alt L1          | High speed, low fees, growing DeFi        |
| **XRP**      | XRP    | Payments        | Cross-border transfers                    |

### Trading Venues

| Type                    | Examples                        | Characteristics                    |
| ----------------------- | ------------------------------- | ---------------------------------- |
| **CEX** (Centralized)   | Binance, Coinbase, Kraken       | Order book, KYC required, insured  |
| **DEX** (Decentralized) | Uniswap, dYdX, GMX              | On-chain, no KYC, self-custody     |
| **Derivatives**         | Binance Futures, Deribit, Bybit | Perpetuals, options, high leverage |
| **Traditional**         | CME Futures, Alpaca             | Regulated, institutional           |

### Perpetual Futures

```
Unique to crypto - futures with no expiration

Funding rate mechanism:
  Every 8 hours, longs and shorts exchange payments

  Positive funding: Price > Spot → Longs pay shorts
  Negative funding: Price < Spot → Shorts pay longs

This keeps perpetual price close to spot

Leverage: Up to 125x on some platforms (extremely risky)
```

```
FUNDING RATE ARBITRAGE (Delta-Neutral Strategy)

When funding rate is POSITIVE (longs pay shorts):

  ┌──────────────────┐     ┌──────────────────┐
  │    SPOT BUY      │     │  PERP SHORT      │
  │                  │     │                  │
  │   Long 1 BTC     │     │   Short 1 BTC    │
  │   @ $50,000      │     │   @ $50,200      │
  └──────────────────┘     └──────────────────┘
           │                        │
           └────────┬───────────────┘
                    │
                    ▼
           ┌────────────────┐
           │  DELTA NEUTRAL │
           │                │
           │  Price moves   │
           │  cancel out    │
           │                │
           │  Profit from:  │
           │  • Funding     │
           │    payments    │
           │  • Premium     │
           │    decay       │
           └────────────────┘

  Collect ~0.01-0.1% every 8 hours = 10-40% APY
  (when funding is elevated)
```

### Crypto-Specific Concepts

```
Gas fees:      Transaction costs on-chain (ETH network)
Slippage:      Price impact when trading on DEXes
MEV:           Miner/validator extractable value (front-running)
Wallet types:  Hot (online, convenient), Cold (offline, secure)
On-chain data: Whale movements, exchange flows, holder distribution
```

### How It's Traded

```
Spot trading:     Direct ownership of crypto
Margin trading:   Borrow to increase position size
Perpetual swaps:  Leverage without owning underlying
Options:          Deribit dominates crypto options

Order types similar to traditional markets plus:
  - Post-only: Only adds liquidity (maker orders)
  - Reduce-only: Can only decrease position
  - Trigger orders: More sophisticated stop types
```

### Best Strategies for Crypto

| Strategy             | Why It Works                               | Notes                         |
| -------------------- | ------------------------------------------ | ----------------------------- |
| **Trend Following**  | Strong trends due to speculation cycles    | Bull/bear cycles pronounced   |
| **Momentum**         | FOMO and capitulation create momentum      | Works during trending markets |
| **Arbitrage**        | Price discrepancies across exchanges       | Requires fast execution       |
| **Funding Rate Arb** | Capture funding payments                   | Delta-neutral positions       |
| **DeFi Yield**       | Liquidity provision, lending               | Smart contract risk           |
| **Grid Trading**     | Volatility creates many fill opportunities | Range-bound periods           |

### Considerations

- Extreme volatility = opportunity + significant risk
- Exchange risk: hacks, insolvency (FTX), frozen withdrawals
- Liquidity varies hugely between assets (BTC liquid, altcoins thin)
- API rate limits stricter than traditional finance
- Tax reporting complex (every trade is taxable event)
- 24/7 means constant monitoring or automation required
- Regulatory uncertainty in many jurisdictions

---

## 6. Bonds (Fixed Income)

### What It Is

Bonds are debt instruments where the issuer (government, corporation) owes the holder principal plus interest payments. Bonds are essentially loans you make to the issuer in exchange for regular interest (coupon) and return of principal at maturity.

### Key Characteristics

```
Face value:     Principal amount (typically $1,000)
Coupon:         Interest rate paid (annually or semi-annually)
Maturity:       Date when principal is repaid
Yield:          Return based on current price
Price:          Trades above (premium) or below (discount) face value
```

### Types of Bonds

| Type             | Issuer                 | Risk Level         | Examples                    |
| ---------------- | ---------------------- | ------------------ | --------------------------- |
| **Treasury**     | US Government          | Lowest (risk-free) | T-Bills, T-Notes, T-Bonds   |
| **Municipal**    | State/Local govt       | Low                | Munis (often tax-free)      |
| **Corporate IG** | Investment grade corps | Medium             | Apple, Microsoft bonds      |
| **Corporate HY** | Below investment grade | High               | "Junk bonds", higher yields |
| **Sovereign**    | Foreign governments    | Varies             | German Bunds, UK Gilts      |
| **TIPS**         | US Government          | Low                | Inflation-protected         |

### Treasury Securities

| Type       | Maturity    | Coupon             | Notes                   |
| ---------- | ----------- | ------------------ | ----------------------- |
| **T-Bill** | ≤ 1 year    | Zero (discount)    | Money market instrument |
| **T-Note** | 2-10 years  | Semi-annual        | Most actively traded    |
| **T-Bond** | 20-30 years | Semi-annual        | Longest duration        |
| **TIPS**   | Various     | Inflation-adjusted | Real yield              |

### Bond Math

```
Price and Yield: Inverse relationship
  Interest rates ↑ → Bond prices ↓
  Interest rates ↓ → Bond prices ↑

Yield to Maturity (YTM):
  Total return if held to maturity
  Accounts for coupon + price change

Duration:
  Price sensitivity to interest rate changes
  Higher duration = more volatile
  10-year duration means ~10% price change per 1% rate change

Convexity:
  Rate of change of duration
  Higher convexity = more upside, less downside
```

### Yield Curve

```
YIELD CURVE SHAPES

Normal (healthy economy):     Inverted (recession signal):

Yield                         Yield
  │        ___________          │  ___________
  │    ___/                     │              \___
  │  _/                         │                  \_
  │_/                           │                    \_
  └─────────────────────▶       └─────────────────────▶
     Short    Long                 Short    Long
     (2Y)    (30Y)                 (2Y)    (30Y)

2s10s spread = 10Y yield - 2Y yield
  Positive: Normal curve
  Negative: Inverted curve (often precedes recession)
```

### How It's Traded

```
Primary market:    Treasury auctions (Treasury Direct)
Secondary market:  OTC dealer market (less transparent)
Bond ETFs:         TLT (20Y+), IEF (7-10Y), BND (total), LQD (corp)
Futures:           ZN (10Y Note), ZB (30Y Bond), ZF (5Y)
```

### Best Strategies for Bonds

| Strategy             | Description                                | Time Horizon    |
| -------------------- | ------------------------------------------ | --------------- |
| **Duration Trading** | Bet on interest rate direction             | Weeks to months |
| **Curve Trading**    | Trade steepening/flattening of yield curve | Weeks to months |
| **Credit Spread**    | Long IG, short HY (or vice versa)          | Months          |
| **Roll Down**        | Profit from natural yield curve roll       | Months          |
| **Relative Value**   | Similar bonds trading at different yields  | Days to weeks   |
| **Macro**            | Central bank policy bets via futures       | Event-driven    |

### Considerations

- Less liquid than equities (except Treasury futures)
- OTC market means less price transparency
- Interest rate risk dominates returns
- Credit risk for corporate bonds (defaults)
- Futures (ZN, ZB) are more liquid than cash bonds
- Complex for retail (institutional-dominated market)

---

## 7. ETFs (Exchange-Traded Funds)

### What It Is

ETFs are funds that hold a basket of assets (stocks, bonds, commodities) but trade on exchanges like individual stocks. They combine the diversification of mutual funds with the tradability of stocks. ETFs have become the dominant vehicle for passive investing.

### Key Characteristics

```
Diversification: Hold basket of assets in one ticker
Transparency:    Holdings disclosed daily
Liquidity:       Trade intraday like stocks
Cost:            Low expense ratios (0.03% to 0.75%)
Tax efficient:   In-kind creation/redemption minimizes gains
```

### ETF Types

| Type              | Tracks               | Examples           | Use Case                   |
| ----------------- | -------------------- | ------------------ | -------------------------- |
| **Index**         | Market indices       | SPY, QQQ, IWM, VTI | Broad market exposure      |
| **Sector**        | Industry sectors     | XLF, XLE, XLK, XLV | Sector bets                |
| **Bond**          | Fixed income         | TLT, BND, LQD, HYG | Fixed income exposure      |
| **Commodity**     | Physical commodities | GLD, SLV, USO      | Commodity exposure         |
| **International** | Foreign markets      | EFA, EEM, VEU      | Geographic diversification |
| **Leveraged**     | 2x/3x daily exposure | TQQQ, SOXL, UPRO   | Short-term speculation     |
| **Inverse**       | Short exposure       | SH, SQQQ, SPXU     | Hedging, bearish bets      |
| **Thematic**      | Specific themes      | ARKK, HACK, BOTZ   | Trend investing            |

### Creation/Redemption

```
ETF ARBITRAGE MECHANISM

┌─────────────────────────────────────────────────────────────┐
│                    ETF at PREMIUM                           │
│                  (Price > NAV)                              │
│                                                             │
│   ┌───────────┐        ┌──────────┐        ┌──────────┐     │
│   │ Underlying│  ───▶  │   ETF    │  ───▶  │  Market  │     │
│   │  Stocks   │  buy   │  Issuer  │ create │  (sell)  │     │
│   └───────────┘        └──────────┘        └──────────┘     │
│                              │                              │
│                        AP gets shares                       │
│                        Sells at premium                     │
│                        → Price falls to NAV                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    ETF at DISCOUNT                          │
│                  (Price < NAV)                              │
│                                                             │
│   ┌──────────┐        ┌──────────┐        ┌──────────┐      │
│   │  Market  │  ───▶  │   ETF    │  ───▶  │Underlying│      │
│   │  (buy)   │  cheap │  Issuer  │ redeem │  (sell)  │      │
│   └──────────┘        └──────────┘        └──────────┘      │
│                              │                              │
│                        AP redeems shares                    │
│                        Gets underlying basket               │
│                        → Price rises to NAV                 │
└─────────────────────────────────────────────────────────────┘
```

### Leveraged ETF Mechanics

```
Daily reset creates volatility decay over time:

Example (2x leveraged in choppy market):
  Day 1: Index +10% → ETF +20% (100 → 120)
  Day 2: Index -10% → ETF -20% (120 → 96)

  Index: 100 → 99 (-1%)
  ETF:   100 → 96 (-4%)  ← Decay!

Why: Leverage is reset daily to 2x
     Compounding works against you in volatile markets

Only suitable for short-term trading (hours to days)
```

### How It's Traded

```
Same as stocks:
  Market, limit, stop orders
  Options available on major ETFs
  Trade during market hours (some have extended hours)

Spread consideration:
  SPY: Usually $0.01 spread (extremely liquid)
  Niche ETFs: Can have $0.10+ spreads

Settlement: T+1
```

### Best Strategies for ETFs

| Strategy               | Description                           | Examples         |
| ---------------------- | ------------------------------------- | ---------------- |
| **Sector Rotation**    | Rotate between sectors based on cycle | XLF → XLE → XLK  |
| **Risk Parity**        | Balance risk across asset classes     | SPY, TLT, GLD    |
| **Pairs Trading**      | Long one ETF, short related ETF       | SPY vs IWM       |
| **Leveraged Momentum** | Use TQQQ/SQQQ for short-term momentum | Day trading only |
| **ETF Arbitrage**      | ETF vs underlying basket              | Requires speed   |
| **Dividend Capture**   | Buy before ex-date, sell after        | High-yield ETFs  |

### Considerations

- Extremely liquid for major ETFs (SPY, QQQ)
- Expense ratios eat into returns (check before buying)
- Leveraged ETFs decay in volatile markets (not for holding)
- Some ETFs have tracking error vs their index
- Premium/discount can be significant for illiquid or international ETFs
- Dividend treatment varies (qualified vs non-qualified)

---

## 8. CFDs (Contracts for Difference)

### What It Is

CFDs are derivative contracts where you exchange the difference in price from open to close, without owning the underlying asset. They're pure price speculation instruments. Note: **CFDs are not available to US residents** (banned by regulation).

### Key Characteristics

```
No ownership:   Pure price speculation
Leverage:       High (5:1 to 30:1 typical)
Both ways:      Easy to go long or short
No expiration:  Hold indefinitely (but overnight costs)
Fractional:     Trade any position size
```

### How CFDs Work

```
Open position:  Buy 100 CFDs of Stock X at $50
Close position: Sell 100 CFDs at $55

Profit = (55 - 50) × 100 = $500
  (minus spreads and overnight fees)

No shares ever owned or borrowed
No stamp duty (UK)
```

### CFD Costs

| Cost                    | Description                           | Typical Amount |
| ----------------------- | ------------------------------------- | -------------- |
| **Spread**              | Bid-ask difference (built into price) | 0.1-2%         |
| **Commission**          | Per-trade fee (some brokers)          | $0-10          |
| **Overnight financing** | Daily fee for holding positions       | 2-4% annually  |
| **Currency conversion** | If trading foreign assets             | 0.5%           |

### Overnight Financing

```
Long position:  Pay (benchmark rate + broker markup)
Short position: Receive (benchmark rate - markup)
                Often net negative for shorts too

Example:
  $10,000 position, 4% annual overnight rate
  Daily cost: $10,000 × 0.04 / 365 = $1.10 per day

Adds up quickly for longer holds
```

### Regulatory Status

```
Banned:        USA (not available to US residents)
Available:     UK, Europe, Australia, Asia
Regulated by:  FCA (UK), ASIC (Australia), CySEC (Cyprus)

ESMA Leverage Caps (EU retail clients):
  Major FX:           30:1
  Minor FX, Gold:     20:1
  Commodities:        10:1
  Individual stocks:  5:1
  Crypto:             2:1
```

### How It's Traded

```
Brokers:    IG, Plus500, CMC Markets, eToro
Markets:    Stocks, indices, forex, commodities, crypto
Execution:  Instant (market maker model)
Pricing:    Mirrors underlying with spread added
```

### Best Strategies for CFDs

| Strategy          | Why It Works                    | Notes                    |
| ----------------- | ------------------------------- | ------------------------ |
| **Day Trading**   | Avoid overnight costs           | Close positions same day |
| **Short Selling** | Easy to short without borrowing | Index shorts popular     |
| **Hedging**       | Offset portfolio risk           | Quick, flexible          |
| **Swing Trading** | Short-term trends (2-5 days)    | Watch overnight costs    |

### Considerations

- **Not available in USA** (important for US traders)
- Overnight costs make long-term holding expensive
- Spreads can widen significantly during news/volatility
- Counterparty risk (broker is counterparty to your trade)
- No ownership = no dividends (adjustment made instead)
- Easy to over-leverage and lose more than deposited

---

## 9. Commodities

### What It Is

Commodities are raw materials and primary products traded on exchanges. They include energy (oil, gas), metals (gold, copper), and agricultural products (corn, wheat). Commodity prices are driven by supply and demand fundamentals plus speculation.

### Categories

**Energy:**
| Commodity | Symbol | Exchange | Contract Size | Characteristics |
|-----------|--------|----------|---------------|-----------------|
| Crude Oil (WTI) | CL | NYMEX | 1,000 barrels | Most traded commodity |
| Brent Crude | BZ | ICE | 1,000 barrels | International benchmark |
| Natural Gas | NG | NYMEX | 10,000 MMBtu | Seasonal, volatile |
| Gasoline | RB | NYMEX | 42,000 gallons | Refining spreads |

**Metals:**
| Commodity | Symbol | Exchange | Contract Size | Characteristics |
|-----------|--------|----------|---------------|-----------------|
| Gold | GC | COMEX | 100 troy oz | Safe haven, inflation hedge |
| Silver | SI | COMEX | 5,000 troy oz | Industrial + precious |
| Copper | HG | COMEX | 25,000 lbs | Economic indicator |
| Platinum | PL | NYMEX | 50 troy oz | Auto catalyst demand |

**Agriculture:**
| Commodity | Symbol | Exchange | Contract Size | Characteristics |
|-----------|--------|----------|---------------|-----------------|
| Corn | ZC | CBOT | 5,000 bushels | Largest ag market |
| Soybeans | ZS | CBOT | 5,000 bushels | China demand driven |
| Wheat | ZW | CBOT | 5,000 bushels | Weather sensitive |
| Coffee | KC | ICE | 37,500 lbs | Highly volatile |
| Sugar | SB | ICE | 112,000 lbs | Brazil production key |

### Price Drivers

```
Supply factors:
  - Weather (agriculture): Droughts, floods, frost
  - Geopolitics (energy): OPEC, sanctions, wars
  - Mining output (metals): Strikes, discoveries
  - Inventory levels: Storage reports (EIA, USDA)

Demand factors:
  - Economic growth (industrial metals, energy)
  - USD strength (commodities priced in USD)
  - Seasonal patterns (heating oil winter, gasoline summer)
  - Speculation and fund flows
```

### Seasonal Patterns

```
COMMODITY SEASONAL TENDENCIES

        Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec
        ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ───

Natural │▓▓▓│   │   │   │   │   │   │   │   │   │▓▓▓│▓▓▓│
Gas     │HI │   │LOW│LOW│   │   │   │   │   │   │   │HI │
        │   │   │   │   │   │   │   │   │   │   │   │   │
────────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┤
        │   │   │   │   │   │   │   │   │   │   │   │   │
Gasoline│   │   │   │▓▓▓│▓▓▓│▓▓▓│▓▓▓│   │   │   │   │   │
        │   │   │   │UP │UP │HI │HI │   │   │   │   │   │
────────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┤
        │   │   │   │   │   │   │   │   │   │   │   │   │
Grains  │   │   │   │   │   │▓▓▓│▓▓▓│▓▓▓│▓▓▓│▓▓▓│   │   │
(Corn)  │   │Plt│Plt│   │   │Gro│Gro│Hvt│Hvt│Hvt│   │   │
────────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┤
        │   │   │   │   │   │   │   │   │   │   │   │   │
Gold    │▓▓▓│▓▓▓│   │   │   │   │   │   │▓▓▓│   │   │   │
        │UP │UP │   │   │   │   │   │   │UP │   │   │   │

HI=High demand  LOW=Low demand  UP=Typically rises
Plt=Planting    Gro=Growing     Hvt=Harvest
```

### Contango and Backwardation

```
FUTURES TERM STRUCTURE

CONTANGO (Futures > Spot)             BACKWARDATION (Futures < Spot)

Price                                 Price
  │              ● Jun                  │  ● Spot
  │          ● May                      │      \
  │      ● Apr                          │   ● Mar
  │  ● Mar                              │       \
  │● Spot                               │     ● Apr
  │                                     │         \
  └────────────────▶                    └──────────●─Jun──▶
      Time to expiry                        Time to expiry

Rolling long = Loss                   Rolling long = Profit
(sell low, buy high)                  (sell high, buy low)

Contango = Normal for storable commodities (cost of carry)
Backwardation = Supply shortage or high convenience yield
```

### How It's Traded

```
Futures:      Direct exposure, most liquid
              Physical delivery possible (close before expiry!)

ETFs:         GLD (gold), SLV (silver), USO (oil), DBA (agriculture)
              Roll costs embedded (contango drag)

Stocks:       Producers (XOM, FCX, NEM, BHP)
              Leverage to commodity prices

Options:      On futures contracts
              Used for hedging and speculation
```

### Best Strategies for Commodities

| Strategy            | Why It Works                               | Examples               |
| ------------------- | ------------------------------------------ | ---------------------- |
| **Trend Following** | Commodities have strong, persistent trends | Managed futures        |
| **Seasonal**        | Predictable supply/demand patterns         | Natural gas winter     |
| **Spread Trading**  | Calendar spreads (front vs back month)     | Crude oil rolls        |
| **Macro**           | Economic cycle positioning                 | Copper as growth proxy |
| **Weather Trading** | Agricultural supply impacts                | Grain futures          |
| **Roll Yield**      | Capture backwardation premium              | Long commodity indices |

### Considerations

- Supply/demand fundamentals matter more than technicals
- Seasonal patterns often strong and tradeable
- Roll costs significant for ETFs and long futures positions
- Physical delivery risk if holding to expiration
- Weather and geopolitical events cause gaps
- Large contract sizes require significant capital

---

## 10. Swaps and OTC Derivatives

### What It Is

Swaps are customized derivative contracts traded directly between parties (not on exchanges). They're primarily institutional instruments used for hedging large exposures. Most retail traders won't trade these directly but should understand them as they affect markets.

### Interest Rate Swaps

```
Exchange fixed rate payments for floating rate payments

Example:
  Party A pays: 3% fixed annually
  Party B pays: SOFR + 0.5% floating

  Notional: $100 million (not exchanged, just for calculation)
  Tenor: 5 years

Use case: Company with floating-rate debt wants fixed payments
          Bank wants floating exposure
```

### Credit Default Swaps (CDS)

```
Insurance against bond default

Buyer pays:  Premium (spread) quarterly
Seller pays: Face value if default occurs

CDS Spread = Market's view of default risk
  - Higher spread = higher perceived risk
  - Watched as credit health indicator

Example:
  Company XYZ 5-year CDS: 200 basis points
  Means: Pay 2% annually for default protection
```

### Total Return Swaps

```
Exchange total return of an asset for fixed payment

Party A receives: Total return on S&P 500 (dividends + price change)
Party A pays:     SOFR + spread

Use cases:
  - Gain exposure without owning asset
  - Leverage without margin requirements
  - Avoid ownership disclosure requirements
```

### Equity Swaps

```
Exchange returns of different equity exposures

Example:
  Party A receives: Return on Tech Sector
  Party B receives: Return on Energy Sector

Used for sector rotation without trading actual stocks
```

### How They're Traded

```
Market:      OTC (over-the-counter), bilateral
Participants: Banks, hedge funds, corporations
Clearing:    Central clearing required for many swaps (post-2008 reforms)
Documentation: ISDA Master Agreement
Size:        Typically $10M+ notional minimum
```

### Considerations

- Mostly institutional market (retail has limited access)
- Bilateral credit risk (counterparty may default)
- Less transparency than exchange-traded
- Size and terms customizable
- Central clearing reduces but doesn't eliminate counterparty risk
- Understanding swaps helps understand institutional positioning

---

## Asset Class Selection Guide

### By Trading Style

| Style                | Best Assets                   | Why                                     |
| -------------------- | ----------------------------- | --------------------------------------- |
| **Scalping**         | Futures, Forex                | Tightest spreads, fastest execution     |
| **Day Trading**      | Futures, Forex, liquid stocks | High liquidity, no overnight risk       |
| **Swing Trading**    | Stocks, ETFs, Forex           | Trends develop over days, manageable    |
| **Position Trading** | Stocks, ETFs, Bonds           | Longer timeframes, fundamentals matter  |
| **Arbitrage**        | ETFs, Futures, Crypto         | Price discrepancies exist across venues |

### By Capital Requirements

| Capital               | Suitable Assets                         | Notes                           |
| --------------------- | --------------------------------------- | ------------------------------- |
| **< $1,000**          | Crypto (fractional), Forex (micro lots) | Start small, learn mechanics    |
| **$1,000 - $10,000**  | Stocks, ETFs, Forex, Crypto             | Build experience                |
| **$10,000 - $25,000** | Add: Options (defined risk)             | More strategies available       |
| **$25,000+**          | All assets (PDT rule cleared)           | Full flexibility for US traders |
| **$50,000+**          | Add: Futures comfortably                | Proper margin for futures       |

### By Market Hours Preference

| Preference            | Assets                | Sessions                         |
| --------------------- | --------------------- | -------------------------------- |
| **US hours only**     | Stocks, ETFs, Options | 9:30am-4pm ET                    |
| **Extended hours**    | Futures, Forex        | Near 24h (Mon-Fri)               |
| **24/7**              | Crypto                | Anytime including weekends       |
| **Specific sessions** | Forex                 | Pick London, NY, or Asia overlap |

### By Risk Tolerance

| Risk Level       | Suitable Assets                   | Max Leverage |
| ---------------- | --------------------------------- | ------------ |
| **Conservative** | Bonds, Bond ETFs, dividend stocks | 1-2x         |
| **Moderate**     | Index ETFs, large-cap stocks      | 2-4x         |
| **Aggressive**   | Options, Futures, Forex           | 10-20x       |
| **Speculative**  | Crypto, leveraged ETFs            | 20x+         |

---

## Key Takeaways

1. **Start with what you understand**: Stocks and ETFs are most intuitive for beginners
2. **Match asset to strategy**: Trend following works better in futures/forex; mean reversion in stocks
3. **Respect leverage**: Higher leverage = faster gains AND losses
4. **Consider costs**: Overnight financing, roll costs, and spreads eat into returns
5. **Know your hours**: 24/7 markets require automation or accepting overnight risk
6. **Diversify across assets**: Different asset classes have low correlation
7. **Paper trade first**: Every asset class has quirks you need to experience

---

_See [Algorithmic Trading Strategies](algorithmic-trading-strategies.md) for detailed strategy implementations._
