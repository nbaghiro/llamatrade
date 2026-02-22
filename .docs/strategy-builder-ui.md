# Strategy Builder UI Specification

This document provides detailed ASCII art wireframes for the LlamaTrade visual strategy builder, inspired by Composer's symphony editor.

---

## 1. Main Layout Overview

```
+-------------------------------------------------------------------------------------------+
|  Logo   Portfolio   Watch   Discover   [+ Create v]   Editor · Backtest              [?]  |
+-------------------------------------------------------------------------------------------+
|         |                                                          |                      |
| +-----+ | +------------------------------------------------------+ | +------------------+ |
| |SAVE | | |                                                      | | | Backtest Preview | |
| +-----+ | | @ Core Satellite                      [* Create AI]  | | |                  | |
| |Undo | | |                                                      | | |    /\    /\      | |
| |Redo | | +------------------------------------------------------+ | |   /  \__/  \     | |
| +-----+ |   |                                                      | |  /          \_   | |
|         |   v WEIGHT Specified                                     | |                  | |
| +-----+ |   |                                                      | | [> RUN]          | |
| |DETAIL |   *---[ v 15% ]                                          | |                  | |
| |-----|  |   |    |                                                 | | > Jump to        | |
| |Name | |   |    +---> +----------------------------------+        | |   Backtest       | |
| |Core | |   |         | @ Mini                            |        | +------------------+ |
| |Satel| |   |         +----------------------------------+         |                      |
| |lite | |   |           |                                          |                      |
| |-----| |   |           v WEIGHT Inverse Volatility 30d            |                      |
| |Desc | |   |           |                                          |                      |
| |Core | |   |           +---> +------------------------------+     |                      |
| |satel| |   |           |     | @ VNQ  Vanguard Real Estate  |     |                      |
| |lite.| |   |           |     +------------------------------+     |                      |
| |-----| |   |           |                                          |                      |
| |Freq | |   |           +---> +------------------------------+     |                      |
| |Quart| |   |                 | + Add a Block                |     |                      |
| |erly | |   |                 +------------------------------+     |                      |
| |-----| |   |                                                      |                      |
| |Value| |   *---[ v 30% ]                                          |                      |
| |$1500| |   |    |                                                 |                      |
| |Dep. | |   |    +---> +----------------------------------+        |                      |
| |$500 | |   |         | @ Satellite                       |        |                      |
| |-----| |   |         +----------------------------------+         |                      |
| |[Inv]| |   |           |                                          |                      |
| |[Sel]| |   |           +---> @ VTI                                |                      |
| +-----+ |   |           +---> @ VXUS                               |                      |
|         |   |           +---> @ BND                                |                      |
| +-----+ |   |           +---> @ BNDX                               |                      |
| |Watch| |   |           +---> @ VMBS                               |                      |
| |Share| |   |                                                      |                      |
| +-----+ |   *---[ v 55% ]                                          |                      |
|         |        |                                                 |                      |
|         |        +---> +----------------------------------+        |                      |
|         |              | @ Satellite-Bond                 |        |                      |
|         |              +----------------------------------+        |                      |
|         |                |                                         |                      |
|         |                v IF price(SPY) > SMA(SPY, 200)           |                      |
|         |                |                                         |                      |
|         |                +---> @ SPY  SPDR S&P 500 ETF             |                      |
|         |                |                                         |                      |
|         |                v ELSE                                    |                      |
|         |                |                                         |                      |
|         |                +---> + Add a Block                       |                      |
|         |                                                          |                      |
+---------+----------------------------------------------------------+----------------------+
```

---

## 2. Left Sidebar - Symphony Details Panel

```
+--------------------+
| v Save changes   v |
+--------------------+
| [< Undo] [Redo >]  |
+--------------------+

+--------------------+
| v Symphony Details |
+--------------------+
| Name               |
| +----------------+ |
| | Core Satellite | |
| +----------------+ |
|                    |
| Description        |
| +----------------+ |
| | Core satellite | |
| | strategies are | |
| | a mainstay of  | |
| | institutional  | |
| | portfolios...  | |
| +----------------+ |
|                    |
| Trading Frequency  |
| +----------------+ |
| | Quarterly    v | |
| +----------------+ |
|                    |
| Investments        |
| Value: $1,500.00   |
| Net Deposits: $500 |
|                    |
| [Invest]  [Sell]   |
+--------------------+

+--------------------+
| [@ Watching]       |
| [^ Share   ]       |
+--------------------+
```

