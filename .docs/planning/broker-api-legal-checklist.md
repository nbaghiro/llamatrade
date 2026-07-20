# Broker API — Regulatory & Legal Checklist (for securities counsel)

**Status:** Phase-0 (WS-B). Decision input, not implementation.
**Related:** [`broker-provider-seam.md`](./broker-provider-seam.md) (WS-A, execution architecture), [`broker-setup-individual-traders.md`](./broker-setup-individual-traders.md) (the non-custodial BYO product that ships first).

> ⚠️ **This is not legal advice.** It is an engineering/product-side map of the regulatory surface for moving from BYO (non-custodial) to **embedded brokerage via Alpaca's Broker API** (Alpaca custodies; LlamaTrade opens & orchestrates customer sub-accounts). It exists to be **handed to securities counsel** and to a named compliance officer. Every item marked **[COUNSEL]** is a question for them, not a decision engineering can make. The go/no-go is a business + legal decision.

---

## 0. The structural facts (Alpaca's role)

- **Alpaca Securities LLC / Alpaca Clearing LLC** is a registered broker-dealer, **member FINRA + SIPC**. It is the **broker-dealer of record and custodian** — it holds customer funds and securities.
- **Alpaca Crypto LLC** is a **FinCEN-registered MSB** (NMLS #2160858), *not* SIPC/FINRA — crypto is a different regulatory regime (state money-transmitter / MSB exposure).
- Because Alpaca custodies, **equities money flows to Alpaca, not through LlamaTrade** → this is what generally keeps LlamaTrade *out* of money-transmitter territory on the equities side. Preserve this; anything that routes customer funds *through* our own accounts changes the analysis. **[COUNSEL]**

---

## 1. Decision 1 — Regulatory posture (which Alpaca model)

Alpaca supports four integration models. The model dictates whether **LlamaTrade itself** must hold a registration.

| Model | Must LlamaTrade be registered? | Who runs KYC/approval | Notes |
|---|---|---|---|
| **Trading/Investing app** ✅ recommended | **No** — Alpaca is BD of record | Alpaca runs KYC async; we collect data + own UX | Lightest path; Alpaca vets our compliance program |
| **RIA** | Yes — SEC-registered RIA | Alpaca owns approval (unless our CIP is vetted) | Only if we charge AUM/advisory fees; no built-in advisory-fee/allocation |
| **Fully-disclosed BD** | Yes — registered broker-dealer | **We** run CIP/KYC/AML | Heavy; we own reporting |
| **Omnibus BD** | Yes — registered broker-dealer | One omnibus account; we do sub-accounting + tax reporting (non-US → IRS FFI/QI) | Heaviest |

**Recommendation to counsel:** target the **"Trading/Investing app"** model — launch *without* LlamaTrade becoming a broker-dealer, with Alpaca as BD of record. **[COUNSEL]** confirm this posture fits our business (self-directed retail app), and whether any planned feature (advisory fees, discretionary trading, model portfolios we manage) forces us up into RIA/BD.

---

## 2. Decision 2 — Reg BI / the AI copilot (the highest-stakes item)

**This is the single decision that most shapes the product, and it applies whether or not we go embedded.**

LlamaTrade ships an **AI copilot**. If the copilot *recommends* securities to retail customers, LlamaTrade likely triggers:
- **Regulation Best Interest (Reg BI)** — broker conduct standard for recommendations to retail; and/or
- **Investment Advisers Act** — making LlamaTrade an *investment adviser* (registration, fiduciary duty, Form ADV/CRS).

The fork:

- **(A) Strictly self-directed** *(recommended for launch)* — the copilot provides tools, education, analysis, and *executes what the user decides*, but does **not** make personalized recommendations ("buy TSLA now"). Keeps us in the light-touch "app" lane. Requires product guardrails: no "recommended trades," no personalized buy/sell prompts, careful language on strategy suggestions. **[COUNSEL]** review copilot outputs against the line between "tools/education" and "recommendation."
- **(B) Advisory** — the copilot recommends. Triggers Reg BI and/or adviser registration, best-interest/fiduciary obligations, and disclosure regime. Much heavier; likely RIA posture.

**Recommendation: (A) for launch.** Design the copilot as self-directed from now — this constraint must land in the copilot roadmap **before** it ships, not retrofitted. **[COUNSEL]** to bless the specific interaction patterns. See `[[copilot-agent-framework-roadmap]]`.

---

## 3. Obligations that fall on LlamaTrade *even on the "app" path*

Alpaca carrying the BD burden ≠ LlamaTrade being unregulated. Confirm scope + ownership of each with **[COUNSEL]**:

| Area | What we must do | Notes |
|---|---|---|
| **AML / BSA** | Collect CIP data (legal name, DOB, SSN/tax ID, address, employment, control-person / affiliated-BD / PEP disclosures); support OFAC/watchlist screening; SAR cooperation | Alpaca screens against its blacklist and runs KYC; we present clean data + agreements. **[COUNSEL]** written AML/CIP policy owner |
| **Advertising & performance** | Gate/disclaim **backtests & hypothetical performance** shown to customers (`BacktestPage`, strategy results) | FINRA Rule 2210 / SEC Marketing Rule — hypothetical/backtested returns are heavily regulated; no cherry-picking, mandatory disclaimers |
| **Privacy & data security** | Protect stored SSNs + financial PII | **Reg S-P / GLBA**, CCPA/CPRA, GDPR (if international); realistically **SOC 2** |
| **Disclosures & agreements** | Present Alpaca customer/account agreements, margin/options/crypto disclosures; **Form CRS** if we land in BD/RIA | Sourced from Alpaca; we surface + capture consent |
| **Recordkeeping** | Keep our own books | SEC 17a-3/17a-4 apply to Alpaca as BD; we keep our records |
| **Money transmission** | Avoid routing customer funds through our own accounts | Generally N/A for equities (funds → Alpaca). **Crypto (Alpaca Crypto = MSB) + any funds we touch** can raise state MTL/MSB **[COUNSEL]** |
| **SIPC representation** | May reference Alpaca's SIPC coverage (up to $500k); must not misrepresent | Marketing review |
| **State blue-sky** | Depends on posture | **[COUNSEL]** |
| **International** | FFI/QI/IRS registration, local licensing, GDPR | Large step-up; **[COUNSEL]** — recommend US-only at launch |

---

## 4. Alpaca-side onboarding gates (contractual, not regulatory-body)

To get Broker API **production** access, Alpaca requires (per their onboarding guide):
1. Sandbox build against `broker-api.sandbox.alpaca.markets`.
2. **Commercial-terms** discussion with Alpaca sales (pricing is negotiated; no account minimums, commission-free for self-directed US cash accounts).
3. **CIP/KYC program review** — Alpaca conducts **due diligence on our firm and compliance program**.
4. **"Full Live Approval"** criteria met → production.

Action: **initiate the Alpaca sales/partnership conversation early** — their due diligence runs in parallel with our compliance build and is part of the long pole.

---

## 5. Explicit questions for counsel

1. Does the **"Trading/Investing app"** posture (Alpaca as BD of record, LlamaTrade unregistered) fit our model, or does any feature force RIA/BD?
2. **Reg BI / adviser line:** review copilot behaviors — where exactly does "tools/education" become a "recommendation," and what guardrails keep us self-directed? *(Blocks copilot roadmap.)*
3. Who is the **named AML/compliance officer**, and what written CIP/AML policy do we need before go-live?
4. **Advertising:** what disclaimers/gates are required for backtested & hypothetical strategy performance shown to retail?
5. **Money transmission / MSB:** confirm equities path stays out of MTL; assess crypto exposure if/when we enable Alpaca Crypto.
6. **Privacy:** Reg S-P/GLBA obligations for storing SSNs + PII; CCPA/CPRA; is SOC 2 required for the Alpaca partnership?
7. **US-only vs international** at launch, and the incremental burden of international (FFI/QI, GDPR).
8. **Entity/insurance:** any entity structure, E&O, or fidelity-bond requirements for the app posture?

---

## 6. What engineering can do *before* counsel clears

- Build the **provider seam** (WS-A) — no legal gate.
- Design the copilot to be **self-directed** now (guardrails, language) — de-risks Decision 2 regardless of outcome.
- Build **embedded flows in sandbox only** (Customer entity, account-open, funding) — sandbox has no real customer money, so this can proceed while legal runs, as long as **nothing goes to production / real customers until §4 + counsel sign-off.**
- Stand up **KMS/envelope encryption** for the one platform Broker credential (today's Fernet + global key + static salt, `libs/common/.../utils.py:46-56`, is inadequate for real customer money).

**Hard gate:** no real customer onboarding, funding, or live embedded trading until counsel sign-off **and** Alpaca Full Live Approval.
