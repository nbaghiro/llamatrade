// Puts the LlamaTrade shoot on the ad studio as its own product entry, so the posts about
// LlamaTrade can draw on the real product instead of drawn frames. Two themes: the product as
// it ships, and a dark preview injected at capture time (see capture.mjs for why the shadows
// are the open question, not the surfaces).
//
//   node ads-publish.mjs        DRY=1 to list
import { readdirSync } from "node:fs";
import { join } from "node:path";
const HERE = import.meta.dirname;
const { publish } = await import(join(process.env.HOME, "Documents/code/nbaghiro/scripts/ads-publish.mjs"));

// the composed plates come first: they are what a post actually uses, because a full-page
// capture at 1080x1350 cannot be read. The raw captures stay below as the source they were
// measured from.
const PLATES = [
    ["plate-01", "The language", "A strategy as a small program: groups, filters and weights."],
    ["plate-02", "The same strategy as a tree", "The builder and the code are two views of one definition."],
    ["plate-03", "What a strategy returns", "Target weights rather than orders."],
    ["plate-04", "A backtest", "522 trading days of Pullback Buyer against SPY, with its real figures."],
    ["plate-05", "Drawdown", "How far down the run went, and how long it took to recover."],
];

const SURFACES = [
    ["dashboard", "The dashboard", "The day's equity, the active strategies and what needs attention."],
    ["strategies", "Strategies", "Every strategy with its return, drawdown and allocation, and the one that is open shown as code."],
    ["backtest", "A backtest", "A run over history: the equity curve against the benchmark, the drawdown under it, and the figures beside it."],
    ["portfolio", "Portfolio", "Total equity, the open positions and the curve against the benchmark."],
    ["wallet", "Wallet", "Cash in the account and what is reserved against open orders."],
    ["copilot", "Copilot", "The assistant that writes a strategy in the allocation language."],
    ["marketing", "The public page", "What someone sees before they sign in."],
    ["login", "Signing in", "The sign-in page beside the product's own argument for itself."],
];
const have = new Set(readdirSync(join(HERE, "m")).filter((f) => f.endsWith(".png")));
const slidesFor = (name) => {
    const out = {};
    for (const theme of ["light", "dark"]) {
        const f = `lt-${name}-${theme}.png`;
        if (have.has(f)) out[theme] = { feed: [`shots/${f}`] };
    }
    return out;
};

await publish({
    project: { id: "llamatrade", name: "LlamaTrade", site: "llamatrade.ai" },
    manifest: {
        themes: [
            { id: "light", name: "Light", dark: false, bg: "#fbf8f1", ink: "#0d0d0d", accent: "#ff4d1c" },
            { id: "dark", name: "Dark (preview)", dark: true, bg: "#141417", ink: "#efece5", accent: "#ff4d1c" },
        ],
        formats: { feed: { w: 2880, h: 1800 } },
        posts: [
            ...PLATES.map(([slug, title, caption]) => ({
                slug,
                title,
                caption,
                defaultTheme: "light",
                slides: { light: { feed: [`shots/lt-${slug}.png`] } },
            })),
            ...SURFACES.filter(([n]) => Object.keys(slidesFor(n)).length).map(([slug, title, caption]) => ({
            slug,
            title,
            caption,
            defaultTheme: "light",
                slides: slidesFor(slug),
            })),
        ],
    },
    syncs: [{ from: join(HERE, "m"), to: "shots", include: ["*.png"] }],
    dryRun: !!process.env.DRY,
});
