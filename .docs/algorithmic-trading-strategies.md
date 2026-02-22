# Comprehensive Guide to Algorithmic Trading Strategies

A detailed reference covering all well-known automated trading strategies, their mechanics, primitives, and implementation considerations.

## Introduction: What is Algorithmic Trading?

Algorithmic trading (also called "algo trading" or "automated trading") is the process of using computer programs to execute trades based on predefined rules and mathematical models. Instead of a human manually clicking "buy" or "sell," the algorithm monitors market data, identifies opportunities, and executes trades automatically—often in fractions of a second.

### Why Use Algorithmic Trading?

**Speed and Consistency**: Algorithms can react to market changes in milliseconds, far faster than any human. They also execute the same strategy consistently, without emotional interference like fear or greed.

**Backtesting Capability**: Before risking real money, you can test your strategy against years of historical data to see how it would have performed. This helps identify flaws and optimize parameters.

**Scalability**: An algorithm can monitor hundreds of instruments simultaneously, something impossible for a human trader.

**Removing Emotional Bias**: One of the biggest challenges in trading is sticking to your plan when money is on the line. Algorithms don't get nervous, don't second-guess themselves, and don't "revenge trade" after a loss.

### The Reality Check

However, algorithmic trading is not a guaranteed path to riches. Markets are highly competitive—you're trading against hedge funds with PhD quants, massive computing resources, and decades of research. Most retail algorithmic strategies underperform simple buy-and-hold approaches after accounting for transaction costs.

This guide provides a foundation of strategies and concepts. Success requires not just understanding these strategies, but also:
- Rigorous backtesting with realistic assumptions
- Proper risk management
- Understanding that past performance doesn't guarantee future results
- Continuous adaptation as markets evolve

---

## Visual System Overview

### Overall Trading System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ALGORITHMIC TRADING SYSTEM                   │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│  DATA FEEDS   │       │   STRATEGY    │       │    BROKER     │
│               │       │    ENGINE     │       │     API       │
│ • Price/OHLCV │──────▶│               │──────▶│               │
│ • Order Book  │       │ • Signals     │       │ • Orders      │
│ • News/Events │       │ • Position    │       │ • Fills       │
│ • Indicators  │       │ • Risk Mgmt   │       │ • Positions   │
└───────────────┘       └───────────────┘       └───────────────┘
                                │
                                ▼
                ┌───────────────────────────────┐
                │        RISK MANAGEMENT        │
                │                               │
                │  • Position Sizing            │
                │  • Stop Losses                │
                │  • Max Drawdown Limits        │
                │  • Correlation Checks         │
                └───────────────────────────────┘
                                │
                                ▼
                ┌───────────────────────────────┐
                │      MONITORING & LOGS        │
                │                               │
                │  • P&L Tracking               │
                │  • Trade Journal              │
                │  • Performance Metrics        │
                │  • Alerts                     │
                └───────────────────────────────┘
```

### Strategy Selection Flowchart

```
                        ┌─────────────────┐
                        │  MARKET STATE?  │
                        └────────┬────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
     ┌──────────┐         ┌──────────┐         ┌──────────┐
     │ TRENDING │         │  RANGING │         │ VOLATILE │
     └────┬─────┘         └────┬─────┘         └────┬─────┘
          │                    │                    │
          ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ TREND FOLLOWING  │  │  MEAN REVERSION  │  │    BREAKOUT /    │
│                  │  │                  │  │    STRADDLES     │
│ • MA Crossover   │  │ • Bollinger Band │  │                  │
│ • MACD           │  │ • RSI Reversal   │  │ • Channel Break  │
│ • Turtle/Donch   │  │ • Pairs Trading  │  │ • Long Straddle  │
│ • Supertrend     │  │ • Z-Score        │  │ • Gamma Scalp    │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### Trade Lifecycle

```
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│ SIGNAL │───▶│  SIZE  │───▶│ ENTRY  │───▶│ MANAGE │───▶│  EXIT  │
└────────┘    └────────┘    └────────┘    └────────┘    └────────┘
     │             │             │             │             │
     ▼             ▼             ▼             ▼             ▼
 Indicator    Position      Order Type     Stop Loss    Target Hit
 Crossover    Sizing        Selection      Trailing       OR
 Pattern      Risk %        Limit/Mkt      Scaling      Stop Hit
 Breakout     Kelly         Timing         Add/Reduce   Time Exit
```

---

## Table of Contents

