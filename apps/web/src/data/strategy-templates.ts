/**
 * Strategy Templates - Pre-built strategies users can load as starting points
 *
 * These templates demonstrate all block types and real-world trading strategies.
 */

import { v4 as uuidv4 } from 'uuid';

import type { Block, BlockId, StrategyTree } from '../types/strategy-builder';

export type TemplateCategory = 'passive' | 'income' | 'growth' | 'all-weather' | 'tactical' | 'factor';
export type TemplateDifficulty = 'beginner' | 'intermediate' | 'advanced';

export interface StrategyTemplate {
  id: string;
  name: string;
  description: string;
  category: TemplateCategory;
  difficulty: TemplateDifficulty;
  blockTypes: string[];
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
// Template 4: Classic 60/40 Portfolio (Beginner)
// ============================================================================

function createClassic6040Strategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const weightId = uuidv4() as BlockId;
  const spyId = uuidv4() as BlockId;
  const aggId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Classic 60/40',
      childIds: [weightId],
    },
    [weightId]: {
      id: weightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: {
        [spyId]: 60,
        [aggId]: 40,
      },
      childIds: [spyId, aggId],
    },
    [spyId]: {
      id: spyId,
      type: 'asset',
      parentId: weightId,
      symbol: 'SPY',
      exchange: 'NYSEARCA',
      displayName: 'SPDR S&P 500 ETF Trust',
    },
    [aggId]: {
      id: aggId,
      type: 'asset',
      parentId: weightId,
      symbol: 'AGG',
      exchange: 'NYSEARCA',
      displayName: 'iShares Core US Aggregate Bond ETF',
    },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 5: Three-Fund Portfolio (Beginner)
// ============================================================================

function createThreeFundStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const weightId = uuidv4() as BlockId;
  const vtiId = uuidv4() as BlockId;
  const vxusId = uuidv4() as BlockId;
  const bndId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Three-Fund Portfolio',
      childIds: [weightId],
    },
    [weightId]: {
      id: weightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: {
        [vtiId]: 50,
        [vxusId]: 30,
        [bndId]: 20,
      },
      childIds: [vtiId, vxusId, bndId],
    },
    [vtiId]: {
      id: vtiId,
      type: 'asset',
      parentId: weightId,
      symbol: 'VTI',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard Total Stock Market ETF',
    },
    [vxusId]: {
      id: vxusId,
      type: 'asset',
      parentId: weightId,
      symbol: 'VXUS',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard Total International Stock ETF',
    },
    [bndId]: {
      id: bndId,
      type: 'asset',
      parentId: weightId,
      symbol: 'BND',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard Total Bond Market ETF',
    },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 6: Risk Parity (Intermediate)
// ============================================================================

function createRiskParityStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const weightId = uuidv4() as BlockId;
  const spyId = uuidv4() as BlockId;
  const tltId = uuidv4() as BlockId;
  const gldId = uuidv4() as BlockId;
  const dbcId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Risk Parity',
      childIds: [weightId],
    },
    [weightId]: {
      id: weightId,
      type: 'weight',
      parentId: rootId,
      method: 'inverse_volatility',
      allocations: {},
      lookbackDays: 60,
      childIds: [spyId, tltId, gldId, dbcId],
    },
    [spyId]: {
      id: spyId,
      type: 'asset',
      parentId: weightId,
      symbol: 'SPY',
      exchange: 'NYSEARCA',
      displayName: 'SPDR S&P 500 ETF Trust',
    },
    [tltId]: {
      id: tltId,
      type: 'asset',
      parentId: weightId,
      symbol: 'TLT',
      exchange: 'NASDAQ',
      displayName: 'iShares 20+ Year Treasury Bond ETF',
    },
    [gldId]: {
      id: gldId,
      type: 'asset',
      parentId: weightId,
      symbol: 'GLD',
      exchange: 'NYSEARCA',
      displayName: 'SPDR Gold Shares',
    },
    [dbcId]: {
      id: dbcId,
      type: 'asset',
      parentId: weightId,
      symbol: 'DBC',
      exchange: 'NYSEARCA',
      displayName: 'Invesco DB Commodity Index Fund',
    },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 7: Simple Trend Following (Advanced)
// ============================================================================

function createSimpleTrendFollowingStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;
  const ifBlockId = uuidv4() as BlockId;
  const elseBlockId = uuidv4() as BlockId;
  const spyId = uuidv4() as BlockId;
  const shyId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Simple Trend Following',
      childIds: [topWeightId],
    },
    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: {
        [ifBlockId]: 100,
        [elseBlockId]: 100,
      },
      childIds: [ifBlockId, elseBlockId],
    },
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
      childIds: [spyId],
    },
    [spyId]: {
      id: spyId,
      type: 'asset',
      parentId: ifBlockId,
      symbol: 'SPY',
      exchange: 'NYSEARCA',
      displayName: 'SPDR S&P 500 ETF Trust',
    },
    [elseBlockId]: {
      id: elseBlockId,
      type: 'else',
      parentId: topWeightId,
      ifBlockId: ifBlockId,
      childIds: [shyId],
    },
    [shyId]: {
      id: shyId,
      type: 'asset',
      parentId: elseBlockId,
      symbol: 'SHY',
      exchange: 'NASDAQ',
      displayName: 'iShares 1-3 Year Treasury Bond ETF',
    },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 8: Equal Weight Sectors (Beginner)
// ============================================================================

function createEqualWeightSectorsStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const weightId = uuidv4() as BlockId;
  const xlkId = uuidv4() as BlockId;
  const xlvId = uuidv4() as BlockId;
  const xlfId = uuidv4() as BlockId;
  const xlyId = uuidv4() as BlockId;
  const xlpId = uuidv4() as BlockId;
  const xleId = uuidv4() as BlockId;
  const xliId = uuidv4() as BlockId;
  const xluId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Equal Weight Sectors',
      childIds: [weightId],
    },
    [weightId]: {
      id: weightId,
      type: 'weight',
      parentId: rootId,
      method: 'equal',
      allocations: {},
      childIds: [xlkId, xlvId, xlfId, xlyId, xlpId, xleId, xliId, xluId],
    },
    [xlkId]: { id: xlkId, type: 'asset', parentId: weightId, symbol: 'XLK', exchange: 'NYSEARCA', displayName: 'Technology Select Sector SPDR' },
    [xlvId]: { id: xlvId, type: 'asset', parentId: weightId, symbol: 'XLV', exchange: 'NYSEARCA', displayName: 'Health Care Select Sector SPDR' },
    [xlfId]: { id: xlfId, type: 'asset', parentId: weightId, symbol: 'XLF', exchange: 'NYSEARCA', displayName: 'Financial Select Sector SPDR' },
    [xlyId]: { id: xlyId, type: 'asset', parentId: weightId, symbol: 'XLY', exchange: 'NYSEARCA', displayName: 'Consumer Discretionary SPDR' },
    [xlpId]: { id: xlpId, type: 'asset', parentId: weightId, symbol: 'XLP', exchange: 'NYSEARCA', displayName: 'Consumer Staples Select Sector SPDR' },
    [xleId]: { id: xleId, type: 'asset', parentId: weightId, symbol: 'XLE', exchange: 'NYSEARCA', displayName: 'Energy Select Sector SPDR' },
    [xliId]: { id: xliId, type: 'asset', parentId: weightId, symbol: 'XLI', exchange: 'NYSEARCA', displayName: 'Industrial Select Sector SPDR' },
    [xluId]: { id: xluId, type: 'asset', parentId: weightId, symbol: 'XLU', exchange: 'NYSEARCA', displayName: 'Utilities Select Sector SPDR' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 9: Dividend Aristocrats (Beginner)
// ============================================================================

function createDividendAristocratsStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const groupId = uuidv4() as BlockId;
  const weightId = uuidv4() as BlockId;
  const jnjId = uuidv4() as BlockId;
  const pgId = uuidv4() as BlockId;
  const koId = uuidv4() as BlockId;
  const pepId = uuidv4() as BlockId;
  const mcdId = uuidv4() as BlockId;
  const wmtId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Dividend Aristocrats',
      childIds: [groupId],
    },
    [groupId]: {
      id: groupId,
      type: 'group',
      parentId: rootId,
      name: 'Aristocrats',
      childIds: [weightId],
    },
    [weightId]: {
      id: weightId,
      type: 'weight',
      parentId: groupId,
      method: 'equal',
      allocations: {},
      childIds: [jnjId, pgId, koId, pepId, mcdId, wmtId],
    },
    [jnjId]: { id: jnjId, type: 'asset', parentId: weightId, symbol: 'JNJ', exchange: 'NYSE', displayName: 'Johnson & Johnson' },
    [pgId]: { id: pgId, type: 'asset', parentId: weightId, symbol: 'PG', exchange: 'NYSE', displayName: 'Procter & Gamble' },
    [koId]: { id: koId, type: 'asset', parentId: weightId, symbol: 'KO', exchange: 'NYSE', displayName: 'Coca-Cola' },
    [pepId]: { id: pepId, type: 'asset', parentId: weightId, symbol: 'PEP', exchange: 'NASDAQ', displayName: 'PepsiCo' },
    [mcdId]: { id: mcdId, type: 'asset', parentId: weightId, symbol: 'MCD', exchange: 'NYSE', displayName: "McDonald's" },
    [wmtId]: { id: wmtId, type: 'asset', parentId: weightId, symbol: 'WMT', exchange: 'NYSE', displayName: 'Walmart' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 10: Tech Growth (Beginner)
// ============================================================================

function createTechGrowthStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const weightId = uuidv4() as BlockId;
  const aaplId = uuidv4() as BlockId;
  const msftId = uuidv4() as BlockId;
  const googlId = uuidv4() as BlockId;
  const amznId = uuidv4() as BlockId;
  const nvdaId = uuidv4() as BlockId;
  const metaId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Tech Growth',
      childIds: [weightId],
    },
    [weightId]: {
      id: weightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: {
        [aaplId]: 25,
        [msftId]: 20,
        [googlId]: 20,
        [amznId]: 15,
        [nvdaId]: 10,
        [metaId]: 10,
      },
      childIds: [aaplId, msftId, googlId, amznId, nvdaId, metaId],
    },
    [aaplId]: { id: aaplId, type: 'asset', parentId: weightId, symbol: 'AAPL', exchange: 'NASDAQ', displayName: 'Apple Inc' },
    [msftId]: { id: msftId, type: 'asset', parentId: weightId, symbol: 'MSFT', exchange: 'NASDAQ', displayName: 'Microsoft Corp' },
    [googlId]: { id: googlId, type: 'asset', parentId: weightId, symbol: 'GOOGL', exchange: 'NASDAQ', displayName: 'Alphabet Inc' },
    [amznId]: { id: amznId, type: 'asset', parentId: weightId, symbol: 'AMZN', exchange: 'NASDAQ', displayName: 'Amazon.com Inc' },
    [nvdaId]: { id: nvdaId, type: 'asset', parentId: weightId, symbol: 'NVDA', exchange: 'NASDAQ', displayName: 'NVIDIA Corp' },
    [metaId]: { id: metaId, type: 'asset', parentId: weightId, symbol: 'META', exchange: 'NASDAQ', displayName: 'Meta Platforms Inc' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 11: Core-Satellite (Intermediate)
// ============================================================================

function createCoreSatelliteStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;
  const coreGroupId = uuidv4() as BlockId;
  const coreWeightId = uuidv4() as BlockId;
  const spyId = uuidv4() as BlockId;
  const vtiId = uuidv4() as BlockId;
  const satelliteGroupId = uuidv4() as BlockId;
  const satelliteWeightId = uuidv4() as BlockId;
  const qqqId = uuidv4() as BlockId;
  const arkkId = uuidv4() as BlockId;
  const bondsGroupId = uuidv4() as BlockId;
  const bndId = uuidv4() as BlockId;
  const tltId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Core-Satellite',
      childIds: [topWeightId],
    },
    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: { [coreGroupId]: 60, [satelliteGroupId]: 25, [bondsGroupId]: 15 },
      childIds: [coreGroupId, satelliteGroupId, bondsGroupId],
    },
    [coreGroupId]: { id: coreGroupId, type: 'group', parentId: topWeightId, name: 'Core Holdings', childIds: [coreWeightId] },
    [coreWeightId]: {
      id: coreWeightId,
      type: 'weight',
      parentId: coreGroupId,
      method: 'equal',
      allocations: {},
      childIds: [spyId, vtiId],
    },
    [spyId]: { id: spyId, type: 'asset', parentId: coreWeightId, symbol: 'SPY', exchange: 'NYSEARCA', displayName: 'SPDR S&P 500 ETF Trust' },
    [vtiId]: { id: vtiId, type: 'asset', parentId: coreWeightId, symbol: 'VTI', exchange: 'NYSEARCA', displayName: 'Vanguard Total Stock Market ETF' },
    [satelliteGroupId]: { id: satelliteGroupId, type: 'group', parentId: topWeightId, name: 'Growth Satellites', childIds: [satelliteWeightId] },
    [satelliteWeightId]: {
      id: satelliteWeightId,
      type: 'weight',
      parentId: satelliteGroupId,
      method: 'inverse_volatility',
      allocations: {},
      lookbackDays: 30,
      childIds: [qqqId, arkkId],
    },
    [qqqId]: { id: qqqId, type: 'asset', parentId: satelliteWeightId, symbol: 'QQQ', exchange: 'NASDAQ', displayName: 'Invesco QQQ Trust' },
    [arkkId]: { id: arkkId, type: 'asset', parentId: satelliteWeightId, symbol: 'ARKK', exchange: 'NYSEARCA', displayName: 'ARK Innovation ETF' },
    [bondsGroupId]: { id: bondsGroupId, type: 'group', parentId: topWeightId, name: 'Bonds', childIds: [bndId, tltId] },
    [bndId]: { id: bndId, type: 'asset', parentId: bondsGroupId, symbol: 'BND', exchange: 'NYSEARCA', displayName: 'Vanguard Total Bond Market ETF' },
    [tltId]: { id: tltId, type: 'asset', parentId: bondsGroupId, symbol: 'TLT', exchange: 'NASDAQ', displayName: 'iShares 20+ Year Treasury ETF' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 12: Momentum Sectors (Intermediate)
// ============================================================================

function createMomentumSectorsStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const weightId = uuidv4() as BlockId;
  const xlkId = uuidv4() as BlockId;
  const xlvId = uuidv4() as BlockId;
  const xlfId = uuidv4() as BlockId;
  const xlyId = uuidv4() as BlockId;
  const xleId = uuidv4() as BlockId;
  const xliId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Momentum Sectors',
      childIds: [weightId],
    },
    [weightId]: {
      id: weightId,
      type: 'weight',
      parentId: rootId,
      method: 'momentum',
      allocations: {},
      lookbackDays: 90,
      childIds: [xlkId, xlvId, xlfId, xlyId, xleId, xliId],
    },
    [xlkId]: { id: xlkId, type: 'asset', parentId: weightId, symbol: 'XLK', exchange: 'NYSEARCA', displayName: 'Technology Select Sector SPDR' },
    [xlvId]: { id: xlvId, type: 'asset', parentId: weightId, symbol: 'XLV', exchange: 'NYSEARCA', displayName: 'Health Care Select Sector SPDR' },
    [xlfId]: { id: xlfId, type: 'asset', parentId: weightId, symbol: 'XLF', exchange: 'NYSEARCA', displayName: 'Financial Select Sector SPDR' },
    [xlyId]: { id: xlyId, type: 'asset', parentId: weightId, symbol: 'XLY', exchange: 'NYSEARCA', displayName: 'Consumer Discretionary SPDR' },
    [xleId]: { id: xleId, type: 'asset', parentId: weightId, symbol: 'XLE', exchange: 'NYSEARCA', displayName: 'Energy Select Sector SPDR' },
    [xliId]: { id: xliId, type: 'asset', parentId: weightId, symbol: 'XLI', exchange: 'NYSEARCA', displayName: 'Industrial Select Sector SPDR' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 13: Income Focus (Intermediate)
// ============================================================================

function createIncomeFocusStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;
  const divGroupId = uuidv4() as BlockId;
  const divWeightId = uuidv4() as BlockId;
  const vymId = uuidv4() as BlockId;
  const schdId = uuidv4() as BlockId;
  const reitGroupId = uuidv4() as BlockId;
  const vnqId = uuidv4() as BlockId;
  const bondGroupId = uuidv4() as BlockId;
  const bondWeightId = uuidv4() as BlockId;
  const hygId = uuidv4() as BlockId;
  const lqdId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Income Focus',
      childIds: [topWeightId],
    },
    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: { [divGroupId]: 40, [reitGroupId]: 30, [bondGroupId]: 30 },
      childIds: [divGroupId, reitGroupId, bondGroupId],
    },
    [divGroupId]: { id: divGroupId, type: 'group', parentId: topWeightId, name: 'Dividend Stocks', childIds: [divWeightId] },
    [divWeightId]: {
      id: divWeightId,
      type: 'weight',
      parentId: divGroupId,
      method: 'equal',
      allocations: {},
      childIds: [vymId, schdId],
    },
    [vymId]: { id: vymId, type: 'asset', parentId: divWeightId, symbol: 'VYM', exchange: 'NYSEARCA', displayName: 'Vanguard High Dividend Yield ETF' },
    [schdId]: { id: schdId, type: 'asset', parentId: divWeightId, symbol: 'SCHD', exchange: 'NYSEARCA', displayName: 'Schwab US Dividend Equity ETF' },
    [reitGroupId]: { id: reitGroupId, type: 'group', parentId: topWeightId, name: 'REITs', childIds: [vnqId] },
    [vnqId]: { id: vnqId, type: 'asset', parentId: reitGroupId, symbol: 'VNQ', exchange: 'NYSEARCA', displayName: 'Vanguard Real Estate ETF' },
    [bondGroupId]: { id: bondGroupId, type: 'group', parentId: topWeightId, name: 'Bonds', childIds: [bondWeightId] },
    [bondWeightId]: {
      id: bondWeightId,
      type: 'weight',
      parentId: bondGroupId,
      method: 'equal',
      allocations: {},
      childIds: [hygId, lqdId],
    },
    [hygId]: { id: hygId, type: 'asset', parentId: bondWeightId, symbol: 'HYG', exchange: 'NYSEARCA', displayName: 'iShares High Yield Corporate Bond ETF' },
    [lqdId]: { id: lqdId, type: 'asset', parentId: bondWeightId, symbol: 'LQD', exchange: 'NYSEARCA', displayName: 'iShares Investment Grade Corporate Bond ETF' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 14: Global Asset Allocation (Intermediate)
// ============================================================================

function createGlobalAssetAllocationStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;
  const usGroupId = uuidv4() as BlockId;
  const vtiId = uuidv4() as BlockId;
  const intlGroupId = uuidv4() as BlockId;
  const intlWeightId = uuidv4() as BlockId;
  const veaId = uuidv4() as BlockId;
  const vwoId = uuidv4() as BlockId;
  const bondGroupId = uuidv4() as BlockId;
  const bndId = uuidv4() as BlockId;
  const altGroupId = uuidv4() as BlockId;
  const altWeightId = uuidv4() as BlockId;
  const vnqId = uuidv4() as BlockId;
  const gldId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Global Asset Allocation',
      childIds: [topWeightId],
    },
    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: { [usGroupId]: 40, [intlGroupId]: 20, [bondGroupId]: 25, [altGroupId]: 15 },
      childIds: [usGroupId, intlGroupId, bondGroupId, altGroupId],
    },
    [usGroupId]: { id: usGroupId, type: 'group', parentId: topWeightId, name: 'US Equities', childIds: [vtiId] },
    [vtiId]: { id: vtiId, type: 'asset', parentId: usGroupId, symbol: 'VTI', exchange: 'NYSEARCA', displayName: 'Vanguard Total Stock Market ETF' },
    [intlGroupId]: { id: intlGroupId, type: 'group', parentId: topWeightId, name: 'International', childIds: [intlWeightId] },
    [intlWeightId]: {
      id: intlWeightId,
      type: 'weight',
      parentId: intlGroupId,
      method: 'equal',
      allocations: {},
      childIds: [veaId, vwoId],
    },
    [veaId]: { id: veaId, type: 'asset', parentId: intlWeightId, symbol: 'VEA', exchange: 'NYSEARCA', displayName: 'Vanguard FTSE Developed Markets ETF' },
    [vwoId]: { id: vwoId, type: 'asset', parentId: intlWeightId, symbol: 'VWO', exchange: 'NYSEARCA', displayName: 'Vanguard FTSE Emerging Markets ETF' },
    [bondGroupId]: { id: bondGroupId, type: 'group', parentId: topWeightId, name: 'Fixed Income', childIds: [bndId] },
    [bndId]: { id: bndId, type: 'asset', parentId: bondGroupId, symbol: 'BND', exchange: 'NYSEARCA', displayName: 'Vanguard Total Bond Market ETF' },
    [altGroupId]: { id: altGroupId, type: 'group', parentId: topWeightId, name: 'Alternatives', childIds: [altWeightId] },
    [altWeightId]: {
      id: altWeightId,
      type: 'weight',
      parentId: altGroupId,
      method: 'equal',
      allocations: {},
      childIds: [vnqId, gldId],
    },
    [vnqId]: { id: vnqId, type: 'asset', parentId: altWeightId, symbol: 'VNQ', exchange: 'NYSEARCA', displayName: 'Vanguard Real Estate ETF' },
    [gldId]: { id: gldId, type: 'asset', parentId: altWeightId, symbol: 'GLD', exchange: 'NYSEARCA', displayName: 'SPDR Gold Shares' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 15: Dual Moving Average (Advanced)
// ============================================================================

function createDualMovingAverageStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;
  const equityGroupId = uuidv4() as BlockId;
  const ifBlockId = uuidv4() as BlockId;
  const elseBlockId = uuidv4() as BlockId;
  const riskOnWeightId = uuidv4() as BlockId;
  const qqqId = uuidv4() as BlockId;
  const spyId = uuidv4() as BlockId;
  const shyId = uuidv4() as BlockId;
  const bondGroupId = uuidv4() as BlockId;
  const bondWeightId = uuidv4() as BlockId;
  const bndId = uuidv4() as BlockId;
  const tipId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Dual Moving Average',
      childIds: [topWeightId],
    },
    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: { [equityGroupId]: 70, [bondGroupId]: 30 },
      childIds: [equityGroupId, bondGroupId],
    },
    [equityGroupId]: { id: equityGroupId, type: 'group', parentId: topWeightId, name: 'Equities', childIds: [ifBlockId, elseBlockId] },
    [ifBlockId]: {
      id: ifBlockId,
      type: 'if',
      parentId: equityGroupId,
      condition: {
        left: { type: 'indicator', indicator: 'sma', symbol: 'SPY', period: 50 },
        comparator: 'gt',
        right: { type: 'indicator', indicator: 'sma', symbol: 'SPY', period: 200 },
      },
      conditionText: 'SMA(SPY, 50) > SMA(SPY, 200)',
      childIds: [riskOnWeightId],
    },
    [riskOnWeightId]: {
      id: riskOnWeightId,
      type: 'weight',
      parentId: ifBlockId,
      method: 'equal',
      allocations: {},
      childIds: [qqqId, spyId],
    },
    [qqqId]: { id: qqqId, type: 'asset', parentId: riskOnWeightId, symbol: 'QQQ', exchange: 'NASDAQ', displayName: 'Invesco QQQ Trust' },
    [spyId]: { id: spyId, type: 'asset', parentId: riskOnWeightId, symbol: 'SPY', exchange: 'NYSEARCA', displayName: 'SPDR S&P 500 ETF Trust' },
    [elseBlockId]: {
      id: elseBlockId,
      type: 'else',
      parentId: equityGroupId,
      ifBlockId: ifBlockId,
      childIds: [shyId],
    },
    [shyId]: { id: shyId, type: 'asset', parentId: elseBlockId, symbol: 'SHY', exchange: 'NASDAQ', displayName: 'iShares 1-3 Year Treasury ETF' },
    [bondGroupId]: { id: bondGroupId, type: 'group', parentId: topWeightId, name: 'Bonds', childIds: [bondWeightId] },
    [bondWeightId]: {
      id: bondWeightId,
      type: 'weight',
      parentId: bondGroupId,
      method: 'equal',
      allocations: {},
      childIds: [bndId, tipId],
    },
    [bndId]: { id: bndId, type: 'asset', parentId: bondWeightId, symbol: 'BND', exchange: 'NYSEARCA', displayName: 'Vanguard Total Bond Market ETF' },
    [tipId]: { id: tipId, type: 'asset', parentId: bondWeightId, symbol: 'TIP', exchange: 'NYSEARCA', displayName: 'iShares TIPS Bond ETF' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Template 16: Volatility Regime (Advanced)
// ============================================================================

function createVolatilityRegimeStrategy(): StrategyTree {
  const rootId = uuidv4() as BlockId;
  const topWeightId = uuidv4() as BlockId;
  const equityGroupId = uuidv4() as BlockId;
  const ifBlockId = uuidv4() as BlockId;
  const elseBlockId = uuidv4() as BlockId;
  const riskOnWeightId = uuidv4() as BlockId;
  const qqqId = uuidv4() as BlockId;
  const smhId = uuidv4() as BlockId;
  const riskOffWeightId = uuidv4() as BlockId;
  const xlpId = uuidv4() as BlockId;
  const xluId = uuidv4() as BlockId;
  const safeGroupId = uuidv4() as BlockId;
  const safeWeightId = uuidv4() as BlockId;
  const tltId = uuidv4() as BlockId;
  const gldId = uuidv4() as BlockId;

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Volatility Regime',
      childIds: [topWeightId],
    },
    [topWeightId]: {
      id: topWeightId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: { [equityGroupId]: 60, [safeGroupId]: 40 },
      childIds: [equityGroupId, safeGroupId],
    },
    [equityGroupId]: { id: equityGroupId, type: 'group', parentId: topWeightId, name: 'Equity Allocation', childIds: [ifBlockId, elseBlockId] },
    [ifBlockId]: {
      id: ifBlockId,
      type: 'if',
      parentId: equityGroupId,
      condition: {
        left: { type: 'price', symbol: 'VIX', field: 'current' },
        comparator: 'lt',
        right: { type: 'number', value: 20 },
      },
      conditionText: 'VIX < 20',
      childIds: [riskOnWeightId],
    },
    [riskOnWeightId]: {
      id: riskOnWeightId,
      type: 'weight',
      parentId: ifBlockId,
      method: 'momentum',
      allocations: {},
      lookbackDays: 30,
      childIds: [qqqId, smhId],
    },
    [qqqId]: { id: qqqId, type: 'asset', parentId: riskOnWeightId, symbol: 'QQQ', exchange: 'NASDAQ', displayName: 'Invesco QQQ Trust' },
    [smhId]: { id: smhId, type: 'asset', parentId: riskOnWeightId, symbol: 'SMH', exchange: 'NYSEARCA', displayName: 'VanEck Semiconductor ETF' },
    [elseBlockId]: {
      id: elseBlockId,
      type: 'else',
      parentId: equityGroupId,
      ifBlockId: ifBlockId,
      childIds: [riskOffWeightId],
    },
    [riskOffWeightId]: {
      id: riskOffWeightId,
      type: 'weight',
      parentId: elseBlockId,
      method: 'inverse_volatility',
      allocations: {},
      lookbackDays: 30,
      childIds: [xlpId, xluId],
    },
    [xlpId]: { id: xlpId, type: 'asset', parentId: riskOffWeightId, symbol: 'XLP', exchange: 'NYSEARCA', displayName: 'Consumer Staples Select Sector SPDR' },
    [xluId]: { id: xluId, type: 'asset', parentId: riskOffWeightId, symbol: 'XLU', exchange: 'NYSEARCA', displayName: 'Utilities Select Sector SPDR' },
    [safeGroupId]: { id: safeGroupId, type: 'group', parentId: topWeightId, name: 'Safe Haven', childIds: [safeWeightId] },
    [safeWeightId]: {
      id: safeWeightId,
      type: 'weight',
      parentId: safeGroupId,
      method: 'equal',
      allocations: {},
      childIds: [tltId, gldId],
    },
    [tltId]: { id: tltId, type: 'asset', parentId: safeWeightId, symbol: 'TLT', exchange: 'NASDAQ', displayName: 'iShares 20+ Year Treasury ETF' },
    [gldId]: { id: gldId, type: 'asset', parentId: safeWeightId, symbol: 'GLD', exchange: 'NYSEARCA', displayName: 'SPDR Gold Shares' },
  };

  return { rootId, blocks };
}