### Trading Frequency Dropdown

```
+------------------+
| Quarterly      v |
+------------------+
| Daily            |
| Weekly           |
| Monthly        * |
| Quarterly        |
| Annually         |
+------------------+
```

---

## 3. Canvas - Tree Structure

The main canvas displays a tree structure with nodes connected by lines.

### Node Types

```
ROOT NODE (Symphony)
+-----------------------------------------------+
| @ Core Satellite              [* Create AI]   |
+-----------------------------------------------+

WEIGHT NODE (Allocation Method)
+-----------------------------------------------+
  v WEIGHT Specified
  |
  *---[ v 15% ]---*---[ v 30% ]---*---[ v 55% ]

WEIGHT METHOD BADGE (Pill)
+------------------------------+
| v WEIGHT Inverse Volatility  |  <-- Green background
+------------------------------+

PERCENTAGE BADGE
+--------+
| v 15%  |  <-- Blue background
+--------+

GROUP NODE
+----------------------------------+
| @ Mini                           |
+----------------------------------+

ASSET NODE
+----------------------------------+
| o VNQ  Vanguard Real Estate...   |
+----------------------------------+

ADD BLOCK NODE
+----------------------------------+
| + Add a Block  Stocks, Weights...|
+----------------------------------+

CONDITIONAL - IF BRANCH
+------------------------------------------+
| v IF price(SPY) > 200d moving average    |  <-- Yellow/gold background
+------------------------------------------+

CONDITIONAL - ELSE BRANCH
+--------+
| v ELSE |  <-- Orange background
+--------+
```

---

## 4. Tree Connection Patterns

### Vertical Connection (Parent to Child)

```
+------------------+
| @ Parent Group   |
+------------------+
        |
        v WEIGHT Equal
        |
        +---> +------------------+
              | o AAPL           |
              +------------------+
```

### Multiple Children (Weight Split)

```
v WEIGHT Specified
|
*---------*---------*
|         |         |
v 15%     v 30%     v 55%
|         |         |
|         |         +---> [Group C]
|         +---> [Group B]
+---> [Group A]
```

### Nested Groups

```
+------------------+
| @ Outer Group    |
+------------------+
        |
        +---> +------------------+
              | @ Inner Group    |
              +------------------+
                      |
                      +---> o AAPL
                      |
                      +---> o MSFT
```

---

## 5. Add Block Dropdown Menu

```
                              +---------------------------+
                              | ADD BLOCK                 |
+---------------------------+ +---------------------------+
| + Add a Block...          | | o Asset                   |
+---------------------------+ |   Add stocks or ETFs      |
                              +---------------------------+
                              | @ Group                   |
                              |   Organize blocks by      |
                              |   placing them inside a   |
                              |   named group             |
                              +---------------------------+
                              | = Weight (Allocation)     |
                              |   Decide how funds are    |
                              |   allocated to blocks     |
                              +---------------------------+
                              | ? If/Else (Conditional)   |
                              |   Use technical indicators|
                              |   to create if/then logic |
                              +---------------------------+
                              | Y Filter                  |
                              |   Sort and filter assets  |
                              |   by their attributes     |
                              +---------------------------+
```

---

## 6. Block Type Details

### 6.1 Asset Block

```
COLLAPSED VIEW:
+------------------------------------------+
| o NVDA  NVIDIA Corporation - NASDAQ      |
+------------------------------------------+

EXPANDED VIEW:
+------------------------------------------+
| o NVDA  NVIDIA Corporation               |
+------------------------------------------+
| Exchange: NASDAQ                         |
| Price: $875.32                           |
| Change: +2.34%                           |
|                                          |
| [Remove]                    [Set Weight] |
+------------------------------------------+
```

### 6.2 Group Block

```
COLLAPSED:
+----------------------------------+
| @ Tech Giants                  v |
+----------------------------------+

EXPANDED:
+----------------------------------+
| @ Tech Giants                  ^ |
+----------------------------------+
        |
        +---> o AAPL
        |
        +---> o MSFT
        |
        +---> o GOOGL
        |
        +---> + Add a Block
```

### 6.3 Weight Block

