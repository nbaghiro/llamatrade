# Design & Brand

Source-of-truth documentation for the LlamaTrade brand, social presence, and
marketing creative. These docs are the canonical reference — the marketing site
(`apps/web/src/marketing/`) and design tokens
(`apps/web/src/styles/monolith.css`) implement them.

---

## Documents

| Document | Description |
|----------|-------------|
| [Brand Guidelines](brand-guidelines.md) | The "Monolith" design system: logo, color, type, voice, form language, compliance, and canonical product facts/copy |
| [Social Accounts](social-accounts.md) | Copy-paste set-up sheet for every platform — handles, names, bios (sized to limits), categories, asset specs |
| [Launch Campaign](social-campaign.md) | Closed-beta content library — IG Stories, LinkedIn, X, blog — with copy, media direction, cadence, and hashtags |
| [Ad Creative](ad-creative.md) | Ad system — six directions, the placement matrix, per-placement copy, and finance-ad compliance |

---

## How to use

- **Writing any external copy?** Start with [Brand Guidelines §2 (voice)](brand-guidelines.md#2-voice--tone)
  and §8 (compliance). Pull approved lines from §2.2.
- **Creating the social accounts?** Everything you need is in
  [Social Accounts](social-accounts.md) — reserve `llamatrade` everywhere first.
- **Shipping a post or ad?** Use the ready copy in [Launch Campaign](social-campaign.md)
  / [Ad Creative](ad-creative.md); keep DSL to the real grammar.

## Ground rules (apply to everything)

1. **Monolith or nothing** — bone / ink / signal-orange, Anton · Archivo · Space
   Mono, zero radius, hard offset shadows.
2. **One accent** — signal orange `#ff4d1c`, spent once per surface.
3. **Real DSL only** — never invent strategy tokens.
4. **Illustrative + not investment advice** — on any asset showing figures.
5. **We never custody funds** — the user brings their own keys.

---

## Provenance

These docs were extracted from the brand/social explorer prototype and rewritten
as maintainable reference. Pixel-level authority stays with the code
(`monolith.css`, `Logo.tsx`); meaning and usage authority lives here.
