/**
 * Strategy Templates - Pre-built strategies users can load as starting points
 *
 * These templates demonstrate all block types and real-world trading strategies.
 */

import { v4 as uuidv4 } from 'uuid';

import type { Block, BlockId, StrategyTree } from '../types/strategy-builder';

export interface StrategyTemplate {
  id: string;
  name: string;
  description: string;
  category: 'tactical' | 'passive' | 'factor' | 'all-weather';
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  blockTypes: string[]; // Block types used in this template
  createTree: () => StrategyTree;
}

// ============================================================================
// Template 1: Risk-On/Risk-Off Tactical Allocation
// ============================================================================

function createRiskOnRiskOffStrategy(): StrategyTree {
  // Generate IDs
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;

  // Risk-On branch
  const ifBlockId = uuidv4() as BlockId;
  const riskOnWeightId = uuidv4() as BlockId;
  const growthGroupId = uuidv4() as BlockId;
  const growthWeightId = uuidv4() as BlockId;
  const qqqId = uuidv4() as BlockId;
  const arkkId = uuidv4() as BlockId;
  const smhId = uuidv4() as BlockId;
  const highBetaGroupId = uuidv4() as BlockId;
  const highBetaWeightId = uuidv4() as BlockId;
  const tslaId = uuidv4() as BlockId;
  const nvdaId = uuidv4() as BlockId;
  const amdId = uuidv4() as BlockId;

  // Risk-Off branch
  const elseBlockId = uuidv4() as BlockId;
  const riskOffWeightId = uuidv4() as BlockId;
  const treasuryGroupId = uuidv4() as BlockId;
  const treasuryWeightId = uuidv4() as BlockId;
  const tltId = uuidv4() as BlockId;
  const iefId = uuidv4() as BlockId;
  const shyId = uuidv4() as BlockId;
  const defensiveGroupId = uuidv4() as BlockId;
  const defensiveWeightId = uuidv4() as BlockId;
  const xluId = uuidv4() as BlockId;
  const xlpId = uuidv4() as BlockId;
  const gldId = uuidv4() as BlockId;

  // Always-on core
  const coreGroupId = uuidv4() as BlockId;
  const coreWeightId = uuidv4() as BlockId;
  const vtiId = uuidv4() as BlockId;
  const bndId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    // Root
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Risk-On/Risk-Off Tactical',
      childIds: [topWeightId],
    },

    // Top-level weight
    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: {
        [ifBlockId]: 35,
        [elseBlockId]: 35,
        [coreGroupId]: 30,
      },
      childIds: [ifBlockId, elseBlockId, coreGroupId],
    },

    // IF block - Risk On condition
    [ifBlockId]: {
      id: ifBlockId,
      type: 'if',
      parentId: topWeightId,
      condition: {
        left: { type: 'price', symbol: 'SPY', field: 'current' },
        comparator: 'gt',
        right: { type: 'indicator', indicator: 'sma', symbol: 'SPY', period: 200 },
      },
      conditionText: 'SPY price > SMA(200)',
      childIds: [riskOnWeightId],
    },

    // Risk-On allocation
    [riskOnWeightId]: {
      id: riskOnWeightId,
      type: 'weight',
      parentId: ifBlockId,
      method: 'specified',
      allocations: {
        [growthGroupId]: 60,
        [highBetaGroupId]: 40,
      },
      childIds: [growthGroupId, highBetaGroupId],
    },

    // Growth Core group
    [growthGroupId]: {
      id: growthGroupId,
      type: 'group',
      parentId: riskOnWeightId,
      name: 'Growth Core',
      childIds: [growthWeightId],
    },

    [growthWeightId]: {
      id: growthWeightId,
      type: 'weight',
      parentId: growthGroupId,
      method: 'equal',
      allocations: {},
      childIds: [qqqId, arkkId, smhId],
    },

    [qqqId]: {
      id: qqqId,
      type: 'asset',
      parentId: growthWeightId,
      symbol: 'QQQ',
      exchange: 'NASDAQ',
      displayName: 'Invesco QQQ Trust',
    },

    [arkkId]: {
      id: arkkId,
      type: 'asset',
      parentId: growthWeightId,
      symbol: 'ARKK',
      exchange: 'NYSEARCA',
      displayName: 'ARK Innovation ETF',
    },

    [smhId]: {
      id: smhId,
      type: 'asset',
      parentId: growthWeightId,
      symbol: 'SMH',
      exchange: 'NYSEARCA',
      displayName: 'VanEck Semiconductor ETF',
    },

    // High Beta group
    [highBetaGroupId]: {
      id: highBetaGroupId,
      type: 'group',
      parentId: riskOnWeightId,
      name: 'High Beta',
      childIds: [highBetaWeightId],
    },

    [highBetaWeightId]: {
      id: highBetaWeightId,
      type: 'weight',
      parentId: highBetaGroupId,
      method: 'momentum',
      allocations: {},
      lookbackDays: 90,
      childIds: [tslaId, nvdaId, amdId],
    },

    [tslaId]: {
      id: tslaId,
      type: 'asset',
      parentId: highBetaWeightId,
      symbol: 'TSLA',
      exchange: 'NASDAQ',
      displayName: 'Tesla Inc',
    },

    [nvdaId]: {
      id: nvdaId,
      type: 'asset',
      parentId: highBetaWeightId,
      symbol: 'NVDA',
      exchange: 'NASDAQ',
      displayName: 'NVIDIA Corp',
    },

    [amdId]: {
      id: amdId,
      type: 'asset',
      parentId: highBetaWeightId,
      symbol: 'AMD',
      exchange: 'NASDAQ',
      displayName: 'Advanced Micro Devices',
    },

    // ELSE block - Risk Off
    [elseBlockId]: {
      id: elseBlockId,
      type: 'else',
      parentId: topWeightId,
      ifBlockId: ifBlockId,
      childIds: [riskOffWeightId],
    },

    // Risk-Off allocation
    [riskOffWeightId]: {
      id: riskOffWeightId,
      type: 'weight',
      parentId: elseBlockId,
      method: 'specified',
      allocations: {
        [treasuryGroupId]: 50,
        [defensiveGroupId]: 30,
        [gldId]: 20,
      },
      childIds: [treasuryGroupId, defensiveGroupId, gldId],
    },

    // Treasury Safety group
    [treasuryGroupId]: {
      id: treasuryGroupId,
      type: 'group',
      parentId: riskOffWeightId,
      name: 'Treasury Safety',
      childIds: [treasuryWeightId],
    },

    [treasuryWeightId]: {
      id: treasuryWeightId,
      type: 'weight',
      parentId: treasuryGroupId,
      method: 'inverse_volatility',
      allocations: {},
      lookbackDays: 30,
      childIds: [tltId, iefId, shyId],
    },

    [tltId]: {
      id: tltId,
      type: 'asset',
      parentId: treasuryWeightId,
      symbol: 'TLT',
      exchange: 'NASDAQ',
      displayName: 'iShares 20+ Year Treasury Bond ETF',
    },

    [iefId]: {
      id: iefId,
      type: 'asset',
      parentId: treasuryWeightId,
      symbol: 'IEF',
      exchange: 'NASDAQ',
      displayName: 'iShares 7-10 Year Treasury Bond ETF',
    },

    [shyId]: {
      id: shyId,
      type: 'asset',
      parentId: treasuryWeightId,
      symbol: 'SHY',
      exchange: 'NASDAQ',
      displayName: 'iShares 1-3 Year Treasury Bond ETF',
    },

    // Defensive Equity group
    [defensiveGroupId]: {
      id: defensiveGroupId,
      type: 'group',
      parentId: riskOffWeightId,
      name: 'Defensive Equity',
      childIds: [defensiveWeightId],
    },

    [defensiveWeightId]: {
      id: defensiveWeightId,
      type: 'weight',
      parentId: defensiveGroupId,
      method: 'equal',
      allocations: {},
      childIds: [xluId, xlpId],
    },

    [xluId]: {
      id: xluId,
      type: 'asset',
      parentId: defensiveWeightId,
      symbol: 'XLU',
      exchange: 'NYSEARCA',
      displayName: 'Utilities Select Sector SPDR',
    },

    [xlpId]: {
      id: xlpId,
      type: 'asset',
      parentId: defensiveWeightId,
      symbol: 'XLP',
      exchange: 'NYSEARCA',
      displayName: 'Consumer Staples Select Sector SPDR',
    },

    [gldId]: {
      id: gldId,
      type: 'asset',
      parentId: riskOffWeightId,
      symbol: 'GLD',
      exchange: 'NYSEARCA',
      displayName: 'SPDR Gold Shares',
    },

    // Always-On Core group
    [coreGroupId]: {
      id: coreGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'Always-On Core',
      childIds: [coreWeightId],
    },

    [coreWeightId]: {
      id: coreWeightId,
      type: 'weight',
      parentId: coreGroupId,
      method: 'equal',
      allocations: {},
      childIds: [vtiId, bndId],
    },

    [vtiId]: {
      id: vtiId,
      type: 'asset',
      parentId: coreWeightId,
      symbol: 'VTI',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard Total Stock Market ETF',
    },

    [bndId]: {
      id: bndId,
      type: 'asset',
      parentId: coreWeightId,
      symbol: 'BND',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard Total Bond Market ETF',
    },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 2: Multi-Factor Sector Rotation