```
EQUAL WEIGHT:
+----------------------------------+
| v WEIGHT Equal                   |
+----------------------------------+
        |
        +---> o AAPL  (auto: 33.3%)
        +---> o MSFT  (auto: 33.3%)
        +---> o GOOGL (auto: 33.3%)

SPECIFIED WEIGHT:
+----------------------------------+
| v WEIGHT Specified               |
+----------------------------------+
        |
        *-------*-------*
        |       |       |
      v 50%   v 30%   v 20%
        |       |       |
      AAPL    MSFT    GOOGL

INVERSE VOLATILITY:
+----------------------------------+
| v WEIGHT Inverse Volatility 30d  |
+----------------------------------+
        |
        +---> o VTI   (calc: 42%)
        +---> o BND   (calc: 58%)
```

### 6.4 Conditional Block (If/Else)

```
+----------------------------------------------+
| v IF current price of SPY is greater than    |
|    the 200d moving average of price of SPY   |
+----------------------------------------------+
        |
        +---> o SPY  SPDR S&P 500 ETF

+--------+
| v ELSE |
+--------+
        |
        +---> o TLT  iShares 20+ Year Treasury
```

**Condition Builder (Expanded):**

```
+--------------------------------------------------+
| IF                                               |
| +----------------------------------------------+ |
| | [current price v] of [SPY        ]           | |
| |                                              | |
| | [is greater than v]                          | |
| |                                              | |
| | [200d moving average v] of [price v] of [SPY]| |
| +----------------------------------------------+ |
|                                                  |
| [+ Add condition]                                |
+--------------------------------------------------+
```

### 6.5 Filter Block

```
+------------------------------------------+
| Y FILTER Top 10 by Momentum (12 months)  |
+------------------------------------------+
        |
        Source: S&P 500
        |
        +---> o NVDA  (rank: 1)
        +---> o META  (rank: 2)
        +---> o AAPL  (rank: 3)
        +---> ... (7 more)
```

**Filter Configuration:**

```
+------------------------------------------+
| FILTER                                   |
+------------------------------------------+
| Select [Top v] [10] assets               |
|                                          |
| From: [S&P 500 Universe         v]       |
|                                          |
| Sorted by: [Momentum            v]       |
| Period:    [12 months           v]       |
|                                          |
| [Apply]                         [Cancel] |
+------------------------------------------+
```

---

## 7. Weight Method Selector

```
+------------------------------------------+
| Select Weight Method                     |
+------------------------------------------+
|                                          |
| ( ) Equal Weight                         |
|     Distribute evenly across all assets  |
|                                          |
| (*) Specified Weight                     |
|     Manually set percentage for each     |
|                                          |
| ( ) Inverse Volatility                   |
|     Less volatile assets get more weight |
|     Period: [30 days v]                  |
|                                          |
| ( ) Risk Parity                          |
|     Equal risk contribution from each    |
|                                          |
| ( ) Market Cap Weighted                  |
|     Weight by market capitalization      |
|                                          |
| ( ) Momentum                             |
|     Higher momentum = higher weight      |
|     Period: [12 months v]                |
|                                          |
+------------------------------------------+
```

---

## 8. Backtest Preview Panel

```
+---------------------------+
| v Backtest Preview        |
+---------------------------+
|                           |
|   Portfolio Value         |
|                           |
|     ^                     |
|    /|\      /\            |
|   / | \    /  \           |
|  /  |  \  /    \          |
| /   |   \/      \____     |
|/____|________________\    |
| Jan  Apr  Jul  Oct  Jan   |
|                           |
| --- Your Strategy         |
| ... Benchmark (SPY)       |
|                           |
+---------------------------+
| Total Return:   +24.5%    |
| Sharpe Ratio:   1.42      |
| Max Drawdown:   -12.3%    |
+---------------------------+
|                           |
|      [> RUN BACKTEST]     |
|                           |
| > Jump to Full Backtest   |
+---------------------------+
```

---

## 9. AI Creation Modal

```
+----------------------------------------------------------------+
|                                                           [X]  |
|  * Create with AI                                              |
+----------------------------------------------------------------+
|                                                                 |
|  Describe your investment strategy in plain English:            |
|                                                                 |
|  +-----------------------------------------------------------+ |
|  | I want a portfolio that invests in tech stocks when the   | |
|  | market is trending up (SPY above 200-day average), but    | |
|  | switches to bonds when trending down. Rebalance monthly.  | |
|  |                                                           | |
|  +-----------------------------------------------------------+ |
|                                                                 |
|  Examples:                                                      |
|  - "Equal weight FAANG stocks, rebalance quarterly"            |
|  - "Top 10 S&P 500 by momentum, inverse volatility weighted"   |
|  - "60/40 stocks/bonds with risk-off when VIX > 30"           |
|                                                                 |
|                                         [Cancel]  [* Generate] |
+----------------------------------------------------------------+
```