1. [Asset Classes](#asset-classes)
2. [Fundamental Primitives](#fundamental-primitives)
3. [Trend Following Strategies](#trend-following-strategies)
4. [Mean Reversion Strategies](#mean-reversion-strategies)
5. [Momentum Strategies](#momentum-strategies)
6. [Arbitrage Strategies](#arbitrage-strategies)
7. [Market Making Strategies](#market-making-strategies)
8. [Statistical & Quantitative Strategies](#statistical--quantitative-strategies)
9. [Event-Driven Strategies](#event-driven-strategies)
10. [Sentiment-Based Strategies](#sentiment-based-strategies)
11. [Seasonal & Calendar Strategies](#seasonal--calendar-strategies)
12. [Volume-Based Strategies](#volume-based-strategies)
13. [Machine Learning Strategies](#machine-learning-strategies)
14. [Options-Based Strategies](#options-based-strategies)
15. [Execution Algorithms](#execution-algorithms)
16. [Risk Management Framework](#risk-management-framework)
17. [Backtesting Considerations](#backtesting-considerations)

---

## Asset Classes

A comprehensive overview of all tradeable asset types, their characteristics, and how they differ from each other.

### Why Asset Class Matters

Choosing the right asset class is one of the most important decisions in algorithmic trading. Each asset class has unique characteristics that make certain strategies more or less viable:

**Liquidity** determines how easily you can enter and exit positions without moving the price against yourself. High-frequency strategies require extremely liquid markets, while longer-term strategies can tolerate less liquidity.

**Volatility** affects how quickly prices move. Higher volatility means more opportunity for profit—but also more risk. Some strategies (like mean reversion) work better in volatile markets, while others (like market making) prefer stability.

**Leverage** amplifies both gains and losses. A 2x leveraged position doubles your profits when you're right, but also doubles your losses when you're wrong. Higher leverage requires more careful risk management.

**Trading Hours** determine when your algorithm needs to run. Crypto markets never close, while stock markets have specific hours. Extended trading sessions (pre-market, after-hours) typically have lower liquidity and wider spreads.

**Settlement** refers to when ownership actually transfers. In stocks, you don't officially own shares until T+1 (one business day after the trade). This affects strategies that depend on dividend capture or corporate actions.

### Overview Comparison

| Asset Class | Liquidity | Volatility | Leverage | Trading Hours | Settlement |
|-------------|-----------|------------|----------|---------------|------------|
| **Equities** | High (large caps) | Medium | 2-4x retail | Exchange hours | T+1 |
| **Options** | Medium | High | Built-in | Exchange hours | T+1 |
| **Futures** | Very High | Medium-High | 10-20x | Near 24h | Daily mark |
| **Forex** | Highest | Low-Medium | 50-500x | 24h Sun-Fri | T+2 |
| **Crypto** | Medium | Very High | 1-125x | 24/7 | Instant-1h |
| **Bonds** | Low-Medium | Low | 10-20x | Exchange hours | T+1 |
| **ETFs** | High | Varies | 2-4x retail | Exchange hours | T+1 |
| **CFDs** | High | Varies | 5-30x | Near 24h | No delivery |
| **Commodities** | Medium | High | 10-20x | Near 24h | Varies |

---

### 1. Equities (Stocks)

**What it is**: Ownership shares in publicly traded companies.

When you buy a stock, you're literally buying a tiny piece of that company. If Apple has 16 billion shares outstanding and you buy 100 shares, you own 100/16,000,000,000 = 0.000000625% of Apple. This entitles you to a proportional share of dividends (if any) and voting rights on major corporate decisions.

Stocks are the most common asset class for retail algorithmic traders because they're relatively straightforward to understand, have abundant free/cheap data available, and can be traded through many broker APIs like Alpaca.

**Characteristics**:
```
Ownership:     Fractional ownership of company
Dividends:     May pay quarterly dividends
Voting:        Common shares have voting rights
Price driver:  Company earnings, growth, sentiment
```

**Types of Equities**:
| Type | Description | Example |
|------|-------------|---------|
| **Common Stock** | Standard ownership with voting rights | AAPL, GOOGL |
| **Preferred Stock** | Fixed dividend, no voting, priority in liquidation | BAC-PL |
| **ADRs** | Foreign stocks traded on US exchanges | BABA, TSM |
| **REITs** | Real estate investment trusts | VNQ, SPG |
| **SPACs** | Special purpose acquisition companies | Varies |

**Market Structure**:
```
Exchanges:     NYSE, NASDAQ, LSE, TSE, etc.
Hours:         9:30 AM - 4:00 PM ET (US)
Pre-market:    4:00 AM - 9:30 AM ET
After-hours:   4:00 PM - 8:00 PM ET
Tick size:     $0.01 (penny increments)
Settlement:    T+1 (trade date + 1 business day)
```

**Key Metrics**:
- Market Cap = Share Price × Shares Outstanding
- P/E Ratio = Price / Earnings Per Share
- EPS = Net Income / Shares Outstanding
- Dividend Yield = Annual Dividend / Price

**Data Available**:
```
Level 1:       Bid, Ask, Last, Volume
Level 2:       Full order book depth
Time & Sales:  Every executed trade
Fundamentals:  Earnings, revenue, ratios
Corporate:     Dividends, splits, M&A
```

**Algo Trading Considerations**:
- High liquidity in large caps, thin in small caps
- Extended hours have wider spreads
- Corporate actions (splits, dividends) affect data
- Short selling requires locating shares

---

### 2. Options

**What it is**: Contracts giving the right (not obligation) to buy/sell an asset at a specific price by a specific date.

Think of an option like a coupon or voucher. Imagine you're interested in buying a house that costs $500,000 today. You're not ready to buy yet, but you're worried prices will rise. The homeowner offers you a deal: pay $10,000 now, and you'll have the right (but not obligation) to buy the house at $500,000 anytime in the next year.

If house prices rise to $600,000, your coupon is worth $100,000 (you can buy at $500k and immediately sell at $600k). If prices fall to $400,000, you simply don't use the coupon—you let it expire and only lose your $10,000 "premium."

This is exactly how options work. A **call option** gives you the right to buy at a set price (the "strike price"), while a **put option** gives you the right to sell.

Options are powerful but complex. Their prices depend not just on the underlying stock price, but also on time remaining until expiration, expected volatility, and interest rates. The mathematics behind options pricing (Black-Scholes model, the Greeks) is a field unto itself.

**Characteristics**:
```
Right to buy:   Call option
Right to sell:  Put option
Strike price:   Price at which option can be exercised
Expiration:     Date when option expires
Premium:        Price paid for the option
```

**Option Types**:
| Type | Exercise | Common In |
|------|----------|-----------|
| **American** | Any time before expiration | US equities |
| **European** | Only at expiration | Index options, FX |
| **Bermudan** | Specific dates | Exotic products |

**Key Concepts**:
```
Moneyness:
  ITM (In The Money):   Call: Stock > Strike, Put: Stock < Strike
  ATM (At The Money):   Stock ≈ Strike
  OTM (Out of Money):   Call: Stock < Strike, Put: Stock > Strike

Intrinsic Value:  max(0, Stock - Strike) for calls
Time Value:       Premium - Intrinsic Value
```

**The Greeks** (Understanding These is Essential for Options Trading):

The "Greeks" measure how an option's price changes in response to different factors. They're called Greeks because they're represented by Greek letters:

| Greek | Measures | Range | Plain English Explanation |
|-------|----------|-------|--------------------------|
| **Delta (Δ)** | Price sensitivity to underlying | -1 to +1 | If delta is 0.5, the option gains $0.50 for every $1 the stock rises. A delta of 0.5 roughly means 50% chance of ending in the money. |
| **Gamma (Γ)** | Rate of change of delta | 0 to ∞ | How quickly delta changes. High gamma means delta can swing wildly—exciting near expiration when options are at-the-money. |
| **Theta (Θ)** | Time decay per day | Usually negative | Options lose value every day as expiration approaches. Theta tells you how much. If theta is -0.05, the option loses $5 per day (for 100 shares). |
| **Vega (ν)** | Sensitivity to volatility | 0 to ∞ | If the market expects more volatility, options become more valuable (bigger potential moves). Vega measures this sensitivity. |
| **Rho (ρ)** | Sensitivity to interest rates | Varies | Usually small, but matters for long-dated options. Higher rates favor calls, hurt puts. |

**Practical tip**: Most traders focus on delta (direction), theta (time decay eating your position), and vega (volatility changes) in that order. Gamma becomes critical when trading near expiration or at-the-money.

```
THE GREEKS: WHAT AFFECTS OPTION PRICE?

┌────────────────────────────────────────────────────────────┐
│                     OPTION PRICE                           │
│                          │                                 │
│    ┌─────────┬───────────┼───────────┬─────────┐           │
│    │         │           │           │         │           │
│    ▼         ▼           ▼           ▼         ▼           │
│ ┌──────┐ ┌──────┐   ┌────────┐  ┌──────┐  ┌──────┐         │
│ │Delta │ │Gamma │   │ Theta  │  │ Vega │  │ Rho  │         │
│ │  Δ   │ │  Γ   │   │   Θ    │  │  ν   │  │  ρ   │         │
│ └──┬───┘ └──┬───┘   └───┬────┘  └──┬───┘  └──┬───┘         │
│    │        │           │          │         │             │
│    ▼        ▼           ▼          ▼         ▼             │
│  Stock    Delta       Time      Implied  Interest          │
│  Price    Change      Decay      Vol      Rates            │
│                                                            │
│  Most ◄───────────────────────────────────────► Least      │
│  Important                                     Important   │
└────────────────────────────────────────────────────────────┘
```

**Options Chain Structure**:
```
              CALLS                    PUTS
Strike   Bid    Ask    IV      Bid    Ask    IV
$95     $6.20  $6.40  28%     $0.80  $0.95  32%
$100    $2.50  $2.65  25%     $2.10  $2.25  26%  ← ATM
$105    $0.70  $0.85  27%     $5.30  $5.50  29%
```

**Market Structure**:
```
Exchanges:     CBOE, ISE, PHLX, AMEX, etc.
Contract size: 100 shares per contract
Expiration:    Weekly, monthly, quarterly, LEAPS
Settlement:    Physical delivery or cash
Assignment:    Random selection of short holders
```

**Algo Trading Considerations**:
- Leverage is built in (control 100 shares for fraction of cost)
- Bid-ask spreads wider than underlying
- Liquidity concentrated at ATM strikes
- Greeks change dynamically (gamma risk near expiry)
- Implied volatility crucial for pricing

---

### 3. Futures

**What it is**: Standardized contracts to buy/sell an asset at a predetermined price on a future date.

Unlike options (where you have the right but not obligation), futures are binding agreements. If you buy a futures contract, you're agreeing to take delivery of the underlying asset at expiration (though most traders close positions before expiration to avoid this).

Futures were originally created for farmers and commodity producers. A corn farmer might sell corn futures in spring to lock in a price for their fall harvest—eliminating the risk that prices crash before harvest. A cereal company might buy corn futures to lock in their input costs. Today, futures are used heavily for speculation and hedging across all asset classes.

**Why traders love futures**: Futures offer high leverage (you only need to put up 5-10% of the contract value as margin), trade nearly 24 hours, and have very tight bid-ask spreads in liquid markets like E-mini S&P 500 (ES). Many professional traders prefer futures over stocks for short-term trading because of these advantages.

**Characteristics**:
```
Obligation:     Must buy/sell at expiration (unlike options)
Leverage:       High (5-20% margin requirement)
Mark-to-market: Daily settlement of gains/losses
Expiration:     Specific delivery months
```

**Types of Futures**:
| Category | Examples | Contract Specs |
|----------|----------|----------------|
| **Equity Index** | ES (S&P 500), NQ (Nasdaq), YM (Dow) | Cash settled |
| **Commodities** | CL (Crude), GC (Gold), ZC (Corn) | Physical delivery |
| **Interest Rates** | ZN (10Y Note), ZB (30Y Bond), ED (Eurodollar) | Cash or delivery |
| **Currencies** | 6E (EUR/USD), 6J (JPY/USD) | Physical delivery |
| **Crypto** | BTC, ETH futures | Cash settled |

**Contract Specifications (E-mini S&P 500 - ES)**:
```
Tick size:        0.25 index points
Tick value:       $12.50 per tick
Contract value:   $50 × index level
Margin:           ~$12,000 (varies)
Expiration:       Quarterly (Mar, Jun, Sep, Dec)
Trading hours:    Sunday 6pm - Friday 5pm ET (23h/day)
```

**Futures Pricing**:
```
Theoretical Price:
  F = S × e^((r - d) × t)

Where:
  F = futures price
  S = spot price
  r = risk-free rate
  d = dividend yield
  t = time to expiration

Basis = Futures - Spot
Contango:    Futures > Spot (normal)
Backwardation: Futures < Spot (supply shortage)
```

**Rolling Contracts**:
```
Futures expire → must roll to next contract
Roll date:    Typically 1-2 weeks before expiry
Roll cost:    Difference between contracts
Continuous contracts: Adjusted for rolls (backtesting)
```

**Algo Trading Considerations**:
- Very high leverage (can be risky)
- Extremely liquid (ES trades billions daily)
- Near 24-hour trading
- Must manage roll dates
- Margin calls if account equity drops

---

### 4. Forex (Foreign Exchange)

**What it is**: Trading of currency pairs - exchanging one currency for another.

The forex market is the largest financial market in the world, with over $7 trillion traded daily. Unlike stocks which trade on centralized exchanges, forex is "over-the-counter" (OTC)—trades happen directly between participants (banks, brokers, traders) without a central location.

Currencies always trade in pairs because you're simultaneously buying one currency and selling another. When you "buy EUR/USD," you're buying euros and selling dollars. If EUR/USD rises from 1.0800 to 1.0900, the euro has strengthened against the dollar—each euro now buys more dollars.

**Why forex attracts algorithmic traders**: The market is extremely liquid (especially for major pairs like EUR/USD), operates 24 hours Monday through Friday, and offers high leverage. The major drawback is that forex trends tend to be subtler and noisier than equity trends, making many strategies harder to implement profitably.

**Characteristics**:
```
Pairs:         Always quoted as base/quote (EUR/USD)
Decentralized: No central exchange (OTC)
Size:          Largest market (~$7 trillion daily)
Leverage:      Very high (50:1 to 500:1 available)
```

**Major Currency Pairs**:
| Pair | Name | Characteristics |
|------|------|-----------------|
| **EUR/USD** | Euro | Most traded, tightest spreads |
| **USD/JPY** | Dollar-Yen | Asian session active |
| **GBP/USD** | Cable | Volatile, Brexit sensitive |
| **USD/CHF** | Swissie | Safe haven |
| **AUD/USD** | Aussie | Commodity correlated |
| **USD/CAD** | Loonie | Oil correlated |
| **NZD/USD** | Kiwi | Carry trade popular |

**Cross Pairs** (no USD): EUR/GBP, EUR/JPY, GBP/JPY
**Exotic Pairs**: USD/TRY, USD/ZAR, USD/MXN (wider spreads)

**Pricing Conventions**:
```
EUR/USD = 1.0850
  Means: 1 EUR = 1.0850 USD
  Base currency: EUR
  Quote currency: USD

Pip:         0.0001 (fourth decimal) for most pairs
             0.01 for JPY pairs
Pip value:   Depends on position size and pair
Lot sizes:   Standard (100k), Mini (10k), Micro (1k)
```

**Trading Sessions**:
```
Sydney:     5pm - 2am ET
Tokyo:      7pm - 4am ET
London:     3am - 12pm ET
New York:   8am - 5pm ET

Most active: London-New York overlap (8am - 12pm ET)
```

**Key Drivers**:
- Interest rate differentials
- Economic data (GDP, employment, inflation)
- Central bank policy (Fed, ECB, BOJ, BOE)
- Risk sentiment (risk-on/risk-off)
- Trade balances

**Algo Trading Considerations**:
- Extremely high liquidity, tight spreads on majors
- 24-hour trading (Sunday 5pm - Friday 5pm ET)
- Leverage amplifies gains AND losses
- Swap/rollover costs for overnight positions
- News releases cause extreme volatility spikes

---

### 5. Cryptocurrencies

**What it is**: Digital/virtual currencies using cryptography, traded on crypto exchanges.

Cryptocurrencies are a relatively new asset class that emerged with Bitcoin in 2009. Unlike traditional currencies issued by central banks, most cryptocurrencies are decentralized—they operate on blockchain networks without a central authority.

For algorithmic traders, crypto presents unique opportunities and challenges:

**Opportunities**: Extreme volatility creates more trading opportunities. Markets never close (24/7/365). The market is less efficient than traditional markets, meaning inefficiencies can persist longer. Many exchanges offer generous API access and low fees for algorithmic traders.

**Challenges**: Volatility cuts both ways—you can lose money very quickly. Exchange risk is real (hacks, insolvency). Liquidity varies dramatically between assets. Regulatory uncertainty exists in many jurisdictions. The market is highly correlated (when Bitcoin drops, almost everything drops).

**Characteristics**:
```
Decentralized:   No central authority (mostly)
24/7 trading:    Never closes
Volatile:        10-20% daily moves not uncommon
Fragmented:      Many exchanges, price variations
```

**Major Cryptocurrencies**:
| Asset | Ticker | Market Cap | Characteristics |
|-------|--------|------------|-----------------|
| **Bitcoin** | BTC | Largest | Digital gold, store of value |
| **Ethereum** | ETH | 2nd | Smart contracts, DeFi |
| **Tether** | USDT | Stablecoin | Pegged to $1 USD |
| **BNB** | BNB | Exchange | Binance ecosystem |
| **Solana** | SOL | Alt L1 | High speed, low fees |
| **XRP** | XRP | Payments | Cross-border transfers |

**Trading Venues**:
| Type | Examples | Characteristics |
|------|----------|-----------------|
| **CEX** (Centralized) | Binance, Coinbase, Kraken | Order book, KYC required |
| **DEX** (Decentralized) | Uniswap, dYdX | On-chain, no KYC |
| **Derivatives** | Binance Futures, Deribit | Perpetuals, options |
| **Traditional** | CME, Alpaca | Regulated, limited pairs |

**Perpetual Futures**:
```
No expiration date (unlike traditional futures)
Funding rate: Paid/received every 8 hours
  Positive funding: Longs pay shorts
  Negative funding: Shorts pay longs

Keeps perpetual price close to spot
```

**Crypto-Specific Concepts**:
```
Gas fees:      Transaction costs on-chain
Slippage:      Price impact on DEXes
MEV:           Miner extractable value (front-running)
Wallet types:  Hot (online), Cold (offline)
On-chain data: Whale movements, exchange flows
```

**Algo Trading Considerations**:
- Extreme volatility = opportunity + risk
- Liquidity varies hugely between assets
- Exchange risk (hacks, insolvency)
- API rate limits stricter than traditional
- Price discrepancies across exchanges (arb opportunities)
- 24/7 means constant monitoring needed

---

### 6. Bonds (Fixed Income)

**What it is**: Debt instruments where issuer owes holder principal plus interest payments.

**Characteristics**:
```
Face value:     Principal amount (typically $1000)
Coupon:         Interest rate paid (annually/semi-annually)
Maturity:       Date when principal is repaid
Yield:          Return based on current price
```

**Types of Bonds**:
| Type | Issuer | Risk | Examples |
|------|--------|------|----------|
| **Treasury** | US Government | Lowest | T-Bills, T-Notes, T-Bonds |
| **Municipal** | State/Local govt | Low | Munis (often tax-free) |
| **Corporate IG** | Investment grade corps | Medium | Apple, Microsoft bonds |
| **Corporate HY** | Below investment grade | High | "Junk bonds" |
| **Sovereign** | Foreign governments | Varies | German Bunds, UK Gilts |

**Treasury Securities**:
| Type | Maturity | Coupon | Pricing |
|------|----------|--------|---------|
| **T-Bill** | ≤ 1 year | Zero (discount) | 100 - yield |
| **T-Note** | 2-10 years | Semi-annual | Par ± premium/discount |
| **T-Bond** | 20-30 years | Semi-annual | Par ± premium/discount |
| **TIPS** | Various | Inflation-adjusted | Real yield |

**Bond Math**:
```
Price and Yield: Inverse relationship
  Price ↑ → Yield ↓
  Price ↓ → Yield ↑

Yield to Maturity (YTM):
  Total return if held to maturity

Duration:
  Sensitivity to interest rate changes
  Higher duration = more price volatility

Convexity:
  Rate of change of duration
  Higher convexity = more upside, less downside
```

**Yield Curve**:
```
Normal:    Upward sloping (short rates < long rates)
Inverted:  Downward sloping (recession signal)
Flat:      Similar rates across maturities

2s10s spread = 10Y yield - 2Y yield (watched closely)
```

**Trading Bonds**:
```
Primary market:  Auctions (Treasury Direct)
Secondary:       OTC dealer market, ETFs
Bond ETFs:       TLT, IEF, LQD, HYG, BND
Futures:         ZN (10Y), ZB (30Y), ZF (5Y)
```

**Algo Trading Considerations**:
- Less liquid than equities (except Treasuries)
- OTC market = less transparency
- Interest rate sensitivity crucial
- Credit risk for corporate bonds
- Futures more liquid than cash bonds

---

### 7. ETFs (Exchange-Traded Funds)

**What it is**: Funds that track an index, sector, commodity, or other assets, but trade like stocks on exchanges.

**Characteristics**:
```
Diversification: Hold basket of assets
Transparency:    Holdings disclosed daily
Liquidity:       Trade intraday like stocks
Cost:            Low expense ratios
```

**ETF Types**:
| Type | Tracks | Examples |
|------|--------|----------|
| **Index** | Market indices | SPY, QQQ, IWM, VTI |
| **Sector** | Industry sectors | XLF (financials), XLE (energy) |
| **Bond** | Fixed income | TLT, BND, LQD, HYG |
| **Commodity** | Physical commodities | GLD (gold), USO (oil) |
| **International** | Foreign markets | EFA, EEM, VEU |
| **Leveraged** | 2x/3x exposure | TQQQ, SOXL, UPRO |
| **Inverse** | Short exposure | SH, SQQQ, SPXU |
| **Thematic** | Specific themes | ARKK, HACK, BOTZ |

**Creation/Redemption Process**:
```
Authorized Participants (APs) arbitrage:

NAV > Market Price:
  AP buys ETF shares, redeems for underlying, sells underlying

NAV < Market Price:
  AP buys underlying, creates ETF shares, sells ETF

This keeps ETF price close to NAV
```

**Premium/Discount**:
```
Premium:   Market Price > NAV (buying pressure)
Discount:  Market Price < NAV (selling pressure)

Usually small for liquid ETFs
Can be large for:
  - International (time zone differences)
  - Bond ETFs (illiquid underlying)
  - Exotic/complex ETFs
```

**Leveraged/Inverse ETF Mechanics**:
```
Daily reset:  Leverage applied daily, not long-term
Decay:        Volatility drag erodes returns over time

Example (2x leveraged):
  Day 1: Index +10% → ETF +20% (100 → 120)
  Day 2: Index -10% → ETF -20% (120 → 96)
  Index: 100 → 99 (-1%)
  ETF:   100 → 96 (-4%)  ← Decay!

Only suitable for short-term trading
```

**Algo Trading Considerations**:
- Very liquid for major ETFs
- Arbitrage opportunities (ETF vs underlying)
- Leveraged ETFs need daily rebalancing awareness
- Expense ratios eat into returns
- Dividend treatment varies

---

### 8. CFDs (Contracts for Difference)

**What it is**: Derivative contracts to exchange the difference in price from open to close, without owning the underlying asset.

**Characteristics**:
```
No ownership:   Pure price speculation
Leverage:       High (5:1 to 30:1 typical)
Both ways:      Easy to go long or short
No expiration:  Hold indefinitely
```

**How CFDs Work**:
```
Open position:  Buy 100 CFDs of Stock X at $50
Close position: Sell 100 CFDs at $55

Profit = (55 - 50) × 100 = $500
  (minus spreads and overnight fees)

No shares ever owned or borrowed
```

**CFD Costs**:
| Cost | Description |
|------|-------------|
| **Spread** | Bid-ask difference (built into price) |
| **Commission** | Per-trade fee (some brokers) |
| **Overnight financing** | Daily fee for holding positions |
| **Currency conversion** | If trading foreign assets |

**Overnight Financing**:
```
Long position:  Pay (benchmark rate + markup)
Short position: Receive (benchmark rate - markup)
                Often net negative for shorts too

Annual rate: 2-4% typical, charged daily
```

**Regulatory Status**:
```
Banned:      USA (not offered to US residents)
Available:   UK, Europe, Australia, Asia
Regulated:   FCA (UK), ASIC (Australia), CySEC (Cyprus)

Leverage caps (ESMA rules for EU):
  Major FX: 30:1
  Minor FX, Gold: 20:1
  Commodities: 10:1
  Equities: 5:1
  Crypto: 2:1
```

**Algo Trading Considerations**:
- Not available for US-based traders
- Overnight costs add up for longer holds
- Spreads can widen significantly
- No ownership = no dividends (adjustment made)
- Counterparty risk (broker is counterparty)

---

### 9. Commodities

**What it is**: Raw materials and primary products traded on exchanges.

**Categories**:

**Energy**:
| Commodity | Symbol | Exchange | Contract Size |
|-----------|--------|----------|---------------|
| Crude Oil (WTI) | CL | NYMEX | 1,000 barrels |
| Brent Crude | BZ | ICE | 1,000 barrels |
| Natural Gas | NG | NYMEX | 10,000 MMBtu |
| Gasoline | RB | NYMEX | 42,000 gallons |
| Heating Oil | HO | NYMEX | 42,000 gallons |

**Metals**:
| Commodity | Symbol | Exchange | Contract Size |
|-----------|--------|----------|---------------|
| Gold | GC | COMEX | 100 troy oz |
| Silver | SI | COMEX | 5,000 troy oz |
| Copper | HG | COMEX | 25,000 lbs |
| Platinum | PL | NYMEX | 50 troy oz |
| Palladium | PA | NYMEX | 100 troy oz |

**Agriculture**:
| Commodity | Symbol | Exchange | Contract Size |
|-----------|--------|----------|---------------|
| Corn | ZC | CBOT | 5,000 bushels |
| Soybeans | ZS | CBOT | 5,000 bushels |
| Wheat | ZW | CBOT | 5,000 bushels |
| Coffee | KC | ICE | 37,500 lbs |
| Sugar | SB | ICE | 112,000 lbs |
| Cotton | CT | ICE | 50,000 lbs |
| Live Cattle | LE | CME | 40,000 lbs |
| Lean Hogs | HE | CME | 40,000 lbs |

**Price Drivers**:
```
Supply factors:
  - Weather (agriculture)
  - Geopolitics (oil, gas)
  - Mining output (metals)
  - Inventory levels

Demand factors:
  - Economic growth (industrial metals, energy)
  - Currency strength (USD inverse correlation)
  - Seasonal patterns (heating oil in winter)
  - Speculation
```

**Contango and Backwardation**:

```
FUTURES TERM STRUCTURE

CONTANGO (Normal market)                BACKWARDATION (Supply shortage)

Price                                   Price
  │                                       │
  │              Jun ●                    │  Spot ●
  │          May ●                        │       ╲
  │      Apr ●                            │        ╲
  │  Mar ●                                │    Mar  ●
  │ Spot ●                                │          ╲
  │                                       │       Apr ●
  │                                       │             ╲
  │                                       │          May ●
  │                                       │                ╲
  │                                       │             Jun ●
  └────────────────────▶                  └────────────────────▶
        Time to expiration                    Time to expiration

  Futures ABOVE spot                      Futures BELOW spot
  Rolling = LOSS                          Rolling = PROFIT
  (sell low, buy high)                    (sell high, buy low)


WHY CONTANGO HURTS LONG ETFs (like USO):

  Month 1: Hold May futures at $80
  Roll date: Sell May at $80, Buy June at $82
  You lost $2 just from rolling!

  This "roll cost" compounds over time and destroys
  returns for buy-and-hold commodity ETF investors
```

```
Contango (futures > spot):
  - Normal for storable commodities
  - Cost of carry: storage + financing
  - Rolling long futures = negative roll yield

Backwardation (futures < spot):
  - Supply shortage
  - Convenience yield
  - Rolling long futures = positive roll yield
```

**Trading Commodities**:
```
Futures:    Direct exposure, physical delivery possible
ETFs:       GLD, SLV, USO, DBA (roll cost embedded)
Stocks:     Producers (XOM, FCX, NEM)
Options:    On futures contracts
```

**Algo Trading Considerations**:
- Supply/demand fundamentals matter
- Seasonal patterns often tradeable
- Roll costs significant for ETFs
- Physical delivery risk if holding to expiration
- Weather and geopolitical events cause gaps

---

### 10. Swaps and OTC Derivatives

**What it is**: Customized derivative contracts traded directly between parties (not on exchanges).

**Interest Rate Swaps**:
```
Exchange fixed rate for floating rate

Example:
  Party A pays: 3% fixed
  Party B pays: SOFR floating

Notional: $10 million (not exchanged)
Tenor: 5 years

Used for: Hedging interest rate exposure
```

**Credit Default Swaps (CDS)**:
```
Insurance against bond default

Buyer pays: Premium (spread) quarterly
Seller pays: Face value if default occurs

CDS Spread = Market's view of default risk
Higher spread = higher perceived risk
```

**Total Return Swaps**:
```
Exchange total return of asset for fixed payment

Party A receives: Total return on S&P 500
Party A pays: SOFR + spread

Used for: Leverage, avoiding ownership
```

**Algo Trading Considerations**:
- Mostly institutional market
- Bilateral credit risk
- Less transparency than exchange-traded
- Size and terms customizable
- Central clearing now required for many swaps

---

### Asset Class Selection Guide

**By Trading Style**:
| Style | Best Assets | Why |
|-------|-------------|-----|
| Day trading | Futures, Forex, liquid stocks | Liquidity, low costs |
| Swing trading | Stocks, ETFs, Forex | Holds overnight, trends |
| Scalping | Futures, Forex | Tight spreads, speed |
| Position trading | Stocks, ETFs, Bonds | Longer timeframes |
| Arbitrage | All (especially ETFs, futures) | Price discrepancies |

**By Capital Requirements**:
| Capital | Suitable Assets |
|---------|-----------------|
| < $1,000 | Crypto (fractional), Forex (micro lots) |
| $1,000 - $25,000 | Stocks, ETFs, Forex |
| $25,000+ | All assets (PDT rule cleared for US) |
| $50,000+ | Futures comfortably |

**By Market Hours Preference**:
| Preference | Assets |
|------------|--------|
| US market hours only | Stocks, ETFs, Options |
| Extended hours | Futures (near 24h), Forex |
| 24/7 | Crypto |
| Specific sessions | Forex (pick session overlap) |

---

## Fundamental Primitives

Before diving into specific strategies, you need to understand the building blocks that all trading strategies use. These "primitives" are the foundational concepts—the types of data you'll work with, the orders you'll place, and the positions you'll manage.

### Market Data Types

Your algorithm needs data to make decisions. The type and quality of data you use significantly impacts your strategy's potential. Higher-resolution data (like tick data) enables more sophisticated strategies but requires more storage, processing power, and often costs more to obtain.

| Type | Description | Use Case | Explanation |
|------|-------------|----------|-------------|
| **Tick Data** | Every trade/quote as it occurs | HFT, microstructure analysis | The most granular data available. You see every single trade and quote change. One day of tick data for a liquid stock might be millions of records. |
| **OHLCV Bars** | Aggregated candles (1m, 5m, 1h, 1d) | Most retail strategies | "Candles" summarize price action: Open (first price), High (max), Low (min), Close (last price), Volume. Most beginners start here because it's manageable and widely available for free. |
| **Level 1** | Best bid/ask + last trade | Basic execution | The "top of the book"—the best price someone is willing to buy (bid) and sell (ask) at any moment. The difference is the "spread." |
| **Level 2 / Order Book** | Full depth of market | Market making, liquidity analysis | See all pending buy and sell orders at every price level. Essential for understanding liquidity and market impact of large orders. |
| **Time & Sales** | Executed trade stream | Volume analysis, tape reading | A record of every completed trade showing price, size, and time. Traders use this to identify institutional buying/selling patterns. |

```
CANDLESTICK (OHLCV BAR) ANATOMY

     BULLISH CANDLE              BEARISH CANDLE
     (Close > Open)              (Close < Open)

          │                           │
          │ ← High                    │ ← High
          │                           │
        ┌─┴─┐                       ┌─┴─┐
        │   │ ← Close (top)         │░░░│ ← Open (top)
        │   │                       │░░░│
        │   │    Body               │░░░│    Body
        │   │    (white/green)      │░░░│    (black/red)
        │   │                       │░░░│
        │   │ ← Open (bottom)       │░░░│ ← Close (bottom)
        └─┬─┘                       └─┬─┘
          │                           │
          │ ← Low                     │ ← Low
          │                           │

  Upper wick (shadow): Shows high reached during period
  Lower wick (shadow): Shows low reached during period
  Body: Range between open and close

  Long body = Strong conviction
  Long wicks = Rejection of extreme prices
  Doji (tiny body) = Indecision
```

### Order Types

Understanding order types is crucial—using the wrong order type can cost you money through slippage or missed fills.

| Order | Behavior | When to Use | Detailed Explanation |
|-------|----------|-------------|---------------------|
| **Market** | Immediate fill at best price | Urgent entry/exit, liquid markets | Guarantees execution but NOT price. In volatile markets, you might get filled at a worse price than expected. Use when getting in/out matters more than the exact price. |
| **Limit** | Fill at specified price or better | Price-sensitive entries | You set the maximum price (for buys) or minimum price (for sells). You might not get filled if price never reaches your level. Use when price matters more than guaranteed execution. |
| **Stop** | Triggers market order at price | Stop losses | Sits dormant until price hits your stop level, then becomes a market order. Protects against large losses but may execute at a worse price during fast moves. |
| **Stop-Limit** | Triggers limit order at price | Controlled stop losses | Like a stop order, but becomes a limit order instead of market. Avoids slippage but risks not executing at all if price gaps through your limit. |
| **Trailing Stop** | Stop that follows price | Lock in profits | The stop price moves with the market. If you set a $2 trailing stop and stock rises from $100 to $110, your stop moves from $98 to $108. It never moves down. |
| **Bracket/OCO** | Entry + stop loss + take profit | Complete trade management | "One-Cancels-Other"—you set both a profit target and stop loss. When one triggers, the other cancels automatically. Essential for automated systems. |
| **Iceberg** | Large order shown in small chunks | Hide size from market | Only shows a portion of your order in the book. When that fills, more is revealed. Prevents others from seeing your full intentions and front-running you. |
| **TWAP** | Time-weighted execution | Minimize impact | Spreads a large order evenly over time. If you need to buy 10,000 shares over an hour, you might buy ~167 every minute. Reduces market impact. |
| **VWAP** | Volume-weighted execution | Match benchmark | Like TWAP but trades more when volume is higher. Aims to match the day's volume-weighted average price—a common institutional benchmark. |

### Position Concepts

Understanding positions and their implications is fundamental to trading:

- **Long**: Own the asset, profit when price rises. This is the intuitive case—you buy something hoping it goes up. If you buy 100 shares of Apple at $150 and it rises to $170, you profit $2,000.

- **Short**: Borrowed and sold, profit when price falls. This is counterintuitive at first. You borrow shares from your broker, sell them immediately, then hope to buy them back cheaper later to return them. If you short 100 shares at $150 and price drops to $130, you profit $2,000. Warning: short positions have unlimited potential loss (price can rise infinitely) while long positions can only lose what you invested.

- **Flat**: No position. Sometimes the best trade is no trade. Your algorithm should know when to stay out.

- **Notional Value**: Position size × price. If you own 100 shares at $150, your notional value is $15,000. This is the total market value of your position.

- **Exposure**: Net directional risk. If you're long $100,000 and short $60,000, your net exposure is $40,000 long. You profit if the market rises (on net).

- **Leverage**: Borrowed capital multiplier. If you have $10,000 but control a position worth $30,000, you're using 3x leverage. Leverage amplifies both gains AND losses. A 10% move in your favor nets 30% on your capital—but a 10% move against you loses 30%. Many blown accounts result from excessive leverage.

---

## Trend Following Strategies

Trend following is based on a simple observation: markets tend to move in trends rather than randomly. When a stock starts going up, it often continues going up for a while (and vice versa). Trend followers don't try to predict when a trend will start—they wait for evidence of a trend, hop on, and ride it until signs show it's ending.

**The philosophy**: "Let your winners run, cut your losers short." Trend followers accept many small losses (when trends don't materialize) in exchange for catching occasional large moves that more than compensate.

**Why it works**: Behavioral finance suggests that investors underreact to new information initially, causing trends to persist longer than they "should" in efficient markets. Additionally, institutional investors often move in and out of positions slowly due to size constraints, creating sustained directional moves.

**The catch**: Trend following strategies suffer during sideways, choppy markets where there are no sustained trends. This is called "whipsaw"—the market chops back and forth triggering buy and sell signals that result in small losses that add up.

### 1. Moving Average Crossover

This is the classic "Hello World" of algorithmic trading—simple to understand and implement, yet captures the essence of trend following.

```
MOVING AVERAGE CROSSOVER

Price
  │
  │                          ╭─── Fast MA (12)
  │         ╭──────────────╮/
  │    ╭───╯                ╲
  │   ╱   BUY ▲              ╲    SELL ▼
  │  ╱    ───────             ╲   ───────
  │ ╱    Fast crosses          ╲  Fast crosses
  │╱     above Slow             ╲ below Slow
  │───────────────────────────────────────────
  │╲                           ╱
  │ ╲    Slow MA (26) ────────╯
  │  ╲                ╱
  │   ╲──────────────╯
  │
  └──────────────────────────────────────────▶ Time
```

**Concept**: Use intersection of fast and slow moving averages to identify trend changes.

A moving average smooths out price data by averaging prices over a period. A 20-day moving average is just the average of the last 20 closing prices. As each new day passes, the oldest price drops off and the newest is added—hence the average "moves" with time.

The insight behind this strategy: when the short-term average (reflecting recent price action) crosses above the long-term average (reflecting longer history), it signals that momentum is shifting upward. The market's recent performance is outpacing its historical average—potentially the start of an uptrend.

**Variants**:
- **SMA (Simple Moving Average)**: Weights all prices equally. Easy to understand but slow to react.
- **EMA (Exponential Moving Average)**: Weights recent prices more heavily. Reacts faster to new information.
- **DEMA/TEMA (Double/Triple EMA)**: Even more responsive variants that attempt to reduce lag.

**Logic**:
```
fast_ma = EMA(close, 12)   # Reflects recent ~2 weeks of trading
slow_ma = EMA(close, 26)   # Reflects recent ~1 month of trading

BUY:  fast_ma crosses above slow_ma  # Recent performance exceeds historical
SELL: fast_ma crosses below slow_ma  # Recent performance falls below historical
```

**Parameters to tune**:
- Fast period (commonly 5-20): Shorter = more signals, more whipsaws
- Slow period (commonly 20-200): Longer = smoother, fewer signals
- Price source: Usually closing price, but some use (high+low+close)/3

**Pros**: Simple to implement and understand, captures major trends, works across many asset classes
**Cons**: Signals lag behind actual trend changes, gets chopped up in sideways markets, many false signals during ranging periods

**Real-world tip**: Many traders add a filter requiring the crossover to persist for a certain time or price distance before acting, reducing false signals.

---

### 2. MACD (Moving Average Convergence Divergence)

**Concept**: Momentum oscillator showing relationship between two EMAs.

The MACD was developed by Gerald Appel in the late 1970s and remains one of the most popular technical indicators. It essentially measures the momentum of a moving average crossover system, telling you not just when the crossover happens, but how strong the trend is.

Think of it this way: The MACD line measures the distance between the fast and slow EMAs. When a trend is strong, the fast EMA pulls away from the slow EMA (they "diverge"), making MACD large. When the trend weakens, they converge back together.

**Components Explained**:
- **MACD Line** = EMA(12) - EMA(26): The "main" line showing the difference between fast and slow EMAs. When positive, the fast is above slow (bullish). When negative, the fast is below slow (bearish).
- **Signal Line** = EMA(9) of MACD Line: A smoothed version of the MACD line. Crossovers between MACD and Signal generate trading signals.
- **Histogram** = MACD Line - Signal Line: A visual representation of the gap between MACD and Signal. When histogram is growing, momentum is increasing. When shrinking, momentum is fading.

```
MACD COMPONENTS VISUAL

                MACD Line (solid)
                    ╲
  +2 ─              ─╲─────────────────────────────────
     │            ╱   ╲
     │           ╱     ╲     Signal Line (dashed)
  +1 ─         ╱        ╲   ╱
     │        ╱    BUY ▲ ╲ ╱
   0 ────────╱───────────╳────────────────────────────
     │      ╱           ╱ ╲
  -1 ─     ╱           ╱   ╲    SELL ▼
     │    ╱           ╱     ╲
  -2 ─   ─           ─       ─────────────────────────
     └────────────────────────────────────────────────▶


  HISTOGRAM (shows momentum strength)
  ────────────────────────────────────────────────────
     │           ████
     │          █████  ← Growing bars = strengthening
     │         ██████
   0 ┼─────────────────────────────────────────────────
     │                    ▓▓▓▓
     │                   ▓▓▓▓▓  ← Shrinking bars = weakening
     │                  ▓▓▓▓▓▓
  ────────────────────────────────────────────────────
```

**Signals**:
```
BUY:  MACD crosses above Signal Line    # Momentum shifting bullish
      OR Histogram turns positive        # Same signal, different visualization
      OR Bullish divergence              # Price makes lower low but MACD makes higher low
                                         # Suggests selling pressure is weakening

SELL: MACD crosses below Signal Line
      OR Histogram turns negative
```

**Divergence explained**: If price makes a new low but MACD doesn't, it suggests that while price is falling, the momentum behind the move is weakening. This "divergence" often precedes reversals.

```
BULLISH DIVERGENCE (Reversal Warning)

Price
  │    ╭───╮
  │   ╱     ╲
  │  ╱       ╲        ╭───╮
  │ ╱         ╲      ╱     ╲    Lower low
  │╱           ╲    ╱       ╲   in PRICE
  │             ╲  ╱         ╲
  │              ╲╱           ╰─────
  │
  │   ───────────────────────────────

MACD
  │
  │        ╭──╮           ╭──╮
  │       ╱    ╲         ╱    ╲   Higher low
  │      ╱      ╲       ╱      ╲  in MACD
  │─────╱────────╲─────╱────────╲────────
  │                ╲  ╱
  │                 ╲╱
  │                  ↑
  │         Momentum weakening!
  │         Potential reversal coming


BEARISH DIVERGENCE

Price making HIGHER highs, but MACD making LOWER highs
→ Uptrend losing steam, potential top forming
```

---

### 3. Donchian Channel Breakout (Turtle Trading)

**Concept**: Enter on new N-period highs/lows (the famous Turtle Traders strategy).

```
DONCHIAN CHANNEL BREAKOUT

Price
  │
  │                              ╭────── BUY: New 20-day high
  │                         ╭───╯
  │    ══════════════════════════════  Upper Channel (20-day high)
  │         ╭──╮    ╭─╮   ╱
  │        ╱    ╲  ╱   ╲ ╱
  │       ╱      ╲╱     ╲
  │      ╱                ╲
  │     ╱    Price         ╲
  │    ╱     Action         ╲
  │    ══════════════════════════════  Lower Channel (20-day low)
  │                           ╲
  │                            ╰────── SELL: New 20-day low
  │
  └──────────────────────────────────────────▶ Time

  Entry: Break of 20-day channel
  Exit:  Break of 10-day channel (tighter)
```

This strategy has a legendary origin story. In 1983, Richard Dennis bet his partner William Eckhardt that trading could be taught to anyone. Dennis recruited a group of novices, taught them a simple trend-following system over two weeks, gave them capital to trade, and they went on to earn over $175 million in five years. These traders were called "Turtles."

The core idea is remarkably simple: markets making new highs tend to keep going higher (momentum), so buy when price breaks to a new 20-day high. The same logic applies in reverse for shorts.

**Logic**:
```
upper_channel = highest(high, 20)   # The highest price over the last 20 days
lower_channel = lowest(low, 20)     # The lowest price over the last 20 days

BUY:  price breaks above upper_channel   # New 20-day high = uptrend breakout
SELL: price breaks below lower_channel   # New 20-day low = downtrend breakout

Exit:
  Long exit on 10-period low    # Use a tighter exit to protect profits
  Short exit on 10-period high  # Faster exit than entry helps lock in gains
```

**Position Sizing (Turtle Method)** - This is perhaps the most important part:
```
N = ATR(20)                                    # Average True Range = volatility measure
Dollar_Volatility = N × Dollars_Per_Point      # How much $ value moves in one N
Unit_Size = (1% of Account) / Dollar_Volatility # Normalize risk across all positions

Example:
  Account = $100,000
  ATR(20) for crude oil = $2.50 per barrel
  Contract = 1,000 barrels per point = $2,500 per $1 move
  Dollar_Volatility = $2.50 × $1,000 = $2,500
  Unit_Size = ($100,000 × 1%) / $2,500 = 0.4 contracts

This ensures that a 1-ATR move costs you the same percentage of your account
regardless of what you're trading. Volatile assets get smaller positions.
```

**Why Turtle Trading is important**: It demonstrates that a simple, mechanical system—with proper risk management and discipline—can be highly successful. The "secret" isn't the entry signal; it's the position sizing and letting winners run while cutting losers.

---

### 4. Parabolic SAR (Stop and Reverse)

**Concept**: Trailing stop system that reverses position when hit.

**Logic**:
```
SAR follows price with acceleration factor (AF)
AF starts at 0.02, increases by 0.02 each new extreme, max 0.20

BUY:  price crosses above SAR (while in downtrend)
SELL: price crosses below SAR (while in uptrend)
```

**Use**: Best in strongly trending markets

---

### 5. ADX Trend Strength Filter

**Concept**: Use ADX to confirm trend strength before entering.

```
ADX: TREND STRENGTH (NOT DIRECTION)

  50 ┬─────────────────────────────────────────────────
     │                                 ╭────── Very strong trend
     │                              ╭──╯
  40 ┼                           ╭──╯
     │                        ╭──╯
     │                     ╭──╯
  30 ┼                  ╭──╯
     │               ╭──╯
  25 ┼══════════════╱══════════════════════════════════ TREND THRESHOLD
     │           ╭──╯        ADX above 25 = Strong trend
     │        ╭──╯           (trade with trend)
  20 ┼─────╭──╯────────────────────────────────────────
     │  ╭──╯                 ADX below 20 = No trend
     │──╯                    (avoid or mean-revert)
   0 ┴─────────────────────────────────────────────────▶

     │
     │  USING +DI AND -DI FOR DIRECTION
     │
     │    +DI (bullish pressure) ────
     │    -DI (bearish pressure) ╌╌╌╌
     │
     │  BUY:  ADX > 25 AND +DI > -DI (strong uptrend)
     │  SELL: ADX > 25 AND -DI > +DI (strong downtrend)
     │  WAIT: ADX < 20 (no clear trend, choppy)
```

**Components**:
- +DI: Positive directional indicator
- -DI: Negative directional indicator
- ADX: Smoothed average of |+DI - -DI| / (+DI + -DI)

**Logic**:
```
Strong trend: ADX > 25
BUY:  ADX > 25 AND +DI > -DI
SELL: ADX > 25 AND -DI > +DI

Avoid trading when ADX < 20 (choppy market)
```

---

### 6. Supertrend

**Concept**: Volatility-based trend indicator using ATR.

```
SUPERTREND: FOLLOWS PRICE WITH ATR BUFFER

Price
  │
  │                          ╭────╮
  │                      ╭───╯    │
  │                  ╭───╯        │
  │    UPTREND   ╭───╯            │
  │    (GREEN)───╯                │
  │  ════════════╯                │ DOWNTREND
  │  ↑ Supertrend                 │ (RED)
  │  (3 ATR below price)          │══════════
  │                               │     ↑ Supertrend
  │                               ╰──── (3 ATR above price)
  │                                  ╲
  │                                   ╲
  │    BUY: Price crosses              ╲
  │    ABOVE Supertrend          SELL: Price crosses
  │                              BELOW Supertrend
  └─────────────────────────────────────────────────────▶

  • Green Supertrend = Uptrend (line below price)
  • Red Supertrend = Downtrend (line above price)
  • Line flips when price crosses through it
```

**Logic**:
```
basic_upper = (high + low) / 2 + (multiplier × ATR)
basic_lower = (high + low) / 2 - (multiplier × ATR)

Supertrend = lower_band when close > lower_band (uptrend)
           = upper_band when close < upper_band (downtrend)

BUY:  close crosses above Supertrend
SELL: close crosses below Supertrend
```

**Parameters**: ATR period (typically 10), multiplier (typically 3)

---

### 7. Ichimoku Cloud

**Concept**: Complete trading system showing support, resistance, trend, and momentum.

```
ICHIMOKU CLOUD STRUCTURE

Price                               Future Cloud
  │                                 (projected 26 periods ahead)
  │         Tenkan (fast) ──╮              │
  │                          ╲             │
  │    ─────── Kijun (slow) ───────        │
  │              │                         ▼
  │              │              ┌─────────────────────┐
  │    Price ────┼──────────────│░░░░░░░░░░░░░░░░░░░░░│ Senkou Span A
  │              │              │░░░GREEN CLOUD░░░░░░░│ (bullish)
  │              │              │░░░░░░░░░░░░░░░░░░░░░│ Senkou Span B
  │              │              └─────────────────────┘
  │              │
  │        Chikou Span
  │    (price plotted 26 periods back)
  │
  └────────────────────────────────────────────────────▶ Time

  BULLISH: Price above cloud, Tenkan > Kijun, green future cloud
  BEARISH: Price below cloud, Tenkan < Kijun, red future cloud
```

**Components**:
- Tenkan-sen (Conversion): (9-period high + 9-period low) / 2
- Kijun-sen (Base): (26-period high + 26-period low) / 2
- Senkou Span A: (Tenkan + Kijun) / 2, plotted 26 periods ahead
- Senkou Span B: (52-period high + 52-period low) / 2, plotted 26 periods ahead
- Chikou Span: Close plotted 26 periods back

**Signals**:
```
BUY (Strong):
  - Price above cloud
  - Tenkan crosses above Kijun
  - Chikou above price
  - Future cloud is green (Span A > Span B)

SELL (Strong): Opposite conditions
```

---

### 8. Keltner Channel Trend

**Concept**: EMA-based channel using ATR for bands.

**Logic**:
```
middle = EMA(close, 20)
upper = middle + (2 × ATR(10))
lower = middle - (2 × ATR(10))

BUY:  close > upper (breakout with trend)
SELL: close < lower

Trend filter: Only long when middle is rising
```

---

### 9. Heikin-Ashi Trend

**Concept**: Smoothed candlesticks that filter noise.

**Calculation**:
```
HA_Close = (open + high + low + close) / 4
HA_Open = (prev_HA_Open + prev_HA_Close) / 2
HA_High = max(high, HA_Open, HA_Close)
HA_Low = min(low, HA_Open, HA_Close)

BUY:  HA candle turns green + no lower wick (strong uptrend)
SELL: HA candle turns red + no upper wick (strong downtrend)
```

---

### 10. Linear Regression Channel

**Concept**: Statistical trend channel based on regression line.

**Logic**:
```
regression_line = linear regression of close over N periods
upper = regression_line + (2 × standard_error)
lower = regression_line - (2 × standard_error)

Trend: Slope of regression line
BUY:  Price near lower band + positive slope
SELL: Price near upper band + negative slope
```

---

## Mean Reversion Strategies

Mean reversion is based on the opposite observation from trend following: prices tend to bounce back to their average over time. When a stock drops "too much too fast," it often bounces back. When it rises "too far too fast," it often pulls back.

**The philosophy**: "Buy low, sell high" in its purest form. Mean reversion traders look for extremes—overbought or oversold conditions—and bet on a return to normal.

**Why it works**: Markets overreact to news in the short term. Fear and greed cause prices to temporarily deviate from fair value. Market makers and arbitrageurs eventually step in to correct these deviations.

**The catch**: Sometimes what looks like an "extreme" is actually the beginning of a new trend. A stock dropping 20% might bounce back—or it might drop another 50% if there's something fundamentally wrong. "Catching falling knives" is the risk. Mean reversion also tends to make money slowly (many small gains) but lose money quickly (occasional big losses when prices don't revert).

**When to use each approach**:
- Trend following works better in markets with strong directional moves
- Mean reversion works better in range-bound, choppy markets
- The best systems often combine both, using one approach in some market regimes and switching in others

### 11. Bollinger Band Bounce

Bollinger Bands are one of the most popular technical analysis tools, created by John Bollinger in the 1980s.

```
BOLLINGER BANDS MEAN REVERSION

Price
  │     ╭──────╮                    ╭────  Upper Band (+2σ)
  │    ╱        ╲     SELL ▼       ╱
  │   ╱          ╲   ─────────    ╱
  │  ╱            ╲    Overbought╱
  │ ─────────────────────────────────────  Middle (SMA 20)
  │                 ╲          ╱
  │                  ╲        ╱   BUY ▲
  │                   ╲      ╱   ─────────
  │                    ╲    ╱    Oversold
  │                     ╰──╯               Lower Band (-2σ)
  │
  │   ◄── Ranging Market: Strategy Works ──►
  │
  └──────────────────────────────────────────▶ Time

  Key: Price reverts to middle band from extremes
```

**Concept**: Price tends to revert to mean after touching bands.

The bands are based on statistics: in a normal distribution, about 95% of data falls within 2 standard deviations of the mean. So if prices are normally distributed, they should stay within the bands 95% of the time. When price touches or exceeds a band, it's statistically "extreme."

**Logic Explained**:
```
middle = SMA(close, 20)                    # The "mean" to revert to
upper = middle + (2 × StdDev(close, 20))   # 2 standard deviations above
lower = middle - (2 × StdDev(close, 20))   # 2 standard deviations below

BUY:  close < lower AND RSI < 30
      # Price has fallen outside the lower band (statistically extreme)
      # AND RSI confirms oversold conditions
      # This double-confirmation reduces false signals

SELL: close > upper AND RSI > 70
      # Price exceeded upper band AND RSI shows overbought

Target: middle band     # Expect price to revert to the average
Stop: Beyond the band   # If price continues further extreme, admit defeat
```

**Variant - Bollinger Band Squeeze**:
```
Squeeze: bandwidth = (upper - lower) / middle < threshold

When bands squeeze tight (low volatility), it often precedes a big move.
Think of it like compressing a spring—the tighter the squeeze, the bigger
the eventual breakout. Traders wait for the squeeze, then trade the
direction of the breakout.
```

**Important caveat**: Bands work best in ranging markets. In strong trends, price can "walk the band"—continuously touching or exceeding the upper (or lower) band for extended periods. Using mean reversion during a strong trend is a recipe for losses.

---

### 12. RSI Mean Reversion

**Concept**: RSI extremes indicate overbought/oversold conditions.

```
RSI OVERBOUGHT/OVERSOLD

RSI
100 ┬─────────────────────────────────────────────
    │
 80 ┼─────────────────────────────────────────────
    │            ╭───╮
 70 ┼ ═══════════╪═══╪════════════════════════════ OVERBOUGHT
    │          ╱ │   │ ╲         SELL ▼
 60 ┤         ╱  │   │  ╲
    │        ╱   │   │   ╲
 50 ┼───────╱────┴───┴────╲───────────────────────
    │      ╱               ╲       ╱
 40 ┤     ╱                 ╲     ╱
    │    ╱                   ╲   ╱
 30 ┼ ══════════════════════════╪═════════════════ OVERSOLD
    │                         ╲ │ ╱   BUY ▲
 20 ┼──────────────────────────╰─╯────────────────
    │
  0 ┴─────────────────────────────────────────────▶ Time

    Zone 30-70: Neutral (no action)
    Below 30:   Oversold → Look for buying opportunity
    Above 70:   Overbought → Look for selling opportunity
```

**Logic**:
```
RSI = 100 - (100 / (1 + avg_gain / avg_loss))

BUY:  RSI < 30 (oversold)
SELL: RSI > 70 (overbought)
```

**Variants**:
- RSI(2) for short-term (Larry Connors style)
- RSI divergence (price vs RSI disagreement)
- Cumulative RSI

**Connors RSI Strategy**:
```
BUY:  RSI(2) < 10 AND close > SMA(200) AND close < SMA(5)
SELL: close > SMA(5)
```

---

### 13. Stochastic Oscillator Reversal

**Concept**: Compare close to high-low range over period.

```
STOCHASTIC OSCILLATOR

      %K (fast, solid)  %D (slow, dashed)
100 ┬─────────────────────────────────────
    │
 80 ┼══════════════════════════════════════ OVERBOUGHT
    │        ╭─╮
    │       ╱   ╲        SELL signal:
    │      ╱     ╲       %K crosses below %D
    │     ╱   ╳───╲──    while above 80
    │    ╱   ╱     ╲
 50 ┼───╱───╱───────╲─────────────────────
    │  ╱   ╱         ╲
    │ ╱   ╱           ╲
    │╱   ╱             ╲
 20 ┼══════════════════╲══════════════════ OVERSOLD
    │                   ╲   ╱
    │              BUY   ╲ ╱  %K crosses above %D
    │            signal   ╳   while below 20
    │                    ╱ ╲
  0 ┴───────────────────────────────────▶

  %K measures: Where is price within recent range?
  %K = 0   → Price at lowest low
  %K = 100 → Price at highest high
```

**Logic**:
```
%K = (close - lowest_low) / (highest_high - lowest_low) × 100
%D = SMA(%K, 3)

BUY:  %K < 20 AND %K crosses above %D
SELL: %K > 80 AND %K crosses below %D
```

---

### 14. CCI (Commodity Channel Index) Reversal

**Concept**: Measures price deviation from statistical mean.

**Logic**:
```
typical_price = (high + low + close) / 3
CCI = (typical_price - SMA(typical_price)) / (0.015 × mean_deviation)

BUY:  CCI < -100 (oversold)
SELL: CCI > +100 (overbought)
```

---

### 15. Z-Score Mean Reversion

**Concept**: Statistical measure of deviation from mean.

**Logic**:
```
z_score = (price - SMA(price, N)) / StdDev(price, N)

BUY:  z_score < -2.0
SELL: z_score > +2.0
EXIT: z_score returns to 0
```

---

### 16. Williams %R Strategy

**Concept**: Similar to stochastic, momentum indicator.

**Logic**:
```
%R = (highest_high - close) / (highest_high - lowest_low) × -100

BUY:  %R < -80 (oversold)
SELL: %R > -20 (overbought)
```

---

### 17. Ornstein-Uhlenbeck Mean Reversion

**Concept**: Model price as mean-reverting stochastic process.

**Model**:
```
dX = θ(μ - X)dt + σdW

Where:
θ = speed of mean reversion
μ = long-term mean
σ = volatility

Trade when X deviates significantly from μ
Half-life = ln(2) / θ
```

---

## Momentum Strategies

### 18. Rate of Change (ROC) Momentum

**Concept**: Measure percentage price change over period.

**Logic**:
```
ROC = ((close - close[N]) / close[N]) × 100

BUY:  ROC > 0 AND increasing (positive accelerating momentum)
SELL: ROC < 0 AND decreasing
```

---

### 19. Relative Strength Momentum (Cross-Sectional)

**Concept**: Buy strongest performers, sell weakest (factor investing).

**Logic**:
```
For universe of stocks:
  Calculate 12-month return (skip most recent month)
  Rank all stocks by return

BUY:  Top decile (winners)
SELL: Bottom decile (losers)

Rebalance monthly
```

**Fama-French Momentum Factor (UMD)**: Up minus Down

---

### 20. Dual Momentum (Gary Antonacci)

**Concept**: Combine absolute and relative momentum.

**Logic**:
```
Absolute Momentum: asset return > T-bill return?
Relative Momentum: which asset has higher return?

Example (Global Equities Momentum):
  Compare: US Stocks, International Stocks, Bonds

  IF US_return > Intl_return AND US_return > Tbill:
    Hold US Stocks
  ELIF Intl_return > US_return AND Intl_return > Tbill:
    Hold International Stocks
  ELSE:
    Hold Bonds (absolute momentum failed)
```

---

### 21. 52-Week High Momentum

**Concept**: Stocks near 52-week high outperform (anchoring bias).

**Logic**:
```
nearness = price / 52_week_high

BUY:  nearness > 0.95 (within 5% of high)
      Often combined with other momentum filters
```

---

### 22. Money Flow Index (MFI) Momentum

**Concept**: Volume-weighted RSI.

**Logic**:
```
typical_price = (high + low + close) / 3
money_flow = typical_price × volume
positive_flow = sum of money_flow on up days
negative_flow = sum of money_flow on down days
MFI = 100 - (100 / (1 + positive_flow / negative_flow))

BUY:  MFI < 20 with bullish divergence
SELL: MFI > 80 with bearish divergence
```

---

### 23. Force Index

**Concept**: Price change × volume for momentum strength.

**Logic**:
```
force_index = (close - prev_close) × volume
smoothed = EMA(force_index, 13)

BUY:  smoothed crosses above 0
SELL: smoothed crosses below 0
```

---

## Arbitrage Strategies

Arbitrage, in its purest form, is risk-free profit from price discrepancies. If gold trades at $2,000 in New York and $2,010 in London, you buy in New York and sell in London, pocketing $10 risk-free (minus transaction costs).

**The reality**: True arbitrage opportunities are extremely rare and fleeting in modern markets. High-frequency trading firms with microsecond latency and co-located servers gobble up these opportunities instantly. What retail traders call "arbitrage" is usually **statistical arbitrage**—strategies that are market-neutral in expectation but still carry risk.

**The appeal**: Arbitrage strategies aim to be uncorrelated with the broader market. Whether the market goes up or down, you're betting on a spread or relationship, not a direction. This makes them attractive for portfolio diversification.

**The challenge**: These strategies require careful execution, management of multiple positions, and understanding of the statistical relationships you're exploiting. When those relationships break down (regime changes), losses can be sudden and severe.

### 24. Statistical Arbitrage (Pairs Trading)

Pairs trading is the most accessible arbitrage strategy for retail traders. It's based on finding two related assets that move together, waiting for them to diverge, and betting they'll converge again.

```
PAIRS TRADING (SPREAD MEAN REVERSION)

Z-Score
  │
 +2│─────────────────────────────────── SELL SPREAD ───
  │                 ╭╮                  (Short Y, Long X)
 +1│                ││
  │                ╱  ╲
  0│──────────────╱────╲──────────────── EQUILIBRIUM ───
  │              ╱      ╲
 -1│            ╱        ╲
  │    ╭──────╯          ╰───╮
 -2│───╯─────────────────────╰──────── BUY SPREAD ─────
  │                                    (Long Y, Short X)
  └──────────────────────────────────────────────────▶ Time

  Stock Y: ████████  (e.g., Coca-Cola)
  Stock X: ░░░░░░░░  (e.g., Pepsi)

  When spread diverges → Trade    When spread converges → Exit
```

**Concept**: Trade the spread between two cointegrated assets.

**Example**: Consider Coca-Cola (KO) and Pepsi (PEP). Both are in the beverage industry, face similar economic conditions, and tend to move together over time. If something causes KO to drop 5% while PEP stays flat—and there's no company-specific news—you might expect KO to bounce back relative to PEP (or PEP to fall).

The strategy: go long the "cheap" one and short the "expensive" one. You're not betting on the market direction; you're betting that their historical relationship will reassert itself.

**The Math Behind It**:
```
Step 1: Test for cointegration (the pair moves together long-term)
        Use Engle-Granger or Johansen tests
        Cointegration ≠ correlation! Correlation measures short-term co-movement
        Cointegration means they have a stable long-term equilibrium

Step 2: Calculate hedge ratio via OLS regression: Y = β × X + ε
        β tells you how many shares of X to short for each share of Y
        Example: if β = 0.8, short 80 shares of X for every 100 shares of Y

Step 3: Calculate the spread
        spread = Y - (β × X)              # Actual difference
        z_spread = (spread - mean(spread)) / std(spread)  # Standardized

Step 4: Trade the extremes
        BUY SPREAD:  z_spread < -2 (spread is unusually small)
                     Action: long Y, short β × X
        SELL SPREAD: z_spread > +2 (spread is unusually large)
                     Action: short Y, long β × X
        EXIT:        z_spread → 0 (spread returns to normal)
```

**Critical risk**: Cointegration can break. If one company in your pair faces bankruptcy, regulatory issues, or fundamental changes in their business, the historical relationship may never recover. This is not a "set and forget" strategy—you must monitor for regime changes.

---

### 25. Triangular Arbitrage (FX)

**Concept**: Exploit pricing inconsistencies across currency pairs.

```
TRIANGULAR ARBITRAGE

                      EUR
                     ╱   ╲
                    ╱     ╲
           EUR/USD ╱       ╲ EUR/GBP
           1.10   ╱         ╲ 0.85
                 ╱           ╲
                ╱             ╲
              USD ─────────── GBP
                   GBP/USD
                    1.30

The arbitrage loop:
┌─────────────────────────────────────────────────────────┐
│ START: $1,000 USD                                       │
│                                                         │
│ Step 1: Buy EUR with USD                                │
│         $1,000 ÷ 1.10 = €909.09                         │
│                                                         │
│ Step 2: Buy GBP with EUR                                │
│         €909.09 × 0.85 = £772.73                        │
│                                                         │
│ Step 3: Buy USD with GBP                                │
│         £772.73 × 1.30 = $1,004.55                      │
│                                                         │
│ PROFIT: $4.55 risk-free (minus transaction costs)       │
└─────────────────────────────────────────────────────────┘

Reality: These opportunities last milliseconds and require
         ultra-low latency systems to capture
```

**Logic**:
```
Example with USD, EUR, GBP:

Rate1: EUR/USD = 1.10
Rate2: GBP/USD = 1.30
Rate3: EUR/GBP = 0.85

Implied EUR/GBP = (EUR/USD) / (GBP/USD) = 1.10 / 1.30 = 0.846

If actual EUR/GBP = 0.85 ≠ 0.846:
  Arbitrage exists
  Execute three simultaneous trades to capture difference
```

---

### 26. Index Arbitrage

**Concept**: Exploit price difference between index and its components.

**Logic**:
```
theoretical_index = Σ(weight_i × price_i)
actual_index = futures price or ETF price

IF actual > theoretical + transaction_costs:
  Sell index, buy components

IF actual < theoretical - transaction_costs:
  Buy index, sell components
```

---

### 27. ETF Arbitrage

**Concept**: Exploit NAV vs market price discrepancy.

**Logic**:
```
NAV = Net Asset Value (fair value from holdings)
Market_Price = ETF trading price

Premium: Market_Price > NAV → Sell ETF, buy underlying
Discount: Market_Price < NAV → Buy ETF, sell underlying

Authorized Participants can create/redeem ETF shares
```

---

### 28. Merger Arbitrage (Risk Arbitrage)

**Concept**: Trade announced M&A deals.

**Logic**:
```
Acquisition announced: Acquirer buys Target at $50/share
Target currently trades at $48 (spread = $2)

Strategy:
  Long Target at $48
  (Optional) Short Acquirer as hedge

Profit: $2 when deal closes
Risk: Deal breaks, target price drops
```

**Considerations**: Deal probability, timeline, regulatory risk

---

### 29. Convertible Arbitrage

**Concept**: Exploit mispricing between convertible bond and underlying stock.

**Logic**:
```
Convertible bond can be converted to stock at conversion_ratio

Strategy:
  Long convertible bond (undervalued optionality)
  Short Δ shares of underlying stock (delta hedge)

Profit from:
  - Volatility (long gamma)
  - Credit spread compression
  - Mispricing
```

---

### 30. Futures Basis Arbitrage

**Concept**: Trade spot vs futures price discrepancy.

**Logic**:
```
theoretical_futures = spot × e^((r - d) × t)

Where:
r = risk-free rate
d = dividend yield
t = time to expiration

Cash-and-carry: IF futures > theoretical
  Buy spot, sell futures, earn basis

Reverse cash-and-carry: IF futures < theoretical
  Sell spot, buy futures
```

---

## Market Making Strategies

Market makers provide liquidity to the market by continuously offering to buy and sell an asset. They profit from the bid-ask spread—buying at the bid price and selling at the ask price.

**How it works in simple terms**: Imagine you're at a currency exchange booth at an airport. You see a sign: "Buy USD at 1.05 EUR, Sell USD at 1.10 EUR." The exchange makes $0.05 on every dollar that passes through. They don't care if the dollar goes up or down—they make money on the spread.

**The appeal**: Market making can be profitable in all market conditions—up, down, or sideways—as long as there's trading activity. You're paid for providing a service (liquidity) rather than betting on direction.

**The challenges**:
1. **Adverse selection**: Informed traders (who know something you don't) tend to trade against you. If they're buying aggressively, maybe they know the price is about to spike—and you're the fool selling to them.
2. **Inventory risk**: As you buy and sell, you accumulate inventory. If you end up holding a large long position when the market crashes, you lose money.
3. **Competition**: Professional market makers have enormous technological advantages. Unless you're trading in less-competitive markets (crypto, obscure instruments), you're facing stiff competition.

### 31. Basic Market Making

**Concept**: Provide liquidity, earn bid-ask spread.

```
MARKET MAKING: EARNING THE SPREAD

             ORDER BOOK                    YOUR QUOTES
        ─────────────────              ─────────────────

        Ask $100.10  [500]  ◄────────  YOUR ASK $100.10
        Ask $100.08  [200]             (Sell to buyers)
        ─────────────────                    │
          Fair Value                         │ Spread
            $100.00                          │ $0.20
        ─────────────────                    │
        Bid $99.92   [300]                   │
        Bid $99.90   [400]  ◄────────  YOUR BID $99.90
                                       (Buy from sellers)

   When both fill: Bought at $99.90, Sold at $100.10 = $0.20 profit


   INVENTORY SKEW (Risk Management)
   ─────────────────────────────────

   Long inventory?          Short inventory?
   Lower both quotes        Raise both quotes
        │                         │
        ▼                         ▼
   Bid $99.85                Bid $99.95
   Ask $100.05               Ask $100.15
   (Encourage sales)         (Encourage buys)
```

The fundamental market making algorithm: post a bid order (offer to buy) below the current price and an ask order (offer to sell) above the current price. When both orders fill, you've bought low and sold high, pocketing the spread.

**Logic Explained**:
```
Continuously quote:
  bid = fair_value - spread/2    # Your buy offer (below fair value)
  ask = fair_value + spread/2    # Your sell offer (above fair value)

  Example: If fair value is $100 and your spread is $0.20
           bid = $99.90, ask = $100.10
           If both fill, you make $0.20

Fair value estimation (the hard part):
  - Mid-price of order book: (best_bid + best_ask) / 2
  - Microprice: weighted by order sizes at each level
  - Theoretical model: incorporating recent trades, news, etc.

Inventory management (critical for survival):
  IF you're long (bought more than sold):
     Lower your quotes to encourage selling, discourage buying
     Example: Instead of bid $99.90 / ask $100.10
              Quote bid $99.85 / ask $100.05
              Makes people more likely to buy from you (reducing your inventory)

  IF you're short (sold more than bought):
     Raise your quotes to encourage buying, discourage selling
```

**Practical reality**: Market making is highly competitive. Professional firms invest billions in low-latency infrastructure. Retail traders generally cannot compete in traditional markets but may find opportunities in crypto or less-liquid instruments.

---

### 32. Avellaneda-Stoikov Market Making

**Concept**: Optimal quoting with inventory risk.

**Logic**:
```
Reservation price (adjusted fair value):
  r = s - q × γ × σ² × (T - t)

Where:
  s = mid-price
  q = current inventory
  γ = risk aversion parameter
  σ = volatility
  T - t = time remaining

Optimal spread:
  δ = γ × σ² × (T - t) + (2/γ) × ln(1 + γ/k)

Quotes:
  bid = r - δ/2
  ask = r + δ/2
```

---

### 33. Order Flow Toxicity (VPIN)

**Concept**: Detect informed trading to avoid adverse selection.

**Logic**:
```
VPIN = Volume-synchronized Probability of Informed Trading

Classify trades as buy/sell (tick rule or bulk classification)
Calculate buy-sell imbalance per volume bucket

VPIN = Σ|Buy - Sell| / Total_Volume

High VPIN → widen spreads or stop quoting
```

---

## Statistical & Quantitative Strategies

### 34. Factor Investing

**Concept**: Systematic exposure to return-generating factors.

**Common Factors**:
| Factor | Description | Metric |
|--------|-------------|--------|
| Value | Cheap vs expensive | P/E, P/B, EV/EBITDA |
| Size | Small vs large cap | Market cap |
| Momentum | Recent winners | 12-1 month return |
| Quality | Profitable, stable | ROE, earnings stability |
| Low Volatility | Less volatile stocks | Historical σ |
| Dividend Yield | High dividends | Div/Price |

**Implementation**:
```
For each factor:
  Score all stocks on factor metric
  Go long top quintile
  Go short bottom quintile

Multi-factor: Combine z-scores
```

---

### 35. PCA-Based Statistical Arbitrage

**Concept**: Decompose returns into principal components, trade residuals.

**Logic**:
```
1. Calculate correlation matrix of returns
2. Extract principal components (eigenportfolios)
3. First K components ≈ market/sector factors
4. Residual = stock return - factor exposures

Trade mean reversion in residuals (idiosyncratic component)
```

---

### 36. Kalman Filter Pairs Trading

**Concept**: Dynamic hedge ratio estimation.

**Logic**:
```
State equation: β(t) = β(t-1) + w (random walk)
Observation: Y(t) = β(t) × X(t) + v

Kalman filter provides:
  - Time-varying hedge ratio β(t)
  - Uncertainty estimate

Trade spread using dynamic β instead of static OLS β
```

---

### 37. Cointegration-Based Trading

**Concept**: Find long-term equilibrium relationships.

**Testing**:
```
Engle-Granger:
  1. Regress Y on X
  2. Test residuals for stationarity (ADF test)

Johansen:
  - Test for multiple cointegrating relationships
  - Provides number of cointegrating vectors
```

---

### 38. Machine Learning Classification

**Concept**: Predict direction using ML models.

**Features**:
```
Technical: RSI, MACD, BB position, volume ratio
Fundamental: P/E change, earnings surprise
Alternative: sentiment scores, satellite data

Models:
  - Random Forest
  - Gradient Boosting (XGBoost, LightGBM)
  - Neural Networks
  - SVM

Target: Next period return > 0? (binary classification)
        Or: Return quintile (multi-class)
```

---

### 39. Reinforcement Learning Trading

**Concept**: Agent learns optimal actions through reward.

**Framework**:
```
State: Price history, indicators, position, PnL
Actions: Buy, Sell, Hold (or continuous sizing)
Reward: Realized PnL, Sharpe ratio, risk-adjusted return

Algorithms:
  - DQN (Deep Q-Network)
  - A3C (Asynchronous Advantage Actor-Critic)
  - PPO (Proximal Policy Optimization)
```

---

### 40. LSTM / Transformer Price Prediction

**Concept**: Deep learning for sequential data.

**Architecture**:
```
LSTM:
  Input: Sequence of [price, volume, indicators]
  LSTM layers capture temporal dependencies
  Output: Next price / return / direction

Transformer:
  Self-attention for long-range dependencies
  Often better for very long sequences

Temporal Fusion Transformer (TFT):
  Combines known future inputs (calendar)
  With unknown future inputs (prices)
```

---

## Event-Driven Strategies

Event-driven strategies trade around specific corporate or economic events: earnings announcements, FDA approvals, mergers, economic data releases, and more. These strategies attempt to profit from the market's reaction to news.

**Why event-driven works**: Markets don't fully price in the implications of new information immediately. Research shows that after positive earnings surprises, stocks tend to continue drifting upward for weeks—this is called "post-earnings announcement drift" (PEAD). The market underreacts initially.

**The challenges**:
1. **Information asymmetry**: Institutional traders often get information faster than you
2. **Unpredictability**: Events can go either way; even good news can cause selling (buy the rumor, sell the news)
3. **Increased volatility**: Options become expensive around events due to implied volatility spikes
4. **Overnight gaps**: Many events occur outside trading hours, causing gap risk

**Keys to success**: Focus on less-followed events where you have an information edge, use proper position sizing to survive the volatility, and understand that event-driven trading is probabilistic—you won't win every time.

### 41. Earnings Momentum

**Concept**: Trade post-earnings announcement drift (PEAD).

One of the most well-documented market anomalies: when companies report earnings that beat expectations, their stocks tend to continue rising for weeks or months afterward. Similarly, stocks that miss expectations continue falling. This is called "post-earnings announcement drift."

**Why does this happen?** Behavioral finance suggests investors are slow to update their views. They anchor to old expectations and only gradually accept new information. This gradual acceptance causes the drift.

**Logic**:
```
Earnings surprise = (Actual EPS - Expected EPS) / Expected EPS

Example:
  Analysts expected $1.00 EPS
  Company reports $1.20 EPS
  Surprise = ($1.20 - $1.00) / $1.00 = +20%

Strategy:
  BUY if surprise > +10% (big positive surprise)
  SELL if surprise < -10% (big negative surprise)

Hold for drift period (typically 60-90 days)
Exit before next earnings announcement
```

**Practical considerations**:
- The first hour after earnings is chaotic; some traders wait for the dust to settle
- Conference call guidance matters as much as the numbers
- Stocks in the extreme surprise categories (top/bottom decile) show the strongest drift
- This edge has declined over time as more traders exploit it

---

### 42. News Sentiment Trading

**Concept**: Trade on news sentiment analysis.

**Pipeline**:
```
1. Collect news from APIs (Reuters, Bloomberg, Twitter)
2. NLP sentiment scoring (-1 to +1)
3. Aggregate sentiment per asset

BUY:  sentiment > threshold AND increasing
SELL: sentiment < -threshold AND decreasing
```

**Considerations**: Latency critical, fake news filtering

---

### 43. Dividend Capture

**Concept**: Capture dividends with minimal price risk.

**Logic**:
```
Buy stock before ex-dividend date
Receive dividend
Sell after ex-dividend date

Price theoretically drops by dividend amount
Profit if:
  - Price drops less than dividend
  - Dividend income > transaction costs
```

---

### 44. Spin-off Investing

**Concept**: Parent/child dislocations after corporate spin-offs.

**Logic**:
```
After spin-off:
  - Index funds forced to sell (child not in index)
  - Institutions may dump small cap

Buy underpriced child company
Wait for revaluation
```

---

### 45. Insider Trading Following

**Concept**: Follow legal insider transactions (Form 4 filings).

**Logic**:
```
Monitor SEC Form 4 filings
Filter for:
  - Cluster buys (multiple insiders)
  - Large purchases relative to salary
  - C-suite executives

BUY when significant insider buying detected
```

---

### 46. 13F Following (Guru Tracking)

**Concept**: Replicate holdings of successful investors.

**Logic**:
```
Monitor quarterly 13F filings from:
  - Hedge funds
  - Famous investors

Track new positions and increases
Replicate with delay (45-day filing deadline)
```

---

## Sentiment-Based Strategies

Sentiment strategies attempt to gauge the mood of market participants and trade accordingly. The key insight: when sentiment reaches extremes, markets often reverse. When everyone is euphoric, there's no one left to buy—prices fall. When everyone is panicking, there's no one left to sell—prices rise.

**Two approaches to sentiment**:

1. **Contrarian**: Trade against extreme sentiment. Buy when fear is extreme; sell when greed is extreme. "Be fearful when others are greedy, and greedy when others are fearful." – Warren Buffett

2. **Momentum**: Trade with sentiment. Rising optimism can create self-fulfilling rallies. Deteriorating sentiment can cascade into crashes. Sometimes the crowd is right, and fighting it is costly.

**Sources of sentiment data**:
- Options markets (put/call ratios)
- Volatility indexes (VIX = "fear gauge")
- Surveys (AAII, Investors Intelligence)
- Social media (Twitter, Reddit, StockTwits)
- News sentiment (NLP on headlines)
- Fund flows (money moving in/out of funds)

**The challenge**: Sentiment is a soft indicator. It doesn't give precise entry/exit signals and can remain extreme for extended periods. Best used as a filter or confirmation rather than a primary signal.

### 47. Put/Call Ratio Contrarian

**Concept**: Extreme options sentiment as contrary indicator.

The put/call ratio measures whether traders are buying more puts (bearish bets) or calls (bullish bets). When everyone is buying puts to protect against downside, it suggests fear is high—often a good time to buy. When everyone is buying calls, optimism is extreme—often a warning sign.

**Logic**:
```
put_call_ratio = put_volume / call_volume

Normal range: 0.8 - 1.0
Most traders buy more calls than puts in normal conditions

Contrarian signals:
  BUY:  PCR > 1.2 (extreme fear, everyone buying protection)
        The masses are panicking—historically a good time to buy

  SELL: PCR < 0.7 (extreme greed, everyone betting on upside)
        The masses are euphoric—historically a warning sign

Why contrarian works here:
  - At extremes, the "smart money" is often on the other side
  - When everyone has already bought puts, who's left to sell?
  - When everyone has already bought calls, who's left to buy?
```

**Important nuance**: Use multi-day moving averages (5-day or 10-day PCR) rather than single-day readings, which are noisy. Also distinguish between equity PCR and index PCR—they can tell different stories.

---

### 48. VIX Mean Reversion

**Concept**: Volatility tends to mean-revert.

**Logic**:
```
VIX spike → sell volatility (VIX will fall)
VIX crush → buy volatility (VIX will rise)

Instruments: VIX futures, VXX, UVXY, SVXY
Warning: Vol can spike much higher than expected
```

---

### 49. Social Media Sentiment

**Concept**: Aggregate sentiment from social platforms.

**Data Sources**:
- Twitter/X: Real-time chatter
- Reddit: WallStreetBets, investing subreddits
- StockTwits: Purpose-built for stocks

**Logic**:
```
sentiment_score = (bullish_posts - bearish_posts) / total_posts

BUY:  sentiment rapidly increasing from low level
SELL: sentiment at extreme high (contrarian)

Watch for: Momentum play (trend) vs contrarian (reversal)
```

---

### 50. AAII Sentiment Survey

**Concept**: Retail investor sentiment indicator.

**Logic**:
```
AAII reports weekly: % Bullish, % Bearish, % Neutral

Contrarian:
  BUY:  Bearish > 50% (extreme pessimism)
  SELL: Bullish > 60% (extreme optimism)
```

---

## Seasonal & Calendar Strategies

Markets exhibit predictable patterns based on the calendar—days of the week, months of the year, holidays, and more. While these patterns aren't as strong as they once were (they get arbitraged as they become well-known), they still provide useful context and occasional edges.

**Why calendar effects exist**:
- **Tax considerations**: Investors sell losers in December (tax-loss harvesting), then buy back in January
- **Institutional behavior**: Fund managers "window dress" at quarter-end, buying winners to show in reports
- **Human behavior**: Traders are optimistic before holidays, distracted on certain days
- **Cash flows**: Salaries are paid monthly, 401(k) contributions happen regularly

**Caution about calendar effects**:
- Many have diminished or disappeared as they became widely known
- Transaction costs can eat up small seasonal edges
- Sample sizes are often small (how many Januaries in your backtest?)
- Spurious correlations abound (avoid data mining)

**Best use**: As a secondary filter or confirmation, not a primary strategy. For example, if your trend system gives a buy signal in late December for a beaten-down small cap, the January Effect provides tailwind.

### 51. January Effect

**Concept**: Small caps outperform in January.

The January Effect is one of the oldest documented market anomalies, first identified in 1942. Small-cap stocks have historically delivered outsized returns in January compared to large caps.

**Why it happens**:
```
December: Tax-loss selling depresses small caps
  - Investors sell losing positions to realize losses for tax purposes
  - Small caps are hit hardest because they're most volatile (more losers)
  - Institutional investors do "window dressing," selling embarrassing positions

January: Buying pressure returns
  - Tax selling ends on December 31
  - Investors reinvest proceeds
  - New year, fresh allocations, optimism
  - "January bargains" attract value buyers

Strategy:
  Buy small caps (IWM, small cap ETF) late December
  Sell late January

Historical performance:
  Small caps have beaten large caps in January about 60-70% of years
  The effect is strongest in the first few trading days
```

**Reality check**: The January Effect has weakened significantly since it became widely known. Some years it works; some years it doesn't. Don't bet the farm on it.

---

### 52. Sell in May (Halloween Indicator)

**Concept**: Market performs better November-April.

This is perhaps the most famous calendar effect, with roots going back to London in the 1930s. The full saying is "Sell in May and go away, come back on St. Leger's Day" (St. Leger's Day is a British horse race in September).

**The Evidence**:
```
Historical data shows:
  November - April average return: ~7%
  May - October average return: ~2%

The difference is significant and persistent across many markets and decades.
```

**Why it might work**:
```
Several theories (none definitive):
- Summer vacations reduce trading activity and liquidity
- Institutional investors "de-risk" before summer holidays
- Earnings season concentration in fall creates catalysts
- Bonus-driven buying at year-end
- Self-fulfilling prophecy as traders believe in it
```

**Strategy**:
```
Simple version:
  Long stocks: November 1 through April 30
  Cash or bonds: May 1 through October 31

Enhanced version:
  Only go to cash in May if trend is weakening
  Stay invested if strong uptrend persists

Surprisingly, this simple strategy has beaten buy-and-hold in many
historical tests, mostly by avoiding some big crashes that occurred in
summer/fall (1929, 1987, 2008).
```

**Caution**: There's no guarantee this will continue to work, and following it rigidly means missing gains in good summer months.

---

### 53. Turn of Month Effect

**Concept**: Markets rise around month end/start.

**Logic**:
```
Buy: Last day of month through 3rd day of next month
Sell: Rest of month

Drivers: Salary investments, portfolio rebalancing
```

---

### 54. Monday Effect / Day-of-Week

**Concept**: Historical day-of-week patterns.

**Historical Patterns**:
```
Monday: Historically negative (weekend news, selling)
Friday: Historically positive (weekend optimism)

Note: Effect has diminished in recent decades
```

---

### 55. Pre-Holiday Effect

**Concept**: Markets rise before holidays.

**Logic**:
```
Buy day before:
  - Christmas
  - Thanksgiving
  - Independence Day
  - Labor Day

Short sellers cover, optimism rises
```

---

### 56. Options Expiration Effects

**Concept**: Price pinning and volatility around expiry.

**Logic**:
```
Max Pain: Price where option writers have minimum payout
Markets tend toward max pain near expiration

Gamma exposure: Dealer hedging moves markets
Quad witching: Increased volatility
```

---

### 57. End of Quarter Window Dressing

**Concept**: Fund managers buy winners before reporting.

**Logic**:
```
Last week of quarter:
  Managers buy recent winners (to show in reports)
  Managers sell losers (to hide mistakes)

First week of new quarter:
  Reversal as artificial demand ends
```

---

## Volume-Based Strategies

Volume tells you how much conviction is behind price moves. A big price move on heavy volume is more significant than the same move on light volume. Volume-based strategies use this insight to confirm trends, spot divergences, and identify potential reversals.

**Core principle**: "Volume precedes price"

Volume often increases before price makes a major move. Accumulation (buying) shows up as rising volume on up days. Distribution (selling) shows up as rising volume on down days. Watching volume can give you early warning of trend changes.

**Volume indicators answer questions like**:
- Is the smart money accumulating or distributing?
- Is this breakout real or a "fake out"?
- Is the trend exhausting (losing volume) or strengthening?
- Where are the high-activity price levels (support/resistance)?

**The challenge**: Volume data can be noisy and interpretation is subjective. Volume analysis works best as confirmation for other signals rather than as a standalone system.

### 58. On-Balance Volume (OBV)

OBV was developed by Joseph Granville in the 1960s and remains one of the simplest and most effective volume indicators.

**Concept**: Cumulative volume as trend confirmation.

OBV creates a running total of volume, adding volume on up days and subtracting on down days. The theory: when OBV is rising, buyers are willing to step in on up days with conviction. When OBV is falling, sellers dominate.

**Logic**:
```
IF close > prev_close: OBV += volume  (buyers won today, add their volume)
IF close < prev_close: OBV -= volume  (sellers won today, subtract volume)
IF close = prev_close: OBV unchanged

The absolute value of OBV doesn't matter—watch the trend and divergences.
```

**How to use OBV**:
```
Trend confirmation:
  - Price rising + OBV rising = healthy uptrend, continue holding
  - Price falling + OBV falling = healthy downtrend, stay out or short

Divergence (early warning signals):
  - Price making higher highs BUT OBV making lower highs
    → Bearish divergence: buyers are weakening, potential top
    → "Distribution" - smart money selling into strength

  - Price making lower lows BUT OBV making higher lows
    → Bullish divergence: sellers are exhausting, potential bottom
    → "Accumulation" - smart money buying weakness

Example:
  Stock rallies from $100 to $120 over 3 weeks (new high)
  But OBV fails to make a new high
  → Warning: this rally lacks conviction, might reverse
```

**Practical tip**: OBV works best on daily or weekly charts. Intraday OBV can be very noisy.

---

### 59. Volume Profile / Market Profile

**Concept**: Identify price levels with high activity.

```
VOLUME PROFILE

Price │                          Volume traded at each price
      │
$105 ─┼─ ████                    ← Low Volume Node (LVN)
      │   (price moves fast)        Weak support/resistance
$104 ─┼─ ████████
      │
$103 ─┼─ ████████████████        ← High Volume Node (HVN)
      │   Strong resistance
$102 ─┼─ ██████████████████████  ← Point of Control (POC)
      │   HIGHEST VOLUME             Most traded price
$101 ─┼─ ████████████████        ← High Volume Node (HVN)
      │   Strong support       ┐
$100 ─┼─ ██████████             │ VALUE AREA
      │                        │ (70% of volume)
 $99 ─┼─ ████████              ┘
      │
 $98 ─┼─ ███                     ← Low Volume Node (LVN)
      │
      └────────────────────────────▶

Trading approach:
  • Buy at lower Value Area edge (support)
  • Sell at upper Value Area edge (resistance)
  • Breakout trade when price escapes Value Area
```

**Concepts**:
```
Value Area: Price range with 70% of volume
Point of Control (POC): Highest volume price level
High Volume Nodes (HVN): Support/resistance
Low Volume Nodes (LVN): Price moves quickly through

Trading:
  Buy near lower value area edge
  Sell near upper value area edge
  Breakout when price leaves value area
```

---

### 60. Volume Weighted Average Price (VWAP)

**Concept**: Fair price benchmark based on volume.

```
VWAP AS SUPPORT/RESISTANCE

Price
  │
  │        ╭──╮
  │       ╱    ╲       SELL zone
  │      ╱      ╲     (price > VWAP)
  │     ╱        ╲
  │════════════════════════════════ VWAP (Fair Value)
  │   ╱            ╲
  │  ╱   BUY zone   ╲
  │ ╱  (price < VWAP) ╲
  │╱                    ╲
  │
  └──────────────────────────────▶ Time (intraday)

  • VWAP resets each day
  • Institutional traders use VWAP as execution benchmark
  • Price tends to gravitate toward VWAP
```

**Logic**:
```
VWAP = Σ(price × volume) / Σ(volume)

Trading:
  BUY:  price < VWAP (below fair value)
  SELL: price > VWAP (above fair value)

Institutional: Benchmark for execution quality
```

---

### 61. Accumulation/Distribution Line

**Concept**: Measure buying vs selling pressure.

**Logic**:
```
money_flow_multiplier = ((close - low) - (high - close)) / (high - low)
money_flow_volume = multiplier × volume
A/D Line = cumulative sum of money_flow_volume

Divergence signals similar to OBV
```

---

### 62. Chaikin Money Flow

**Concept**: Net buying/selling pressure over period.

**Logic**:
```
CMF = Sum(money_flow_volume, 21) / Sum(volume, 21)

BUY:  CMF > 0 (buying pressure)
SELL: CMF < 0 (selling pressure)
```

---

## Machine Learning Strategies

Machine learning (ML) has become increasingly popular in algorithmic trading, with the promise of finding patterns that humans (and simple rules) miss. However, applying ML to trading is notoriously difficult.

**Why ML is appealing**: Markets generate massive amounts of data. Traditional rule-based strategies only use a tiny fraction of this information. ML models can potentially process much more data and find complex, non-linear relationships.

**Why ML is hard in trading**:

1. **Non-stationarity**: Unlike image recognition (a cat today looks like a cat from 10 years ago), market patterns change. What worked in 2015 may not work in 2025.

2. **Low signal-to-noise ratio**: Markets are extremely noisy. Most price movements are random. Extracting signal is much harder than in domains where ML has achieved breakthrough success.

3. **Overfitting paradise**: With thousands of potential features and millions of data points, it's easy to find patterns that fit historical data perfectly but have no predictive power.

4. **Adversarial environment**: If you find a pattern, others will too. Once a pattern becomes widely known, it gets arbitraged away.

5. **Regime changes**: A model trained during a bull market may fail spectacularly in a crash.

**Best practices for ML in trading**:
- Use simple models first; complex models overfit more easily
- Rigorous out-of-sample testing (walk-forward validation)
- Focus on robust features with economic intuition
- Monitor for decay in model performance

### 63. Feature Engineering for Finance

**Common Features**:
```
Price-based:
  - Returns (log, simple)
  - Volatility (realized, rolling)
  - Technical indicators

Volume-based:
  - Volume ratio (current/average)
  - Dollar volume
  - Bid-ask spread

Cross-sectional:
  - Relative strength rank
  - Sector performance
  - Market beta

Alternative data:
  - Sentiment scores
  - Satellite imagery
  - Credit card data
  - Web traffic
```

---

### 64. Walk-Forward Optimization

**Concept**: Realistic out-of-sample testing.

**Process**:
```
1. Train on period 1-12
2. Test on period 13
3. Train on period 2-13
4. Test on period 14
...continue walking forward

Combines in-sample training with out-of-sample validation
```

---

### 65. Ensemble Methods

**Concept**: Combine multiple models/strategies.

**Approaches**:
```
Model averaging:
  prediction = (model1 + model2 + model3) / 3

Stacking:
  Meta-model learns optimal combination

Voting:
  BUY only if majority of models agree
```

---

### 66. Regime Detection

**Concept**: Identify market regimes, adapt strategy.

**Methods**:
```
Hidden Markov Models (HMM):
  - Learn latent states (bull, bear, sideways)
  - Switch strategies based on detected regime

Clustering:
  - K-means on volatility, correlation, trend
  - Assign current period to cluster
```

---

## Options-Based Strategies

Options provide unique capabilities that aren't possible with stocks alone. You can profit from moves in either direction, generate income while holding stocks, protect positions against losses, and express views on volatility rather than just direction.

**Why learn options strategies?**

1. **Defined risk**: Many options strategies have a known maximum loss. You can never lose more than your initial investment, even if the stock goes to zero.

2. **Leverage**: Control 100 shares of stock for a fraction of the cost. This amplifies returns (both ways).

3. **Non-directional trades**: Profit from volatility or lack thereof, regardless of which direction the market moves.

4. **Income generation**: Sell options to collect premium, earning money while waiting for your price targets.

**The catch**: Options expire, have time decay working against long positions, and can be complex to understand and trade. Most beginners lose money on options until they develop proper understanding.

**Key concept: The four basic positions**:
- Buy call = Bullish, limited loss, unlimited gain
- Sell call = Neutral/Bearish, limited gain, potentially large loss
- Buy put = Bearish, limited loss, large gain potential
- Sell put = Bullish/Neutral, limited gain, large loss potential

### 67. Covered Call (Buy-Write)

The covered call is often the first options strategy beginners learn because it's relatively straightforward and reduces risk compared to holding stock alone.

**Concept**: Own stock, sell upside calls against it for income.

**Real-world analogy**: You own a house worth $500,000. You sell someone an option to buy it for $550,000 anytime in the next year, and they pay you $10,000 for this right. If your house value stays below $550,000, you keep the $10,000 premium. If it rises to $600,000, they exercise the option and you sell at $550,000, missing out on $50,000 upside—but you still made money.

**Logic**:
```
Hold 100 shares of stock at $150
Sell 1 call option with strike $160 for $2 premium ($200 total)

Scenarios:
1. Stock stays at $150: Option expires worthless, you keep $200 premium
2. Stock falls to $140: You lose $1000 on stock but keep $200 premium (net -$800)
3. Stock rises to $155: Option expires worthless, you profit $500 + $200 = $700
4. Stock rises to $170: Option is exercised, you sell at $160
   Stock gain: $1000, Premium: $200, Total: $1200
   But you missed: $1000 of upside (170-160)

Max profit: (Strike - Entry) + Premium = ($160-$150) + $2 = $12/share
Max loss: Entry - Premium = $150 - $2 = $148/share (stock goes to zero)
```

**When to use**: When you're mildly bullish or neutral on a stock you own. You're willing to cap your upside in exchange for guaranteed income now. Works best in flat or slowly rising markets.

---

### 68. Protective Put

**Concept**: Own stock, buy downside protection.

**Logic**:
```
Hold 100 shares of stock
Buy 1 ATM or OTM put option

Profit: Unlimited upside, limited downside
Cost: Put premium
```

---

### 69. Iron Condor

**Concept**: Sell volatility, profit from range-bound market.

```
IRON CONDOR: PROFIT/LOSS DIAGRAM

Profit
  │
  │         ┌─────────────────────┐
  │         │   MAX PROFIT ZONE   │
  │         │    (keep credit)    │
+$120 ──────┼─────────────────────┼───────
  │        ╱│                     │╲
  │       ╱ │                     │ ╲
  0 ─────╱──┼─────────────────────┼──╲─────
  │     ╱   │                     │   ╲
  │    ╱    │                     │    ╲
  │   ╱     │                     │     ╲
-$380 ─────────────────────────────────────
  │   │     │                     │     │
  │  $90   $95       $100       $105  $110
  │   │     │                     │     │
  │   └─────┴─────────────────────┴─────┘
  │   Buy   Sell     Stock       Sell  Buy
  │   Put   Put      Price       Call  Call
  │
  └────────────────────────────────────────▶ Stock Price

  Win: Stock stays between $95-$105
  Lose: Stock breaks outside $90-$110
```

This strategy bets that the stock will stay within a range until expiration. It's a favorite of income-focused options traders because it has a high win rate (markets stay in ranges more often than they break out). However, when it loses, it can lose big.

**Real-world analogy**: You're an insurance company. You bet that nothing catastrophic will happen. Most of the time you collect premiums and everything's fine. Occasionally there's a disaster and you pay out heavily.

**Structure Explained**:
```
Say stock is at $100. You think it will stay between $90 and $110.

Sell $95 put at $1.00   ← Collecting premium, promising to buy at $95
Buy $90 put at $0.40    ← Insurance in case stock crashes below $90
Sell $105 call at $1.00 ← Collecting premium, promising to sell at $105
Buy $110 call at $0.40  ← Insurance in case stock rockets above $110

Net credit: $1.00 + $1.00 - $0.40 - $0.40 = $1.20 per share ($120 total)

Scenarios:
1. Stock stays between $95-$105: All options expire worthless, keep $120 ✓
2. Stock drops to $92: You must buy at $95 (losing $3) but keep $1.20
   Net loss: $180. Your $90 put limits further loss.
3. Stock rises to $107: You must sell at $105 (losing $2 vs market) but keep $1.20
   Net loss: $80. Your $110 call limits further loss.

Max profit: Net credit = $120
Max loss: Width of spread - credit = ($95-$90) - $1.20 = $3.80/share = $380
```

**When to use**: When you expect low volatility and sideways price action. Avoid before earnings, major announcements, or when VIX is spiking.

---

### 70. Straddle/Strangle

**Concept**: Profit from large moves regardless of direction.

```
LONG STRADDLE P/L DIAGRAM

Profit
  │
  │ ╲                               ╱
  │  ╲                             ╱
  │   ╲     Profit if price       ╱
  │    ╲    moves enough in      ╱
  │     ╲   EITHER direction    ╱
  │      ╲                     ╱
  0 ──────╲───────────────────╱────────
  │        ╲                 ╱
  │         ╲   MAX LOSS    ╱
  │          ╲ (premium)   ╱
-$500 ────────╲───────────╱────────────
  │            ╲         ╱
  │             ╲       ╱
  │              ╲     ╱
  │               ╲   ╱
  │                ╲ ╱
  │                 V  ← Strike price ($100)
  │
  └──────────────────────────────────────▶ Stock Price
           $80      $100      $120

  Best for: Expecting BIG move, unsure of direction
            (earnings, FDA decisions, elections)


STRADDLE vs STRANGLE

           STRADDLE                    STRANGLE
        (ATM call + put)           (OTM call + put)

           ╲     ╱                    ╲         ╱
            ╲   ╱                      ╲       ╱
             ╲ ╱                        ╲     ╱
              V                          ╲   ╱
         $100 strike                      ╲─╱
                                    $95 put  $105 call

  Higher premium                   Lower premium
  Lower breakeven                  Higher breakeven
  More sensitive                   Cheaper but needs
  to small moves                   bigger move to profit
```

**Long Straddle**:
```
Buy ATM call
Buy ATM put
Same expiration

Profit if |move| > premium paid
```

**Long Strangle**:
```
Buy OTM call
Buy OTM put
Cheaper than straddle, needs bigger move
```

---

### 71. Calendar Spread

**Concept**: Profit from time decay differential.

**Structure**:
```
Sell near-term option
Buy same-strike longer-term option

Profit: Near-term decays faster
Best when: Low volatility, price near strike
```

---

### 72. Volatility Arbitrage

**Concept**: Trade implied vs realized volatility.

**Logic**:
```
implied_vol = option-implied volatility
realized_vol = historical/forecast volatility

IF implied > realized (expensive options):
  Sell options, delta-hedge with stock

IF implied < realized (cheap options):
  Buy options, delta-hedge

Gamma scalping: Adjust delta hedge, profit from moves
```

---

### 73. Dispersion Trading

**Concept**: Trade index volatility vs component volatility.

**Logic**:
```
Usually: Index vol < weighted average component vol
         (Correlation < 1 provides diversification)

If correlation is HIGH:
  Sell index options, buy component options

If correlation is LOW:
  Buy index options, sell component options
```

---

## Execution Algorithms

### 74. TWAP (Time-Weighted Average Price)

**Concept**: Spread order evenly over time.

**Logic**:
```
total_quantity = 10,000 shares
duration = 60 minutes
interval = 1 minute

Each minute: execute 10,000 / 60 = 167 shares

Goal: Minimize timing risk, not market impact
```

---

### 75. VWAP (Volume-Weighted Average Price)

**Concept**: Trade proportionally to historical volume.

**Logic**:
```
Predict volume distribution using historical pattern
Allocate shares to each interval proportionally

Example: If 10am-11am typically has 10% of daily volume
         Execute 10% of order during that hour

Goal: Match VWAP benchmark
```

---

### 76. Implementation Shortfall (Arrival Price)

**Concept**: Minimize slippage from decision price.

**Logic**:
```
Benchmark: Price when decision was made (arrival price)
Urgency: Based on volatility, alpha decay, risk

Trade-off:
  Fast execution: More impact, less timing risk
  Slow execution: Less impact, more timing risk

Optimize schedule to minimize expected cost
```

---

### 77. Iceberg / Hidden Orders

**Concept**: Show only small portion of large order.

**Logic**:
```
Total order: 100,000 shares
Display quantity: 1,000 shares

When display fills, replenish from reserve
Prevents showing hand to market
```

---

### 78. Smart Order Routing (SOR)

**Concept**: Find best execution across venues.

**Logic**:
```
Check prices at:
  - NYSE
  - NASDAQ
  - BATS
  - IEX
  - Dark pools

Route to venue with best price
Consider: Fees/rebates, latency, fill probability
```

---

## Risk Management Framework

```
RISK MANAGEMENT HIERARCHY

┌─────────────────────────────────────────────────────────────┐
│                    PORTFOLIO LEVEL                          │
│  • Max total exposure (e.g., 100% of capital)               │
│  • Max correlation between positions                        │
│  • Max drawdown limit (stop trading if exceeded)            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    POSITION LEVEL                           │
│  • Max position size (e.g., 10% per trade)                  │
│  • Risk per trade (e.g., 1-2% of account)                   │
│  • Sector/asset concentration limits                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     TRADE LEVEL                             │
│  • Stop loss (defined before entry)                         │
│  • Take profit targets                                      │
│  • Time-based exits                                         │
└─────────────────────────────────────────────────────────────┘


POSITION SIZING FORMULA

    ┌────────────────────────────────────────────┐
    │                                            │
    │           Account × Risk %                 │
    │  Shares = ────────────────────             │
    │           Entry Price - Stop Price         │
    │                                            │
    └────────────────────────────────────────────┘

    Example: $100,000 × 1% ÷ $5 stop = 200 shares
```

**Risk management is more important than entry signals.** This cannot be overstated. You can have the best entry signals in the world, but without proper risk management, one bad trade can wipe out months of profits—or your entire account.

Many beginners focus obsessively on finding the "perfect" entry while neglecting risk management. Professional traders do the opposite: they know that any reasonable entry system can be profitable with excellent risk management, while even the best entries fail without it.

**Key principles of risk management**:

1. **Never risk more than you can afford to lose**: Your position sizes should be small enough that a string of losses doesn't knock you out of the game.

2. **Define your exit before you enter**: Know exactly where your stop loss is before you place a trade. Never move stops to avoid a loss.

3. **Diversify**: Don't put all your capital in one trade, one sector, or one strategy.

4. **Respect correlation**: Ten "different" positions might all lose money together if they're correlated (e.g., all tech stocks).

5. **Expect drawdowns**: Even the best strategies have losing periods. Plan for them psychologically and financially.

### 79. Position Sizing Methods

Position sizing answers the question: "How much capital should I allocate to this trade?" It's arguably the most important decision you make.

**Fixed Fractional** (Most Common for Retail Traders):

The idea: risk a fixed percentage of your account on each trade. If you're wrong, you lose that percentage. This automatically adjusts your position sizes as your account grows or shrinks.

```
position_size = account × risk_percent / risk_per_unit
risk_per_unit = entry_price - stop_price

Example: $100,000 account, 1% risk ($1,000), $5 stop distance
position_size = $1,000 / $5 = 200 shares

If the trade hits your stop loss, you lose exactly $1,000 (1% of account)
After 5 consecutive losses at 1%, your account is $95,099 (not $95,000 due to compounding)
This lets you survive extended drawdowns
```

**Kelly Criterion** (Theoretically Optimal but Aggressive):

The Kelly formula tells you the mathematically optimal bet size to maximize long-term growth. However, it produces very aggressive position sizes that most traders find too volatile.

```
f* = (p × b - q) / b

Where:
p = probability of winning (say 55% = 0.55)
q = probability of losing (1 - p = 0.45)
b = win/loss ratio (say you make $1.20 for every $1 risked = 1.2)

f* = (0.55 × 1.2 - 0.45) / 1.2 = (0.66 - 0.45) / 1.2 = 0.175 = 17.5%

Full Kelly says bet 17.5% of your bankroll!
This is too aggressive—one bad streak can devastate you.
Half-Kelly (8.75%) or Quarter-Kelly (4.4%) is more practical.
```

**Volatility-Based (Turtle Method)** (Best for Multi-Asset Portfolios):

This method normalizes risk across different assets. Whether you're trading volatile crypto or stable bonds, each position risks the same dollar amount.

```
N = ATR(20)  # Average True Range over 20 days = volatility measure
Unit = (1% of account) / (N × dollars_per_point)

Example comparing two assets:
Asset A: ATR = $2, dollars/point = $100 → Unit = $1000 / ($2 × $100) = 5 contracts
Asset B: ATR = $0.50, dollars/point = $100 → Unit = $1000 / ($0.50 × $100) = 20 contracts

More volatile assets get smaller positions.
All positions have the same risk-adjusted size.
```

---

### 80. Stop Loss Strategies

```
STOP LOSS TYPES COMPARED

Price
  │
  │                    ╭───── Highest high ($120)
  │                 ╭──╯
  │              ╭──╯        ┄┄┄┄┄ Trailing stop follows
  │           ╭──╯                 (stays 2 ATR below high)
  │        ╭──╯              ┄┄┄┄┄ $114 (Chandelier: $120 - 2×ATR)
  │     ╭──╯
  │  ╭──╯
  │──╯   ← Entry at $100
  │
  │─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ $95 (Fixed 5% stop)
  │
  │─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ $94 (ATR-based: $100 - 2×$3)
  │
  │══════════════════════════ $92 (Support level stop)
  │
  └────────────────────────────────────────────────────▶ Time


TRAILING STOP IN ACTION

  │
  │                    ╭──╮
  │                 ╭──╯  │
  │              ╭──╯     ╰─── Price reverses
  │           ╭──╯          ╲
  │        ╭──╯              ╲
  │     ╭──╯    ┄┄┄┄┄┄┄┄┄┄┄┄┄┄╳ Stop triggered!
  │  ╭──╯       Trailing stop    Lock in profit
  │──╯          (never moves down)
  │
  └────────────────────────────────────────────────────▶
```

**Fixed Percentage**:
```
stop = entry × (1 - stop_percent)
```

**ATR-Based**:
```
stop = entry - (multiplier × ATR)
Typically: 2-3 ATR
```

**Support-Based**:
```
stop = below nearest support level
```

**Chandelier Exit**:
```
trailing_stop = highest_high - (multiplier × ATR)
```

---

### 81. Portfolio Risk Measures

**Value at Risk (VaR)**:
```
VaR = Expected loss at confidence level over time period
Example: 1-day 95% VaR of $1M means 5% chance of losing $1M+ in a day

Methods:
  - Historical simulation
  - Parametric (variance-covariance)
  - Monte Carlo
```

**Expected Shortfall (CVaR)**:
```
Average loss beyond VaR
More informative about tail risk
```

**Maximum Drawdown**:

```
UNDERSTANDING DRAWDOWN

Account
Value
  │
$150k ┼                  ╭── Peak ($150k)
      │               ╭──╯
      │            ╭──╯
$130k ┼─        ╭──╯
      │  ╲   ╭──╯
      │   ╲ ╱
$120k ┼    ╳
      │    │╲
      │    │ ╲
$100k ┼────│──╲─────────────────── Trough ($100k)
      │    │   ╲     ╱
      │    │    ╲   ╱
 $90k ┼    │     ╲ ╱
      │    │      ╲    Recovery begins
      │    │
      │    └──────────── Drawdown = ($150k - $100k) / $150k
      │                           = 33.3%
      │
      └────────────────────────────────────────▶ Time

  Max Drawdown: Largest peak-to-trough decline
  Recovery time: How long to get back to previous peak

  Rule of thumb: Can you emotionally handle 2x your
  backtested max drawdown? (Live trading is harder)
```

```
max_drawdown = max(peak - trough) / peak
Track rolling drawdown, stop trading if threshold hit
```

---

### 82. Correlation and Diversification

**Correlation Matrix**:
```
Monitor pairwise correlations
Limit exposure to highly correlated positions
```

**Factor Exposure**:
```
Decompose portfolio into factor exposures
Limit unintended factor bets
```

---

### 83. Leverage and Margin

**Key Concepts**:
```
Gross exposure = |Long| + |Short|
Net exposure = Long - Short
Leverage = Gross exposure / Capital

Example:
  $100K long, $50K short, $100K capital
  Gross = $150K, Net = $50K
  Leverage = 1.5x

Margin requirements vary by broker and asset
```

---

## Backtesting Considerations

```
BACKTESTING WORKFLOW

┌──────────────────────────────────────────────────────────────┐
│                      HISTORICAL DATA                         │
│  ├── Training Set (60%) ──┬── Validation (20%) ──┬── Test (20%)
│  │   Develop strategy     │   Tune parameters    │   Final check
│  │   2015-2019            │   2020-2021          │   2022-2024
└──────────────────────────────────────────────────────────────┘
        │                           │                    │
        ▼                           ▼                    ▼
┌──────────────┐           ┌──────────────┐     ┌──────────────┐
│   DEVELOP    │           │    REFINE    │     │   VALIDATE   │
│              │           │              │     │              │
│ • Hypothesis │──────────▶│ • Optimize   │────▶│ • Final test │
│ • Code logic │           │ • Walk-fwd   │     │ • NO CHANGES │
│ • Initial    │           │ • Check      │     │ • Pass/Fail  │
│   results    │           │   robustness │     │   decision   │
└──────────────┘           └──────────────┘     └──────────────┘


WALK-FORWARD TESTING (Proper Validation)

     Train      Test    Train      Test    Train      Test
    ┌──────┐   ┌──┐    ┌──────┐   ┌──┐    ┌──────┐   ┌──┐
    │██████│───│▒▒│    │██████│───│▒▒│    │██████│───│▒▒│
    └──────┘   └──┘    └──────┘   └──┘    └──────┘   └──┘
    2015-16    2017    2016-17    2018    2017-18    2019
                │                  │                  │
                └────── Roll forward in time ─────────┘
                        Combine all test results
```

Backtesting is the process of testing a trading strategy on historical data to see how it would have performed. It's essential—you'd never launch a strategy without backtesting it first—but it's also fraught with pitfalls that can give you false confidence.

**Why backtesting is both essential and dangerous**:

A backtest can show you that a strategy would have made 50% per year for the last 10 years. Amazing! But that same strategy might lose money going forward. Why? Because backtesting has numerous biases that inflate apparent performance, and because past performance genuinely doesn't guarantee future results—markets change.

The goal of backtesting is NOT to prove that a strategy works. The goal is to try to prove that it DOESN'T work and fail to do so. This adversarial mindset protects you from overconfidence.

**Good practices**:
- Use realistic transaction costs (commissions, spread, slippage)
- Test on multiple time periods and market conditions
- Hold out recent data for final validation (don't peek!)
- Be skeptical of strategies that only work with specific parameters
- Ask: "Does this make economic sense? Why would this edge persist?"

### 84. Common Pitfalls

These are the traps that make backtests look better than reality. Every one of these has fooled professional quants—be paranoid about avoiding them.

**Look-Ahead Bias**:
```
Using future information not available at decision time.

Example 1: Using adjusted closing prices before the adjustment occurred.
  If a stock splits 2:1 on June 15, the historical prices get adjusted.
  But on June 14, you didn't know the split was coming.
  Using adjusted data for decisions before June 15 is cheating.

Example 2: Using fundamental data before it was released.
  Q2 earnings are announced August 5, but your model uses them for trades in July.

Solution: Always ask "Could I have known this at the time of the trade?"
```

**Survivorship Bias**:
```
Only testing on stocks that survived to present.

If you download "S&P 500 stocks" today and backtest over 20 years,
you're only testing stocks that are in the S&P 500 NOW.
What about Enron, Lehman Brothers, or hundreds of other companies
that were once in the index but went bankrupt or were acquired?

Your backtest looks great because you're only trading "winners" (survivors).
In reality, you would have lost money on the failures.

Solution: Use point-in-time databases that include delisted stocks.
```

**Overfitting** (The Silent Killer):
```
Too many parameters fit to historical noise, not signal.

Example: You test 1000 different parameter combinations.
One shows 100% annual returns! Is it real or luck?
With 1000 tries, you'd EXPECT to find some amazing results by chance.

Signs of overfitting:
- Performance degrades outside the test period
- Sensitive to small parameter changes
- No logical reason for specific parameter values
- Many parameters relative to number of trades

Solution:
- Keep strategies simple (fewer parameters)
- Use walk-forward testing
- Demand economic intuition for why it should work
- Test on completely fresh data at the very end
```

**Transaction Costs** (Death by a Thousand Cuts):
```
Many strategies look profitable until you add realistic costs.

Must include:
  - Commissions: Often $0 now, but not always
  - Bid-ask spread: You buy at ask, sell at bid. This cost is real.
    Example: If spread is $0.05 and you trade 100 times, you lose $5 × 100 = $500
  - Slippage (market impact): Large orders move the market against you.
    You want to buy 10,000 shares; by the time you're done, price rose $0.10.
  - Borrowing costs: For short selling, you pay to borrow shares (variable rate)

A strategy that shows 10% annual returns might show 2% after realistic costs.
High-frequency strategies are especially sensitive—many die completely when
costs are properly modeled.
```

---

### 85. Performance Metrics

Understanding these metrics is crucial for evaluating strategies objectively. Beginners often focus only on total return, but that ignores risk. A strategy that makes 50% but has a 60% max drawdown is often worse than one that makes 20% with a 10% drawdown.

| Metric | Formula | What It Tells You |
|--------|---------|-------------------|
| **Total Return** | (Final - Initial) / Initial | Raw performance. But a 100% return over 10 years is mediocre; over 1 year is exceptional. |
| **CAGR** | (Final/Initial)^(1/years) - 1 | Annualized return. Standardizes returns to compare across timeframes. 15% CAGR is strong for any strategy. |
| **Volatility** | StdDev(returns) × √252 | Risk measure. 20% annual volatility means daily swings of ~1.25% are normal. Higher volatility = bumpier ride. |
| **Sharpe Ratio** | (Return - RiskFree) / Volatility | The gold standard for risk-adjusted return. >1.0 is good, >2.0 is excellent, >3.0 is exceptional (or too good to be true). |
| **Sortino Ratio** | (Return - RiskFree) / DownsideVol | Like Sharpe, but only penalizes downside volatility. Many prefer this since upside volatility is good. |
| **Max Drawdown** | Largest peak-to-trough decline | The worst loss from a peak. If your peak was $150k and trough was $100k, max DD is 33%. Can you stomach that? |
| **Calmar Ratio** | CAGR / Max Drawdown | Return per unit of drawdown. A Calmar of 2 means you make 2x your worst drawdown. Higher is better. |
| **Win Rate** | Winning trades / Total trades | What percentage of trades win? But this alone is meaningless—you can win 90% of trades and still lose money overall. |
| **Profit Factor** | Gross profits / Gross losses | If you made $10,000 on winners and lost $5,000 on losers, PF = 2.0. Above 1.0 means net profitable. |
| **Expectancy** | (WinRate × AvgWin) - (LossRate × AvgLoss) | Expected profit per trade. Combines win rate with average win/loss sizes. Must be positive for strategy to work. |

**The key insight**: A strategy with 30% win rate can be highly profitable if average wins are much larger than average losses (trend following). A strategy with 90% win rate can be a disaster if the occasional loss wipes out all the small wins (selling options naked).

```
WIN RATE vs REWARD:RISK - BOTH PATHS TO PROFIT

HIGH WIN RATE, SMALL WINS              LOW WIN RATE, BIG WINS
(Mean Reversion, Options Selling)      (Trend Following)

100 trades:                            100 trades:
  90 wins × $100 = $9,000                30 wins × $400 = $12,000
  10 losses × $800 = $8,000              70 losses × $100 = $7,000
  ─────────────────────────              ─────────────────────────
  Net: +$1,000                           Net: +$5,000

Feels good (winning often)             Feels bad (losing often)
But one big loss hurts                 But winners are MUCH bigger


BREAKEVEN WIN RATE CALCULATOR

  If your avg win = 2× your avg loss (2:1 reward:risk)
  Breakeven = 1 / (1 + 2) = 33% win rate

  Reward:Risk │ Breakeven Win Rate │ At 50% wins, profit?
  ────────────┼────────────────────┼─────────────────────
      1:1     │       50%          │ Break even
      2:1     │       33%          │ +$50 per $100 risked
      3:1     │       25%          │ +$100 per $100 risked
      0.5:1   │       67%          │ -$25 per $100 risked

  → You can win less often IF your wins are bigger
  → High win rate doesn't guarantee profit!
```

---

### 86. Statistical Validation

**T-Test for Returns**:
```
Is mean return statistically different from zero?
t = mean / (std / √n)
p-value < 0.05 → statistically significant
```

**Monte Carlo Simulation**:
```
Randomly sample trades with replacement
Generate distribution of outcomes
Confidence intervals for metrics
```

**Walk-Forward Analysis**:
```
Train on window 1, test on window 2
Roll forward, repeat
More realistic than single train/test split
```

---

## Appendix: Quick Reference

### Strategy Decision Matrix

```
┌─────────────────────────────────────────────────────────────────┐
│                    WHICH STRATEGY TO USE?                       │
└─────────────────────────────────────────────────────────────────┘

                    Is market trending?
                           │
              ┌────────────┴────────────┐
              │                         │
             YES                        NO
              │                         │
              ▼                         ▼
    ┌─────────────────┐       ┌─────────────────┐
    │ TREND FOLLOWING │       │  Is volatility  │
    │                 │       │      high?      │
    │ • MA Crossover  │       └────────┬────────┘
    │ • MACD          │                │
    │ • Turtle        │       ┌────────┴────────┐
    │ • Supertrend    │       │                 │
    └─────────────────┘      YES                NO
                              │                 │
                              ▼                 ▼
                    ┌──────────────┐   ┌──────────────┐
                    │   BREAKOUT   │   │    MEAN      │
                    │              │   │  REVERSION   │
                    │ • Channel    │   │              │
                    │   breakout   │   │ • Bollinger  │
                    │ • Straddles  │   │ • RSI        │
                    │ • Gamma      │   │ • Pairs      │
                    └──────────────┘   └──────────────┘


        TIME HORIZON GUIDE
        ══════════════════

        Seconds     │  HFT, Market Making
        Minutes     │  Scalping, Momentum
        Hours       │  Day Trading, Mean Reversion
        Days        │  Swing Trading, Breakouts
        Weeks       │  Position Trading, Trend Following
        Months      │  Factor Investing, Value
```

### Indicator Cheat Sheet

| Indicator | Type | Bullish Signal | Bearish Signal |
|-----------|------|----------------|----------------|
| SMA Cross | Trend | Fast > Slow | Fast < Slow |
| RSI | Momentum | < 30 | > 70 |
| MACD | Momentum | Signal cross up | Signal cross down |
| Bollinger | Volatility | Touch lower band | Touch upper band |
| ADX | Trend | > 25 (trending) | < 20 (ranging) |
| OBV | Volume | Rising | Falling |
| Stochastic | Momentum | < 20 + cross up | > 80 + cross down |

### Order Type Decision Tree

```
Need immediate fill?
  YES → Market Order
  NO → Need specific price?
         YES → Limit Order
         NO → Need to protect position?
                YES → Stop or Trailing Stop
                NO → Consider algo execution
```

### Strategy Selection by Market Condition

| Condition | Recommended Strategies |
|-----------|----------------------|
| Strong trend | Trend following, momentum |
| Range-bound | Mean reversion, market making |
| High volatility | Breakout, long straddle |
| Low volatility | Iron condors, short straddle |
| Uncertain | Reduce size, factor-neutral |

---

## Further Resources

### Books
- "Algorithmic Trading" - Ernest Chan
- "Quantitative Trading" - Ernest Chan
- "Trading and Exchanges" - Larry Harris
- "Advances in Financial Machine Learning" - Marcos López de Prado
- "Active Portfolio Management" - Grinold & Kahn
- "Option Volatility and Pricing" - Sheldon Natenberg

### Academic Papers
- Fama-French Factor Models
- Jegadeesh & Titman (Momentum)
- Avellaneda-Stoikov (Market Making)
- Lo & MacKinlay (Statistical Arbitrage)

### Data Sources
- Alpaca (US equities, free tier available)
- Polygon.io (comprehensive market data)
- Quandl (alternative data)
- Yahoo Finance (basic historical data)
- FRED (economic indicators)

---

## Conclusion: Getting Started

After reading through all these strategies, you might feel overwhelmed. Where should you start? Here's a practical roadmap:

### For Complete Beginners

1. **Start with paper trading**: Use simulated money before risking real capital. Most brokers offer paper trading modes.

2. **Master one simple strategy first**: Moving average crossover on a single ETF (like SPY) is a great starting point. Understand it deeply before adding complexity.

3. **Learn proper position sizing**: This is more important than your entry signals. Risk 1-2% per trade maximum.

4. **Backtest rigorously**: Before trading any strategy live, test it on at least 5 years of data. Be paranoid about biases.

5. **Start small**: When you go live, trade with 10% of what you eventually plan to trade. Learn from real-market conditions with limited downside.

### Common Beginner Mistakes to Avoid

- **Over-optimizing**: Finding parameters that worked perfectly in the past but won't work in the future
- **Ignoring transaction costs**: Many strategies only look profitable before costs
- **Trading too large**: Position sizes that cause you to panic when positions move against you
- **Strategy hopping**: Abandoning a strategy after a few losses instead of trusting your backtested system
- **Complexity for complexity's sake**: Simple strategies often outperform complex ones

### A Realistic Perspective

Most individual algorithmic traders do not beat the market after accounting for the time they spend and transaction costs. The competition—hedge funds with billions in resources—is fierce.

However, algorithmic trading is still worthwhile because:
- You learn to make decisions systematically, not emotionally
- You develop deep market understanding
- You can automate execution even if your strategy is simple
- Small, patient edges can compound over time
- The process is intellectually rewarding

The journey of a thousand trades begins with a single backtest. Good luck!

---

*Document generated for algorithmic trading research and education purposes.*
*Last updated: 2025*