// ============================================================================
// Export all templates
// ============================================================================

export const STRATEGY_TEMPLATES: StrategyTemplate[] = [
  // ========== BEGINNER ==========
  {
    id: 'classic-60-40',
    name: 'Classic 60/40',
    description: 'The foundational portfolio—60% stocks, 40% bonds. Simple, time-tested, effective.',
    category: 'passive',
    difficulty: 'beginner',
    blockTypes: ['root', 'weight', 'asset'],
    createTree: createClassic6040Strategy,
  },
  {
    id: 'three-fund',
    name: 'Three-Fund Portfolio',
    description: 'Bogleheads classic—total US market, international, and bonds for maximum diversification.',
    category: 'passive',
    difficulty: 'beginner',
    blockTypes: ['root', 'weight', 'asset'],
    createTree: createThreeFundStrategy,
  },
  {
    id: 'equal-weight-sectors',
    name: 'Equal Weight Sectors',
    description: 'Equal allocation across major market sectors. Removes market-cap bias.',
    category: 'passive',
    difficulty: 'beginner',
    blockTypes: ['root', 'weight', 'asset'],
    createTree: createEqualWeightSectorsStrategy,
  },
  {
    id: 'dividend-aristocrats',
    name: 'Dividend Aristocrats',
    description: 'Blue-chip companies with 25+ years of consecutive dividend increases.',
    category: 'income',
    difficulty: 'beginner',
    blockTypes: ['root', 'group', 'weight', 'asset'],
    createTree: createDividendAristocratsStrategy,
  },
  {
    id: 'tech-growth',
    name: 'Tech Growth',
    description: 'Concentrated exposure to leading technology companies with conviction weights.',
    category: 'growth',
    difficulty: 'beginner',
    blockTypes: ['root', 'weight', 'asset'],
    createTree: createTechGrowthStrategy,
  },
  // ========== INTERMEDIATE ==========
  {
    id: 'core-satellite',
    name: 'Core-Satellite',
    description: 'Stable core of index funds combined with satellite positions in higher-conviction plays.',
    category: 'passive',
    difficulty: 'intermediate',
    blockTypes: ['root', 'group', 'weight', 'asset'],
    createTree: createCoreSatelliteStrategy,
  },
  {
    id: 'risk-parity',
    name: 'Risk Parity',
    description: 'Allocate by risk contribution using inverse volatility—equal risk across asset classes.',
    category: 'all-weather',
    difficulty: 'intermediate',
    blockTypes: ['root', 'weight', 'asset'],
    createTree: createRiskParityStrategy,
  },
  {
    id: 'momentum-sectors',
    name: 'Momentum Sectors',
    description: 'Weight sectors by recent momentum—more allocation to stronger performers.',
    category: 'factor',
    difficulty: 'intermediate',
    blockTypes: ['root', 'weight', 'asset'],
    createTree: createMomentumSectorsStrategy,
  },
  {
    id: 'income-focus',
    name: 'Income Focus',
    description: 'Maximize income through dividends, REITs, and high-yield bonds.',
    category: 'income',
    difficulty: 'intermediate',
    blockTypes: ['root', 'group', 'weight', 'asset'],
    createTree: createIncomeFocusStrategy,
  },
  {
    id: 'global-allocation',
    name: 'Global Asset Allocation',
    description: 'Globally diversified portfolio across geographies and asset classes.',
    category: 'passive',
    difficulty: 'intermediate',
    blockTypes: ['root', 'group', 'weight', 'asset'],
    createTree: createGlobalAssetAllocationStrategy,
  },
  {
    id: 'all-weather',
    name: 'All-Weather Vol-Target',
    description: 'Ray Dalio-inspired all-weather portfolio with volatility targeting and conditional commodities.',
    category: 'all-weather',
    difficulty: 'intermediate',
    blockTypes: ['root', 'group', 'weight', 'asset', 'if', 'else'],
    createTree: createAllWeatherStrategy,
  },
  // ========== ADVANCED ==========
  {
    id: 'simple-trend',
    name: 'Simple Trend Following',
    description: 'Stay invested above 200-day SMA, move to bonds when below. Classic trend strategy.',
    category: 'tactical',
    difficulty: 'advanced',
    blockTypes: ['root', 'weight', 'asset', 'if', 'else'],
    createTree: createSimpleTrendFollowingStrategy,
  },
  {
    id: 'dual-ma',
    name: 'Dual Moving Average',
    description: 'Golden cross strategy—bullish when 50-day crosses above 200-day moving average.',
    category: 'tactical',
    difficulty: 'advanced',
    blockTypes: ['root', 'group', 'weight', 'asset', 'if', 'else'],
    createTree: createDualMovingAverageStrategy,
  },
  {
    id: 'volatility-regime',
    name: 'Volatility Regime',
    description: 'Adjust allocation based on VIX levels—aggressive in low vol, defensive in high vol.',
    category: 'tactical',
    difficulty: 'advanced',
    blockTypes: ['root', 'group', 'weight', 'asset', 'if', 'else'],
    createTree: createVolatilityRegimeStrategy,
  },
  {
    id: 'risk-on-off',
    name: 'Risk-On/Risk-Off Tactical',
    description: 'Switch between aggressive growth and defensive positions based on market regime.',
    category: 'tactical',
    difficulty: 'advanced',
    blockTypes: ['root', 'group', 'weight', 'asset', 'if', 'else'],
    createTree: createRiskOnRiskOffStrategy,
  },
  {
    id: 'multi-factor-rotation',
    name: 'Multi-Factor Sector Rotation',
    description: 'Rotate into top-performing sectors using filters with factor-based weighting.',
    category: 'factor',
    difficulty: 'advanced',
    blockTypes: ['root', 'group', 'weight', 'asset', 'if', 'else', 'filter'],
    createTree: createMultiFactorRotationStrategy,
  },
];

/**
 * Get a strategy template by ID
 */
export function getStrategyTemplate(id: string): StrategyTemplate | undefined {
  return STRATEGY_TEMPLATES.find((t) => t.id === id);
}