**AI Generation Result:**

```
+----------------------------------------------------------------+
|                                                           [X]  |
|  * AI Generated Strategy                                       |
+----------------------------------------------------------------+
|                                                                 |
|  Based on your description, here's your strategy:              |
|                                                                 |
|  +-----------------------------------------------------------+ |
|  | symphony "Trend Following 60/40" {                        | |
|  |   rebalance: monthly                                      | |
|  |                                                           | |
|  |   if Price(SPY) > SMA(SPY, 200) {                        | |
|  |     allocate fixed_weight [                               | |
|  |       QQQ @ 60%,                                          | |
|  |       TLT @ 40%                                           | |
|  |     ]                                                     | |
|  |   } else {                                                | |
|  |     allocate fixed_weight [                               | |
|  |       TLT @ 80%,                                          | |
|  |       GLD @ 20%                                           | |
|  |     ]                                                     | |
|  |   }                                                       | |
|  | }                                                         | |
|  +-----------------------------------------------------------+ |
|                                                                 |
|  [Edit as Code]  [Edit Visually]              [Regenerate]     |
|                                                                 |
|                                  [Cancel]  [Apply to Canvas]   |
+----------------------------------------------------------------+
```

---

## 10. Code Editor View (Split Panel)

```
+-----------------------------------------------------------------------------------+
| [Visual] [Code]  [Split]                                    [Infix v] [Validate] |
+-----------------------------------------------------------------------------------+
|                                   |                                               |
| @ Core Satellite                  |  symphony "Core Satellite" {                  |
|   |                               |    rebalance: quarterly                       |
|   v WEIGHT Specified              |                                               |
|   |                               |    allocate fixed_weight [                    |
|   *---[ 15% ]                     |      Group("Mini") @ 15% {                    |
|   |     |                         |        allocate inverse_volatility [          |
|   |     +---> @ Mini              |          VNQ                                  |
|   |           |                   |        ]                                      |
|   |           v WEIGHT Inv Vol    |      },                                       |
|   |           |                   |      Group("Satellite") @ 30% {               |
|   |           +---> o VNQ         |        allocate equal_weight [                |
|   |                               |          VTI, VXUS, BND, BNDX, VMBS           |
|   *---[ 30% ]                     |        ]                                      |
|   |     |                         |      },                                       |
|   |     +---> @ Satellite         |      Group("Satellite-Bond") @ 55% {          |
|   |           |                   |        if Price(SPY) > SMA(SPY, 200) {        |
|   |           +---> o VTI         |          allocate fixed_weight [SPY]          |
|   |           +---> o VXUS        |        } else {                               |
|   |           +---> o BND         |          // Add allocation                    |
|   |           +---> o BNDX        |        }                                      |
|   |           +---> o VMBS        |      }                                        |
|   |                               |    ]                                          |
|   *---[ 55% ]                     |  }                                            |
|         |                         |                                               |
|         +---> @ Satellite-Bond    |                                               |
|               |                   |                                               |
|               v IF SPY > SMA      |                                               |
|               |                   |                                               |
|               +---> o SPY         |                                               |
|               |                   |                                               |
|               v ELSE              |                                               |
|               |                   |                                               |
|               +---> + Add Block   |                                               |
|                                   |                                               |
+-----------------------------------+-----------------------------------------------+
```

---

## 11. Mobile Responsive Layout

```
MOBILE VIEW (< 768px)
+-------------------------+
| [=] LlamaTrade     [?]  |
+-------------------------+
| Core Satellite   [...]  |
+-------------------------+
|                         |
| v WEIGHT Specified      |
| |                       |
| *---[ 15% ]             |
| |    |                  |
| |    @ Mini             |
| |      |                |
| |      v WEIGHT Inv Vol |
| |      |                |
| |      o VNQ            |
| |      + Add            |
| |                       |
| *---[ 30% ]             |
| |    |                  |
| |    @ Satellite        |
| |      |                |
| |      o VTI            |
| |      o VXUS           |
| |      o BND            |
| |      ...              |
| |                       |
| *---[ 55% ]             |
|      |                  |
|      @ Satellite-Bond   |
|        |                |
|        v IF SPY > 200MA |
|        |                |
|        o SPY            |
|        |                |
|        v ELSE           |
|        |                |
|        + Add            |
|                         |
+-------------------------+
| [Details] [Backtest]    |
+-------------------------+
```

---