// ============================================================================

function createMultiFactorRotationStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;

  // Momentum Leaders
  const momentumGroupId = uuidv4() as BlockId;
  const momentumFilterId = uuidv4() as BlockId;

  // Quality Value
  const qualityGroupId = uuidv4() as BlockId;
  const qualityWeightId = uuidv4() as BlockId;
  const brkId = uuidv4() as BlockId;
  const jpmId = uuidv4() as BlockId;
  const jnjId = uuidv4() as BlockId;
  const pgId = uuidv4() as BlockId;
  const unhId = uuidv4() as BlockId;

  // Sector ETFs with condition
  const sectorGroupId = uuidv4() as BlockId;
  const sectorIfId = uuidv4() as BlockId;
  const sectorElseId = uuidv4() as BlockId;
  const bullishSectorWeightId = uuidv4() as BlockId;
  const xlkId = uuidv4() as BlockId;
  const xlvId = uuidv4() as BlockId;
  const xlfId = uuidv4() as BlockId;
  const xleId = uuidv4() as BlockId;
  const defensiveSectorWeightId = uuidv4() as BlockId;
  const xlpDefId = uuidv4() as BlockId;
  const xluDefId = uuidv4() as BlockId;

  // International
  const intlGroupId = uuidv4() as BlockId;
  const intlWeightId = uuidv4() as BlockId;
  const veaId = uuidv4() as BlockId;
  const vwoId = uuidv4() as BlockId;
  const efaId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Multi-Factor Sector Rotation',
      childIds: [topWeightId],
    },

    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: {
        [momentumGroupId]: 30,
        [qualityGroupId]: 30,
        [sectorGroupId]: 20,
        [intlGroupId]: 20,
      },
      childIds: [momentumGroupId, qualityGroupId, sectorGroupId, intlGroupId],
    },

    // Momentum Leaders with Filter
    [momentumGroupId]: {
      id: momentumGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'Momentum Leaders',
      childIds: [momentumFilterId],
    },

    [momentumFilterId]: {
      id: momentumFilterId,
      type: 'filter',
      parentId: momentumGroupId,
      config: {
        selection: 'top',
        count: 10,
        universe: 'sp500',
        sortBy: 'momentum',
        period: '6m',
      },
      displayText: 'Top 10 by Momentum (6 months)',
      childIds: [],
    },

    // Quality Value group
    [qualityGroupId]: {
      id: qualityGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'Quality Value',
      childIds: [qualityWeightId],
    },

    [qualityWeightId]: {
      id: qualityWeightId,
      type: 'weight',
      parentId: qualityGroupId,
      method: 'min_variance',
      allocations: {},
      lookbackDays: 60,
      childIds: [brkId, jpmId, jnjId, pgId, unhId],
    },

    [brkId]: {
      id: brkId,
      type: 'asset',
      parentId: qualityWeightId,
      symbol: 'BRK.B',
      exchange: 'NYSE',
      displayName: 'Berkshire Hathaway Inc',
    },

    [jpmId]: {
      id: jpmId,
      type: 'asset',
      parentId: qualityWeightId,
      symbol: 'JPM',
      exchange: 'NYSE',
      displayName: 'JPMorgan Chase & Co',
    },

    [jnjId]: {
      id: jnjId,
      type: 'asset',
      parentId: qualityWeightId,
      symbol: 'JNJ',
      exchange: 'NYSE',
      displayName: 'Johnson & Johnson',
    },

    [pgId]: {
      id: pgId,
      type: 'asset',
      parentId: qualityWeightId,
      symbol: 'PG',
      exchange: 'NYSE',
      displayName: 'Procter & Gamble Co',
    },

    [unhId]: {
      id: unhId,
      type: 'asset',
      parentId: qualityWeightId,
      symbol: 'UNH',
      exchange: 'NYSE',
      displayName: 'UnitedHealth Group Inc',
    },

    // Sector ETFs with conditional logic
    [sectorGroupId]: {
      id: sectorGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'Sector ETFs',
      childIds: [sectorIfId, sectorElseId],
    },

    [sectorIfId]: {
      id: sectorIfId,
      type: 'if',
      parentId: sectorGroupId,
      condition: {
        left: { type: 'indicator', indicator: 'rsi', symbol: 'XLK', period: 14 },
        comparator: 'lt',
        right: { type: 'number', value: 70 },
      },
      conditionText: 'RSI(XLK, 14) < 70',
      childIds: [bullishSectorWeightId],
    },

    [bullishSectorWeightId]: {
      id: bullishSectorWeightId,
      type: 'weight',
      parentId: sectorIfId,
      method: 'momentum',
      allocations: {},
      lookbackDays: 30,
      childIds: [xlkId, xlvId, xlfId, xleId],
    },

    [xlkId]: {
      id: xlkId,
      type: 'asset',
      parentId: bullishSectorWeightId,
      symbol: 'XLK',
      exchange: 'NYSEARCA',
      displayName: 'Technology Select Sector SPDR',
    },

    [xlvId]: {
      id: xlvId,
      type: 'asset',
      parentId: bullishSectorWeightId,
      symbol: 'XLV',
      exchange: 'NYSEARCA',
      displayName: 'Health Care Select Sector SPDR',
    },

    [xlfId]: {
      id: xlfId,
      type: 'asset',
      parentId: bullishSectorWeightId,
      symbol: 'XLF',
      exchange: 'NYSEARCA',
      displayName: 'Financial Select Sector SPDR',
    },

    [xleId]: {
      id: xleId,
      type: 'asset',
      parentId: bullishSectorWeightId,
      symbol: 'XLE',
      exchange: 'NYSEARCA',
      displayName: 'Energy Select Sector SPDR',
    },

    [sectorElseId]: {
      id: sectorElseId,
      type: 'else',
      parentId: sectorGroupId,
      ifBlockId: sectorIfId,
      childIds: [defensiveSectorWeightId],
    },

    [defensiveSectorWeightId]: {
      id: defensiveSectorWeightId,
      type: 'weight',
      parentId: sectorElseId,
      method: 'equal',
      allocations: {},
      childIds: [xlpDefId, xluDefId],
    },

    [xlpDefId]: {
      id: xlpDefId,
      type: 'asset',
      parentId: defensiveSectorWeightId,
      symbol: 'XLP',
      exchange: 'NYSEARCA',
      displayName: 'Consumer Staples Select Sector SPDR',
    },

    [xluDefId]: {
      id: xluDefId,
      type: 'asset',
      parentId: defensiveSectorWeightId,
      symbol: 'XLU',
      exchange: 'NYSEARCA',
      displayName: 'Utilities Select Sector SPDR',
    },

    // International Diversification
    [intlGroupId]: {
      id: intlGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'International',
      childIds: [intlWeightId],
    },

    [intlWeightId]: {
      id: intlWeightId,
      type: 'weight',
      parentId: intlGroupId,
      method: 'inverse_volatility',
      allocations: {},
      lookbackDays: 30,
      childIds: [veaId, vwoId, efaId],
    },

    [veaId]: {
      id: veaId,
      type: 'asset',
      parentId: intlWeightId,
      symbol: 'VEA',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard FTSE Developed Markets ETF',
    },

    [vwoId]: {
      id: vwoId,
      type: 'asset',
      parentId: intlWeightId,
      symbol: 'VWO',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard FTSE Emerging Markets ETF',
    },

    [efaId]: {
      id: efaId,
      type: 'asset',
      parentId: intlWeightId,
      symbol: 'EFA',
      exchange: 'NYSEARCA',
      displayName: 'iShares MSCI EAFE ETF',
    },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 3: All-Weather Volatility-Targeted Portfolio