## 12. Component States

### Block States

```
NORMAL STATE:
+----------------------------------+
| o AAPL  Apple Inc.               |
+----------------------------------+

HOVER STATE:
+----------------------------------+
| o AAPL  Apple Inc.          [x]  |  <-- Delete button appears
+----------------------------------+
  ^-- Subtle highlight/shadow

SELECTED STATE:
+==================================+
| o AAPL  Apple Inc.          [x]  |  <-- Bold border
+==================================+

DRAGGING STATE:
  +----------------------------------+
  | o AAPL  Apple Inc.               |  <-- Slight rotation, shadow
  +----------------------------------+
         ^-- Ghost shows original position

DROP TARGET:
+----------------------------------+
|           DROP HERE              |  <-- Highlighted drop zone
+----------------------------------+

ERROR STATE:
+----------------------------------+
| o INVALID  Symbol not found      |  <-- Red border
+----------------------------------+
  ! Please enter a valid symbol

LOADING STATE:
+----------------------------------+
| [....] Loading...                |
+----------------------------------+
```

### Button States

```
NORMAL:        HOVER:         ACTIVE:        DISABLED:
+--------+     +--------+     +--------+     +--------+
| > RUN  |     | > RUN  |     | > RUN  |     | > RUN  |
+--------+     +========+     +########+     +--------+
               (highlight)    (pressed)      (grayed)
```

---

## 13. Drag and Drop Interactions

### Reordering Assets

```
BEFORE:                    DURING:                    AFTER:
+----------+               +----------+               +----------+
| o AAPL   |               |  ~~~~~~~~ |  <-- drop    | o MSFT   |
+----------+               +----------+     indicator +----------+
| o MSFT   |  --drag-->    | o MSFT   |               | o AAPL   |
+----------+               +----------+               +----------+
| o GOOGL  |               | o GOOGL  |               | o GOOGL  |
+----------+               +----------+               +----------+
      ^                          ^
      |                    +----------+
   dragging                | o AAPL   |  <-- floating
                           +----------+
```

### Moving Between Groups

```
GROUP A                    GROUP B
+-----------------+        +-----------------+
| @ Tech          |        | @ Finance       |
+-----------------+        +-----------------+
| o AAPL          |  ===>  | o JPM           |
| o MSFT    drag--|------->| o BAC           |
| o GOOGL         |        | o MSFT  <--new  |
+-----------------+        +-----------------+
```

---

## 14. Validation Messages

```
SUCCESS VALIDATION:
+-------------------------------------------------------+
| [*] Strategy validated successfully                   |
|                                                       |
|   * 5 assets configured                              |
|   * Weights sum to 100%                              |
|   * All conditions have valid comparisons            |
+-------------------------------------------------------+

WARNING VALIDATION:
+-------------------------------------------------------+
| [!] Strategy has warnings                             |
|                                                       |
|   ! No assets in ELSE branch (line 12)               |
|   ! High concentration: NVDA is 45% of portfolio     |
+-------------------------------------------------------+

ERROR VALIDATION:
+-------------------------------------------------------+
| [X] Strategy has errors                               |
|                                                       |
|   X Weights sum to 115% (must equal 100%)            |
|   X Unknown indicator: RSI_FAST (line 8)             |
|   X Missing closing brace (line 15)                  |
+-------------------------------------------------------+
```

---

## 15. Color Coding Reference

```
BADGE COLORS:
+----------------------+------------------+
| Element              | Color            |
+----------------------+------------------+
| WEIGHT method        | Green  #22C55E   |
| Percentage           | Blue   #3B82F6   |
| IF condition         | Yellow #EAB308   |
| ELSE branch          | Orange #F97316   |
| FILTER               | Purple #A855F7   |
| Error                | Red    #EF4444   |
+----------------------+------------------+

NODE ICONS:
+--------+------------------+
| Symbol | Meaning          |
+--------+------------------+
|   @    | Group            |
|   o    | Asset            |
|   +    | Add block        |
|   v    | Expandable       |
|   >    | Collapsed        |
|   *    | Branch point     |
|   =    | Weight           |
|   ?    | Conditional      |
|   Y    | Filter           |
+--------+------------------+
```

---

## 16. Keyboard Shortcuts

```
+------------------+--------------------------------+
| Shortcut         | Action                         |
+------------------+--------------------------------+
| Cmd/Ctrl + S     | Save changes                   |
| Cmd/Ctrl + Z     | Undo                           |
| Cmd/Ctrl + Y     | Redo                           |
| Cmd/Ctrl + D     | Duplicate selected block       |
| Delete/Backspace | Delete selected block          |
| Cmd/Ctrl + /     | Toggle code view               |
| Cmd/Ctrl + Enter | Run backtest                   |
| Cmd/Ctrl + K     | Open AI creation               |
| Escape           | Deselect / Close modal         |
| Tab              | Navigate to next block         |
| Shift + Tab      | Navigate to previous block     |
| Arrow keys       | Navigate tree                  |
| Enter            | Expand/collapse selected       |
+------------------+--------------------------------+
```

---

## 17. DSL Mapping

Each visual element maps directly to DSL constructs:

```
VISUAL                              INFIX DSL
------                              ---------

@ Core Satellite          -->       symphony "Core Satellite" {
  |
  v WEIGHT Specified      -->         allocate fixed_weight [
  |
  *--[ 15% ]              -->           Group("Mini") @ 15% {
  |    |
  |    @ Mini             -->
  |      |
  |      v WEIGHT Inv Vol -->             allocate inverse_volatility [
  |      |
  |      o VNQ            -->               VNQ
  |                       -->             ]
  |                       -->           },
  |
  *--[ 30% ]              -->           Group("Satellite") @ 30% {
       |
       @ Satellite        -->
         |
         o VTI            -->             allocate equal_weight [VTI, VXUS]
         o VXUS           -->
                          -->           }
                          -->         ]
                          -->       }


VISUAL                              S-EXPRESSION DSL
------                              ----------------

@ Core Satellite          -->       (defsymphony "Core Satellite"
  |
  v WEIGHT Specified      -->         (weight-specified
  |
  *--[ 15% ]              -->           [(group "Mini" :weight 0.15
  |    |
  |    @ Mini             -->
  |      |
  |      v WEIGHT Inv Vol -->              (weight-inverse-volatility
  |      |
  |      o VNQ            -->                [(asset "VNQ")]))
  |
  *--[ 30% ]              -->            (group "Satellite" :weight 0.30
       |
       @ Satellite        -->
         |
         o VTI            -->              (weight-equal
         o VXUS           -->                [(asset "VTI") (asset "VXUS")]))]))
```

---

## 18. Implementation Notes

### React Component Hierarchy

```
<StrategyBuilder>
  <Toolbar>
    <SaveButton />
    <UndoRedo />
    <ViewToggle />
  </Toolbar>

  <Layout>
    <LeftSidebar>
      <SymphonyDetails />
      <InvestmentPanel />
      <ActionButtons />
    </LeftSidebar>

    <Canvas>
      <TreeView>
        <RootNode />
        <WeightNode>
          <PercentageBadge />
          <GroupNode>
            <AssetNode />
            <AddBlockButton />
          </GroupNode>
        </WeightNode>
        <ConditionalNode>
          <IfBranch />
          <ElseBranch />
        </ConditionalNode>
      </TreeView>
    </Canvas>

    <RightSidebar>
      <BacktestPreview />
      <RunButton />
    </RightSidebar>
  </Layout>

  <Modals>
    <AICreationModal />
    <AddBlockModal />
    <ConditionBuilder />
  </Modals>
</StrategyBuilder>
```

### State Management

```
StrategyBuilderState {
  // Symphony data
  symphony: SymphonyNode

  // UI state
  selectedBlockId: string | null
  expandedBlocks: Set<string>
  viewMode: 'visual' | 'code' | 'split'
  codeFormat: 'infix' | 'sexpr'

  // History for undo/redo
  history: SymphonyNode[]
  historyIndex: number

  // Validation
  errors: ValidationError[]
  warnings: ValidationWarning[]

  // Backtest
  backtestResults: BacktestResults | null
  isBacktesting: boolean
}
```

---

## 19. Accessibility Considerations

```
ARIA LABELS:
- Tree structure uses role="tree" and role="treeitem"
- Expandable nodes have aria-expanded
- Drag handles have aria-label="Drag to reorder"
- Modals trap focus and have aria-modal="true"

SCREEN READER ANNOUNCEMENTS:
- "Block added: Asset AAPL"
- "Block deleted: Group Tech"
- "Weights updated: 15%, 30%, 55%"
- "Backtest complete: 24.5% return"

KEYBOARD NAVIGATION:
- Full tree navigation with arrow keys
- Tab order follows visual hierarchy
- Enter/Space to activate buttons
- Escape to close modals/dropdowns
```