// ============================================================================

function createAllWeatherStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;

  // Equity Sleeve
  const equityGroupId = uuidv4() as BlockId;
  const equityWeightId = uuidv4() as BlockId;
  const usLargeCapGroupId = uuidv4() as BlockId;
  const usLargeCapWeightId = uuidv4() as BlockId;
  const spyId = uuidv4() as BlockId;
  const iwmId = uuidv4() as BlockId;
  const mdyId = uuidv4() as BlockId;
  const factorGroupId = uuidv4() as BlockId;
  const factorWeightId = uuidv4() as BlockId;
  const mtumId = uuidv4() as BlockId;
  const qualId = uuidv4() as BlockId;
  const vlueId = uuidv4() as BlockId;

  // Fixed Income
  const fixedIncomeGroupId = uuidv4() as BlockId;
  const fixedIncomeWeightId = uuidv4() as BlockId;
  const durationGroupId = uuidv4() as BlockId;
  const durationWeightId = uuidv4() as BlockId;
  const shyId = uuidv4() as BlockId;
  const iefId = uuidv4() as BlockId;
  const tltId = uuidv4() as BlockId;
  const creditGroupId = uuidv4() as BlockId;
  const creditWeightId = uuidv4() as BlockId;
  const lqdId = uuidv4() as BlockId;
  const hygId = uuidv4() as BlockId;
  const tipsId = uuidv4() as BlockId;

  // Real Assets with condition
  const realAssetsGroupId = uuidv4() as BlockId;
  const realAssetsIfId = uuidv4() as BlockId;
  const realAssetsElseId = uuidv4() as BlockId;
  const inflationWeightId = uuidv4() as BlockId;
  const gldId = uuidv4() as BlockId;
  const slvId = uuidv4() as BlockId;
  const dbcId = uuidv4() as BlockId;
  const normalRealWeightId = uuidv4() as BlockId;
  const gldNormalId = uuidv4() as BlockId;
  const vnqId = uuidv4() as BlockId;

  // Alternatives
  const altGroupId = uuidv4() as BlockId;
  const altWeightId = uuidv4() as BlockId;
  const dbmfId = uuidv4() as BlockId;
  const btalId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'All-Weather Vol-Target',
      childIds: [topWeightId],
    },

    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: {
        [equityGroupId]: 40,
        [fixedIncomeGroupId]: 30,
        [realAssetsGroupId]: 15,
        [altGroupId]: 15,
      },
      childIds: [equityGroupId, fixedIncomeGroupId, realAssetsGroupId, altGroupId],
    },

    // Equity Sleeve
    [equityGroupId]: {
      id: equityGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'Equity Sleeve',
      childIds: [equityWeightId],
    },

    [equityWeightId]: {
      id: equityWeightId,
      type: 'weight',
      parentId: equityGroupId,
      method: 'inverse_volatility',
      allocations: {},
      lookbackDays: 60,
      childIds: [usLargeCapGroupId, factorGroupId],
    },

    [usLargeCapGroupId]: {
      id: usLargeCapGroupId,
      type: 'group',
      parentId: equityWeightId,
      name: 'US Large Cap',
      childIds: [usLargeCapWeightId],
    },

    [usLargeCapWeightId]: {
      id: usLargeCapWeightId,
      type: 'weight',
      parentId: usLargeCapGroupId,
      method: 'market_cap',
      allocations: {},
      childIds: [spyId, iwmId, mdyId],
    },

    [spyId]: {
      id: spyId,
      type: 'asset',
      parentId: usLargeCapWeightId,
      symbol: 'SPY',
      exchange: 'NYSEARCA',
      displayName: 'SPDR S&P 500 ETF Trust',
    },

    [iwmId]: {
      id: iwmId,
      type: 'asset',
      parentId: usLargeCapWeightId,
      symbol: 'IWM',
      exchange: 'NYSEARCA',
      displayName: 'iShares Russell 2000 ETF',
    },

    [mdyId]: {
      id: mdyId,
      type: 'asset',
      parentId: usLargeCapWeightId,
      symbol: 'MDY',
      exchange: 'NYSEARCA',
      displayName: 'SPDR S&P MidCap 400 ETF',
    },

    [factorGroupId]: {
      id: factorGroupId,
      type: 'group',
      parentId: equityWeightId,
      name: 'Factor Tilt',
      childIds: [factorWeightId],
    },

    [factorWeightId]: {
      id: factorWeightId,
      type: 'weight',
      parentId: factorGroupId,
      method: 'equal',
      allocations: {},
      childIds: [mtumId, qualId, vlueId],
    },

    [mtumId]: {
      id: mtumId,
      type: 'asset',
      parentId: factorWeightId,
      symbol: 'MTUM',
      exchange: 'NYSEARCA',
      displayName: 'iShares MSCI USA Momentum Factor ETF',
    },

    [qualId]: {
      id: qualId,
      type: 'asset',
      parentId: factorWeightId,
      symbol: 'QUAL',
      exchange: 'NYSEARCA',
      displayName: 'iShares MSCI USA Quality Factor ETF',
    },

    [vlueId]: {
      id: vlueId,
      type: 'asset',
      parentId: factorWeightId,
      symbol: 'VLUE',
      exchange: 'NYSEARCA',
      displayName: 'iShares MSCI USA Value Factor ETF',
    },

    // Fixed Income
    [fixedIncomeGroupId]: {
      id: fixedIncomeGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'Fixed Income',
      childIds: [fixedIncomeWeightId],
    },

    [fixedIncomeWeightId]: {
      id: fixedIncomeWeightId,
      type: 'weight',
      parentId: fixedIncomeGroupId,
      method: 'specified',
      allocations: {
        [durationGroupId]: 50,
        [creditGroupId]: 30,
        [tipsId]: 20,
      },
      childIds: [durationGroupId, creditGroupId, tipsId],
    },

    [durationGroupId]: {
      id: durationGroupId,
      type: 'group',
      parentId: fixedIncomeWeightId,
      name: 'Duration Ladder',
      childIds: [durationWeightId],
    },

    [durationWeightId]: {
      id: durationWeightId,
      type: 'weight',
      parentId: durationGroupId,
      method: 'inverse_volatility',
      allocations: {},
      lookbackDays: 30,
      childIds: [shyId, iefId, tltId],
    },

    [shyId]: {
      id: shyId,
      type: 'asset',
      parentId: durationWeightId,
      symbol: 'SHY',
      exchange: 'NASDAQ',
      displayName: 'iShares 1-3 Year Treasury Bond ETF',
    },

    [iefId]: {
      id: iefId,
      type: 'asset',
      parentId: durationWeightId,
      symbol: 'IEF',
      exchange: 'NASDAQ',
      displayName: 'iShares 7-10 Year Treasury Bond ETF',
    },

    [tltId]: {
      id: tltId,
      type: 'asset',
      parentId: durationWeightId,
      symbol: 'TLT',
      exchange: 'NASDAQ',
      displayName: 'iShares 20+ Year Treasury Bond ETF',
    },

    [creditGroupId]: {
      id: creditGroupId,
      type: 'group',
      parentId: fixedIncomeWeightId,
      name: 'Credit',
      childIds: [creditWeightId],
    },

    [creditWeightId]: {
      id: creditWeightId,
      type: 'weight',
      parentId: creditGroupId,
      method: 'equal',
      allocations: {},
      childIds: [lqdId, hygId],
    },

    [lqdId]: {
      id: lqdId,
      type: 'asset',
      parentId: creditWeightId,
      symbol: 'LQD',
      exchange: 'NYSEARCA',
      displayName: 'iShares iBoxx $ Investment Grade Corporate Bond ETF',
    },

    [hygId]: {
      id: hygId,
      type: 'asset',
      parentId: creditWeightId,
      symbol: 'HYG',
      exchange: 'NYSEARCA',
      displayName: 'iShares iBoxx $ High Yield Corporate Bond ETF',
    },

    [tipsId]: {
      id: tipsId,
      type: 'asset',
      parentId: fixedIncomeWeightId,
      symbol: 'TIP',
      exchange: 'NYSEARCA',
      displayName: 'iShares TIPS Bond ETF',
    },

    // Real Assets with inflation condition
    [realAssetsGroupId]: {
      id: realAssetsGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'Real Assets',
      childIds: [realAssetsIfId, realAssetsElseId],
    },

    [realAssetsIfId]: {
      id: realAssetsIfId,
      type: 'if',
      parentId: realAssetsGroupId,
      condition: {
        left: { type: 'price', symbol: 'GLD', field: 'current' },
        comparator: 'gt',
        right: { type: 'indicator', indicator: 'sma', symbol: 'GLD', period: 50 },
      },
      conditionText: 'GLD > SMA(50) (inflation proxy)',
      childIds: [inflationWeightId],
    },

    [inflationWeightId]: {
      id: inflationWeightId,
      type: 'weight',
      parentId: realAssetsIfId,
      method: 'specified',
      allocations: {
        [gldId]: 40,
        [slvId]: 30,
        [dbcId]: 30,
      },
      childIds: [gldId, slvId, dbcId],
    },

    [gldId]: {
      id: gldId,
      type: 'asset',
      parentId: inflationWeightId,
      symbol: 'GLD',
      exchange: 'NYSEARCA',
      displayName: 'SPDR Gold Shares',
    },

    [slvId]: {
      id: slvId,
      type: 'asset',
      parentId: inflationWeightId,
      symbol: 'SLV',
      exchange: 'NYSEARCA',
      displayName: 'iShares Silver Trust',
    },

    [dbcId]: {
      id: dbcId,
      type: 'asset',
      parentId: inflationWeightId,
      symbol: 'DBC',
      exchange: 'NYSEARCA',
      displayName: 'Invesco DB Commodity Index Tracking Fund',
    },

    [realAssetsElseId]: {
      id: realAssetsElseId,
      type: 'else',
      parentId: realAssetsGroupId,
      ifBlockId: realAssetsIfId,
      childIds: [normalRealWeightId],
    },

    [normalRealWeightId]: {
      id: normalRealWeightId,
      type: 'weight',
      parentId: realAssetsElseId,
      method: 'equal',
      allocations: {},
      childIds: [gldNormalId, vnqId],
    },

    [gldNormalId]: {
      id: gldNormalId,
      type: 'asset',
      parentId: normalRealWeightId,
      symbol: 'GLD',
      exchange: 'NYSEARCA',
      displayName: 'SPDR Gold Shares',
    },

    [vnqId]: {
      id: vnqId,
      type: 'asset',
      parentId: normalRealWeightId,
      symbol: 'VNQ',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard Real Estate ETF',
    },

    // Alternatives
    [altGroupId]: {
      id: altGroupId,
      type: 'group',
      parentId: topWeightId,
      name: 'Alternatives',
      childIds: [altWeightId],
    },

    [altWeightId]: {
      id: altWeightId,
      type: 'weight',
      parentId: altGroupId,
      method: 'min_variance',
      allocations: {},
      lookbackDays: 90,
      childIds: [dbmfId, btalId],
    },

    [dbmfId]: {
      id: dbmfId,
      type: 'asset',
      parentId: altWeightId,
      symbol: 'DBMF',
      exchange: 'NYSEARCA',
      displayName: 'iMGP DBi Managed Futures Strategy ETF',
    },

    [btalId]: {
      id: btalId,
      type: 'asset',
      parentId: altWeightId,
      symbol: 'BTAL',
      exchange: 'NYSEARCA',
      displayName: 'AGFiQ US Market Neutral Anti-Beta Fund',
    },
  };

  return { rootId, blocks };
}

// ============================================================================
// Export all templates
// ============================================================================

export const STRATEGY_TEMPLATES: StrategyTemplate[] = [
  {
    id: 'risk-on-off',
    name: 'Risk-On/Risk-Off Tactical',
    description:
      'Switch between aggressive growth and defensive positions based on market regime (SPY vs 200-day SMA)',
    category: 'tactical',
    difficulty: 'advanced',
    blockTypes: ['root', 'group', 'weight', 'asset', 'if', 'else'],
    createTree: createRiskOnRiskOffStrategy,
  },
  {
    id: 'multi-factor-rotation',
    name: 'Multi-Factor Sector Rotation',
    description:
      'Dynamically rotate into top-performing sectors and stocks using filters with factor-based weighting',
    category: 'factor',
    difficulty: 'advanced',
    blockTypes: ['root', 'group', 'weight', 'asset', 'if', 'else', 'filter'],
    createTree: createMultiFactorRotationStrategy,
  },
  {
    id: 'all-weather',
    name: 'All-Weather Vol-Target',
    description:
      'Ray Dalio-inspired all-weather portfolio with volatility targeting and conditional commodity exposure',
    category: 'all-weather',
    difficulty: 'intermediate',
    blockTypes: ['root', 'group', 'weight', 'asset', 'if', 'else'],
    createTree: createAllWeatherStrategy,
  },
];

/**
 * Get a strategy template by ID
 */
export function getStrategyTemplate(id: string): StrategyTemplate | undefined {
  return STRATEGY_TEMPLATES.find((t) => t.id === id);
}
