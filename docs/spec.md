# IoT Weather Project — UI/UX Design Specification

**Dashboard web app · Desktop-first, responsive · Black & gold, dark default with a light theme · v1.1, updated 7 Nov 2026**

> **Scope change, 7 Nov 2026.** Only **Overview, Accuracy and Data Health** are built, each with fewer panels than shown here; the Rain & Satellite, ML Lab and About pages are out of scope. The panel list is in [Implementation-plan.md](Implementation-plan.md) §5.6, and the visual system below still applies. The rain lamp shows Open-Meteo's rain probability and must be captioned that way. Data before `live_since` is **retrieved**, and no screen may call it continuous live collection.

This document defines the visual system, navigation, page-by-page wireframes, chart rules and UI states for the dashboard described in [architecture.md](architecture.md). Every panel names the data contract it reads from [api-spec.md](api-spec.md).

---

## 1. Design principles

The dashboard should feel like an **observatory console**: calm, precise, and confident about its numbers. Marks for this section reward "nicer, more interactive", so polish goes into the details rather than into decoration.

1. **Every number has a sample size and a definition.** Each chart subtitle shows `n`, the truth source and the lead time. Each card has an ⓘ popover that says "how this is computed" in plain English, so a marker never has to guess.
2. **Gold means "look here" or "you chose this".** Gold marks the active tab, focus, the selected series and the single most important number on a card. It is never a background wash or decoration, and it covers **≤ 10 %** of any screen.
3. **Status never relies on colour alone.** The rain indicator, freshness and run status always pair colour with an icon and a word.
4. **The core never waits for the sleeping server.** Pages backed by Supabase render immediately. Only the ML Lab extras show a "waking up" state.
5. **Interactive by default.** Hover tooltips, brush-to-zoom, toggleable series, a lead-time slider, a satellite loop scrubber and shareable URLs that keep every filter.
6. **Report-ready.** The light theme and a capture mode produce clean screenshots for the 8-page report.

---

## 2. Design tokens

All colours are CSS variables on `:root[data-theme="dark" | "light"]`, consumed by Tailwind (`theme.extend.colors` → `var(--…)`) and by the ECharts themes (§6.4).

### 2.1 Colour: dark theme (default)

| Token | Hex | Usage |
|---|---|---|
| `--bg` | `#0A0A0B` | Page background (near-black, never pure `#000`) |
| `--surface-1` | `#121214` | Cards, top bar |
| `--surface-2` | `#1A1A1D` | Hovered rows, popovers, night shading in charts |
| `--surface-3` | `#232327` | Inputs, chips, slider track |
| `--border` | `#2A2A2F` | Hairline card borders, table rules |
| `--grid` | `#1F1F23` | Chart gridlines (decorative only) |
| `--text` | `#F3EFE6` | Primary text: warm ivory (≈ 17 : 1 on `--surface-1`) |
| `--text-muted` | `#A39E93` | Labels, axis ticks, helper copy (≈ 7 : 1) |
| `--gold-500` | `#D4AF37` | **Primary accent**: active tab underline, focus ring, primary button, key KPI value (≈ 9 : 1 on `--bg`) |
| `--gold-400` | `#E3C463` | Hover state of gold elements |
| `--gold-300` | `#F0DC9A` | Gold text on dark tinted backgrounds |
| `--gold-700` | `#8A6D1F` | Pressed state, active chip border |
| `--gold-900` | `#2B2209` | Active tab / selected row tint |
| `--on-gold` | `#0A0A0B` | Text on gold fills |

### 2.2 Colour: light theme

| Token | Hex | Usage |
|---|---|---|
| `--bg` | `#F7F4EC` | Warm paper background |
| `--surface-1` | `#FFFFFF` | Cards |
| `--surface-2` | `#FBF9F4` | Hover, popovers, night shading |
| `--surface-3` | `#F0ECE2` | Inputs, chips |
| `--border` | `#E2DCCD` | Hairlines |
| `--grid` | `#EEE9DD` | Gridlines |
| `--text` | `#17150F` | Primary text |
| `--text-muted` | `#5F5A4F` | Secondary text (≈ 6.9 : 1 on white) |
| `--gold-500` | `#C9A227` | Gold **fills** only (buttons, underline), with `--on-gold: #17150F` (≈ 7.5 : 1) |
| `--gold-text` | `#8A6510` | Gold **text and links** on white (≈ 5.3 : 1; plain `#D4AF37` fails contrast on white) |
| `--gold-900` | `#F6EED3` | Active tint |

### 2.3 Colour: semantic status (both themes)

Orange is used for **Watch** so it is never confused with brand gold.

| Status | Dark | Light | Icon (lucide) | Label |
|---|---|---|---|---|
| Rain · `CLEAR` | `#3FB68B` | `#1F8A63` | `Sun` / `CloudSun` | "Clear" |
| Rain · `WATCH` | `#F08A24` | `#B85F0B` | `CloudDrizzle` | "Watch: rain possible" |
| Rain · `RAIN_LIKELY` | `#E5484D` | `#C62A2F` | `CloudRainWind` | "Rain likely within 1 h" |
| Rain · `UNKNOWN` | `#6E6A62` | `#8E887B` | `CloudOff` | "No recent nowcast" |
| Run · success / partial / failed / missing | `#3FB68B` / `#F08A24` / `#E5484D` / `#3A3A40` | `#1F8A63` / `#B85F0B` / `#C62A2F` / `#D6D0C2` | `Check` / `AlertTriangle` / `X` / `Minus` | as named |

### 2.4 Colour: data series

| Series | Dark | Light | Line style |
|---|---|---|---|
| **Actual** (any truth source) | `#F3EFE6` ivory | `#17150F` ink | solid 2 px, on top |
| `best_match` | `#D4AF37` gold | `#A8841A` | solid 1.5 px |
| `best_match+ml` | `#F0DC9A` champagne | `#6E5410` | **dashed** 1.5 px |
| `ecmwf_ifs025` | `#5AA9E6` sky | `#2F7FC1` | solid 1.5 px |
| `gfs_seamless` | `#E8775A` coral | `#C4553A` | solid 1.5 px |
| `icon_seamless` | `#4FC1A6` teal | `#1F9480` | solid 1.5 px |
| `ecmwf_aifs025_single` (optional) | `#A88BEB` violet | `#7B5CC9` | solid 1.5 px |
| `jma_seamless` (optional) | `#E58FB4` rose | `#C0587F` | solid 1.5 px |
| ML nowcast probability | `#D4AF37` | `#A8841A` | solid 2 px + area at 12 % |
| Open-Meteo probability (comparison) | `#A39E93` | `#5F5A4F` | dotted 1.5 px |

**Scales**

| Scale | Stops (dark) | Use |
|---|---|---|
| Rain (sequential) | `#121214 → #12324A → #1F6E9C → #5AA9E6 → #CDE9FA` | Rain heatmap, IMERG legend |
| Magnitude (sequential, gold) | `#1A1A1D → #4A3B12 → #8A6D1F → #D4AF37 → #F6E7B0` | MAE heatmaps, coverage grid |
| Bias (diverging) | `#5AA9E6` (forecast too low) ← `#2A2A2F` (0) → `#E8775A` (forecast too high) | Error heatmap, bias bars |

The light theme uses the same hues, with the neutral stop set to `#EEE9DD`.

### 2.5 Typography

| Role | Font | Size / weight / line height | Notes |
|---|---|---|---|
| Wordmark, page titles | **Fraunces** (variable serif, optical size on) | 28 / 600 / 1.2 | A touch of "almanac" elegance that pairs well with gold. Fallback: IBM Plex Sans 600 |
| UI text, labels, tables | **IBM Plex Sans** | 14 / 400 / 1.45 (body) · 13 / 500 (labels) · 12 / 500 uppercase +0.06 em tracking (overlines) | A technical, instrument-like grotesque |
| Big readings (Now card, KPIs) | IBM Plex Sans | 56 / 300 (Now temperature) · 32 / 400 (KPI values) | Always `font-variant-numeric: tabular-nums` |
| Timestamps, IDs, code | **IBM Plex Mono** | 12 / 400 | e.g. `2026-11-03 14:00 MYT`, run IDs |
| Chart text | IBM Plex Sans | 11–12 | Axis labels use `--text-muted` |

The scale is 12 · 13 · 14 · 16 · 20 · 24 · 28 · 32 · 56 px. Fonts are self-hosted with `@fontsource` (no third-party font calls, which also counts toward the RM0 story).

### 2.6 Spacing, shape and elevation

- Base unit **4 px**. Card padding 20 px, grid gutter 24 px, section gap 32 px.
- Radius: cards 12 px · inputs and buttons 8 px · chips and pills 999 px · the map 12 px.
- **Elevation by surface step, not shadow** (`--surface-1` → `-2` → `-3`) on dark. Light uses one soft shadow, `0 1px 2px rgb(23 21 15 / 0.06)`.
- 1 px `--border` hairlines between regions. Gold borders only on the active or selected element.
- Motion: 150 ms for UI state changes and 300 ms for chart transitions (`cubic-bezier(.2,.7,.2,1)`). All motion is disabled under `prefers-reduced-motion`.

---

## 3. Information architecture and navigation

### 3.1 Routes (multi-page tabs)

| Tab | Route | Purpose | Report section it feeds |
|---|---|---|---|
| Overview | `/` | "What's happening now, and how good is the forecast?" | Visualization (hero screenshot) |
| Accuracy | `/accuracy` | Forecast vs actual, error by lead, leaderboard | Visualization + Conclusion, bonus (b) |
| Rain & Satellite | `/rain` | IR loop, nowcast, rain scorecard | Bonus (b)(c), system design (perception) |
| ML Lab | `/ml` | Model cards, live evaluation, explanations | Bonus (c) |
| Data Health | `/health` | Data coverage (retrieved and live), uptime | Technical implementation, problem statement |
| About | `/about` | Architecture, definitions, sources, limitations | System design, cost, citations |

### 3.2 Global layout

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◎ IOT WEATHER PROJECT   Overview  Accuracy  Data Health                                    │
│                                              [▣ 4 Nov – 7 Nov · report window]  ● 3 min  ◐ WATCH  ☾ │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│   PAGE TITLE (Fraunces)                                  page filter bar (right-aligned)     │
│   one-line description in --text-muted                                                       │
│                                                                                              │
│   ┌──────── 12-column grid, max-width 1440 px, 24 px gutters ─────────────────────────────┐  │
│   │  ChartCard  ChartCard  …                                                               │  │
│   └────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Weather data by Open-Meteo.com (CC BY 4.0) · METAR NOAA AWC                                    │
│ Times in MYT (UTC+8)   ·   GitHub · v1.0                                                       │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Top bar (56 px, sticky, `--surface-1`, bottom hairline)

| Element | Behaviour |
|---|---|
| Wordmark | A gold "◎" glyph (concentric arcs, like a radar sweep) + "IOT WEATHER PROJECT" in Plex Sans 13/600, +0.12 em tracking. Links to `/` |
| Tabs | Text tabs. The active one gets `--text` + a 2 px gold underline; inactive ones are `--text-muted`. Keyboard: ←/→ moves between tabs, Enter opens |
| Date range | A pill button that opens a popover with presets ("Collection window" default, "Last 24 h", "Last 3 days", "Last 7 days", custom). Saved to the URL as `?from&to` |
| Freshness | A dot + "3 min" (age of the newest `openmeteo_current` row). Green ≤ 20 min, orange ≤ 60 min, red > 60 min. Tooltip lists the newest row per source (`v_now`) |
| Rain badge | A mini lamp + level word from `v_rain_status`, which links to `/rain` |
| Theme toggle | ☾ / ☀. It follows the system theme on first visit, then remembers the choice in `localStorage` |

---

## 4. Page wireframes

Column spans refer to the 12-column grid at ≥ 1280 px. §7 covers the smaller breakpoints.

### 4.1 Overview `/`

```
┌ NOW · Seri Iskandar ─────────── span 5 ┐┌ RAIN INDICATOR ───── span 4 ┐┌ MAP ────────── span 3 ┐
│  27.4°  ☁ Light drizzle                 ││        ╭───╮                ││  Leaflet dark base    │
│  feels muggy · dew point 24.2°          ││        │ ● │  WATCH          ││  ◎ Seri Iskandar      │
│  ──────────────────────────────────     ││        ╰───╯                ││  ▲ WMKI (26 km)       │
│  RH 84 %   Wind 7 km/h NE   1010 hPa    ││  Next 1 h  58 %  ▁▂▄▆█      ││  ▢ model grid cell    │
│  Rain (15 min) 0.1 mm   Cloud 84 %      ││  Next 3 h  81 %             ││  latest IR frame 75 % │
│  ──────────────────────────────────     ││  Open-Meteo says 45 %       ││                       │
│  Station check · METAR WMKI  26° −RA    ││  "Cold cloud tops 18 km W,  ││  [Open satellite →]   │
│  Updated 14:15 MYT · source ⓘ           ││   cooling 6 K in 30 min"    ││                       │
└─────────────────────────────────────────┘└─────────────────────────────┘└───────────────────────┘
┌ KPI ROW ───────────────────────────────────────────────────────────────────────────── span 12 ┐
│ COLLECTED          UPTIME         TEMP MAE · 24 h lead   RAIN CSI · 0–6 h   BEST MODEL (temp)   │
│ 7 d 3 h ✓ ≥ 3 d    98.6 %         1.12 °C  n=162         0.41  n=168        ECMWF IFS           │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ NEXT 24 HOURS ──────────────────────────────────────────────────────────────────────── span 12 ┐
│  hourly icons ☀ ☀ ⛅ ☁ 🌧 🌧 ⛈ …                                                               │
│  temperature line (gold) + ML-corrected (dashed champagne) · rain-probability bars (sky, 40 %)  │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ LAST 72 HOURS · forecast made 24 h before vs actual ───────────────────────────────── span 12 ┐
│  ivory actual line, gold forecast line, observed rain bars below · night shading · [Open Accuracy →] │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Panel | Data | Interactions |
|---|---|---|
| Now | `v_now` (`openmeteo_current` + `metar_wmki`) | ⓘ explains that "actual" is model analysis, cross-checked by the station |
| Rain indicator | `v_rain_status` | Lamp pulses once (scale 1 → 1.06) when the level changes; `aria-live="polite"` announces it; the explanation is the top `explain` item turned into a sentence |
| Map | `locations`, `sources`, GIBS latest frame | Static mini map; click → `/rain` |
| KPI row | `rpc_kpis` | Each tile links to the chart it summarises |
| Next 24 h | `rpc_next_24h` | Hover shows the hour's values; the ML line shows only if the bias model is active |
| Last 72 h | `rpc_forecast_vs_actual(best_match, temperature_c, 24, …)` | Brush to zoom; the link keeps the range |

### 4.2 Accuracy `/accuracy`

```
Filter bar:  Variable [Temp ▪ RH ▪ Wind ▪ Pressure ▪ Rain]   Models [● best ● ecmwf ● gfs ● icon ○ +ml]
             Truth [Open-Meteo current ▾]   Lead ≥ [━━━━●━━━━━] 24 h   (stops 1·3·6·12·24·48·72·120·168)

┌ FORECAST VS ACTUAL ─────────────────────────────────────────────────────────────────── span 12 ┐
│ subtitle: "Forecasts issued at least 24 h before each hour · truth: Open-Meteo current · n = 162" │
│ ivory actual + one line per selected model · error band toggle · dataZoom slider under the x-axis │
│ tooltip: 14:00 Tue 3 Nov · actual 29.0 · best 33.7 (+4.7, issued Mon 14:00, lead 24 h) …         │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ ERROR VS LEAD TIME ─────────────── span 6 ┐┌ SKILL VS PERSISTENCE ───────────────── span 6 ┐
│ x: lead bucket · y: MAE (toggle Bias/RMSE)  ││ y: skill (1 − MAE/MAE_persist.) · 0-line in    │
│ one line per model, markers sized by n      ││ gold · bars per model per bucket               │
└─────────────────────────────────────────────┘└───────────────────────────────────────────────┘
┌ MODEL LEADERBOARD ·  leads ≤ 72 h ─────────── span 7 ┐┌ WHEN IS IT WRONG? hour × date ─ span 5 ┐
│ # Model         Temp MAE  RH MAE  Wind MAE  CSI Brier │ │ diverging heatmap of mean error        │
│ 1 ECMWF IFS     0.98★     6.1     3.2      0.38 —     │ │ rows: dates · cols: 00–23 MYT          │
│ 2 best_match+ml 1.01      5.4★    3.0★     —    —     │ │ afternoon storms show as a hot band    │
│ … best value per column in gold, sortable headers    │ │ lead bucket selector inside the card    │
└──────────────────────────────────────────────────────┘└────────────────────────────────────────┘
┌ NEXT-DAY FORECAST (brief requirement) ──────────────────────────────────────────── span 8 ┐┌ WHAT IS "ACTUAL"? span 4 ┐
│ Date | Max fc / obs | Min fc / obs | Rain fc / obs (mm) | Rain prob | ✓/✗ rain day          ││ source agreement table  │
│ lead-days selector 1 ▪ 2 ▪ 3 · rows with incomplete days greyed with "partial" tag        ││ (FastAPI, optional)     │
└───────────────────────────────────────────────────────────────────────────────────────────┘└─────────────────────────┘
```

| Panel | Data | Notes |
|---|---|---|
| Forecast vs actual | `rpc_forecast_vs_actual` per selected model | Rain variable switches to bars (forecast hatched, actual solid). Up to 5 models at once |
| Error vs lead | `rpc_metrics_by_lead` | Buckets with `n < 20` are drawn at 40 % opacity and tagged "low n" |
| Skill | `rpc_skill_vs_persistence` | A gold zero-line marks "as good as yesterday's weather" |
| Leaderboard | `rpc_leaderboard` | ★ + gold text for the best per column; the `+ml` row carries an "ML" chip |
| Heatmap | `rpc_error_heatmap` | Diverging bias scale with a symmetric domain (±max \|error\|) |
| Next-day | `rpc_daily_pairs` | The brief's "next-day temperature and rainfall prediction" |
| Agreement | FastAPI `/analytics/agreement` | Hidden (not an error) if the API is asleep: "Load comparison" button |

### 4.3 Rain & Satellite `/rain`

```
┌ HIMAWARI-9 INFRARED · last 3 h ───────────────────────── span 8 ┐┌ NOWCAST NOW ────────── span 4 ┐
│  Leaflet map, Perak view (z 7), GIBS B13 IR at 75 %             ││  ( ● ) WATCH                  │
│  ◎ Seri Iskandar + dashed rings at 10 / 25 / 50 km              ││  1 h 58 % · 3 h 81 %          │
│  ▲ WMKI                                                         ││  vs Open-Meteo 45 %           │
│  ┌ controls ───────────────────────────────────────────────┐    ││  WHY ─────────────────────    │
│  │ ▶ ❚❚  ◀ ▶  ━━━━━━━━━━━●━━  13:40 MYT (−20 min)  1× 2× 4×  │    ││  + 42 % cold cloud ≤ 25 km  ▇▇▇│
│  │ Layer [IR ▪ IR + IMERG rain]  Opacity ━━●━━              │    ││  + cooled 6.1 K / 30 min    ▇▇ │
│  └──────────────────────────────────────────────────────────┘    ││  − dry air aloft            ▇  │
│  legend: brightness-temp colour bar · 235 K and 221 K ticks      ││  model v1.0 · slot 14:00      │
└──────────────────────────────────────────────────────────────────┘└───────────────────────────────┘
┌ NOWCAST TIMELINE · last 72 h ──────────────────────────────────────────────────────────── span 12 ┐
│ background ribbon = level (clear / watch / likely) · gold line = ML p(1 h) · dotted = Open-Meteo % │
│ dashed horizontal threshold lines · sky bars below = observed rain (Open-Meteo 15-min, IMERG)      │
│ click a time → the IR loop above jumps to that frame                                              │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ RAIN SCORECARD · model [best ▾] lead [0–6 h ▾] ─ span 6 ┐┌ RELIABILITY ───────────────── span 6 ┐
│        Observed: rain   no rain                        ││ x: forecast prob · y: observed freq │
│ Fc rain   HITS 31      FALSE ALARM 22                  ││ diagonal = perfect (gold dashed)    │
│ Fc dry    MISS 12      CORRECT NEG 103                 ││ points sized by n · inset histogram │
│ POD 0.72   FAR 0.42   CSI 0.48   HSS 0.51   Bias 1.23  ││ Brier 0.142 · BSS 0.18 (n = 168)    │
└────────────────────────────────────────────────────────┘└─────────────────────────────────────┘
┌ WHEN DOES IT RAIN? hour × date (observed mm) ──────────────── span 8 ┐┌ BRIER BY LEAD ────── span 4 ┐
│ rain scale heatmap; ⨯ marks hours the 0–6 h forecast missed          ││ grouped bars per model      │
└──────────────────────────────────────────────────────────────────────┘└─────────────────────────────┘
┌ STORM REPLAY (P1) · [3 Nov 15:15 · 18.4 mm ▾]  ▶ Replay ─────────────────────────────────── span 12 ┐
│ loads the event window into the IR loop + timeline and autoplays them in sync                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Panel | Data | Notes |
|---|---|---|
| IR loop | GIBS WMTS (architecture §10.4) | Keys: Space play/pause, ←/→ step a frame. Preloads all frames (progress shown in the scrubber track). No autoplay under reduced motion |
| Nowcast now | `v_rain_status`; FastAPI `/nowcast/latest` for the "why" (falls back to `explain` in the view) | Contribution bars: gold = pushes toward rain, muted = pushes away |
| Timeline | `rpc_nowcast_timeline` (3-day pages) | Synced cursor with the IR loop |
| Scorecard | `rpc_rain_contingency` | 2 × 2 matrix cells tinted by share; tiles explain each score in the ⓘ |
| Reliability | `rpc_reliability` + `rpc_brier` | Bins with n < 10 are drawn hollow |
| Rain heatmap | `rpc_rain_heatmap` | |
| Storm replay | FastAPI `/events` | Optional; hidden if the API is asleep and no cached list exists |

### 4.4 ML Lab `/ml`

```
┌ MODEL CARDS ─────────────────────────────────────────────────────────────────────────── span 12 ┐
│ [Rain nowcast · LightGBM v1.0 · active]  [Bias · temperature v1.0]  [Bias · humidity]  [Bias · wind] │
│ each: trained on …, tested on …, features (n), headline metric, "View card" ↗                      │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ NOWCAST · ROC (live window) ──────── span 6 ┐┌ NOWCAST VS BASELINES ─────────────────── span 6 ┐
│ gold curve = model; muted = Open-Meteo,     ││ grouped bars: AUC ↑, Brier ↓, CSI ↑, warning min │
│ persistence, 235 K rule · AUC in legend     ││ offline test vs live, with n · horizon [1 h ▪ 3 h]│
└─────────────────────────────────────────────┘└───────────────────────────────────────────────────┘
┌ WHAT THE MODEL LOOKS AT (importance) ─ span 6 ┐┌ LIVE EXPLANATION (latest slot) ───── span 6 ┐
│ horizontal bars by gain, grouped by family   ││ waterfall from base rate to p = 58 %        │
│ (satellite / weather / calendar)              ││ top 8 contributions with plain labels       │
└───────────────────────────────────────────────┘└─────────────────────────────────────────────┘
┌ BIAS CORRECTION · raw vs corrected MAE by lead ── span 7 ┐┌ RAW VS CORRECTED VS ACTUAL ─── span 5 ┐
│ paired bars per lead bucket, improvement % label in gold,  ││ time series, variable picker          │
│ 95 % CI whiskers (FastAPI) · variable [Temp ▪ RH ▪ Wind]   ││                                       │
└────────────────────────────────────────────────────────────┘└───────────────────────────────────────┘
┌ METHOD ──────────────────────────────────────────────────────────────────────────────────── span 12 ┐
│ training data · time-blocked split · leakage guard · labels and their limits · why LightGBM         │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Panel | Primary data | Fallback when FastAPI sleeps |
|---|---|---|
| Model cards | FastAPI `/models` | `ml_models` table via Supabase (offline metrics only) |
| ROC, baselines | FastAPI `/nowcast/evaluation` | Offline metrics from `ml_models.metrics`, labelled "offline test" |
| Importance | `ml_models.importance` (Supabase) | Always available |
| Live explanation | FastAPI `/nowcast/latest` | `v_rain_status.explain` (top 5) |
| Bias MAE | `rpc_bias_eval` (Supabase) + CI from FastAPI `/bias/evaluation` | Bars without whiskers |
| Raw vs corrected | `rpc_forecast_vs_actual` for `best_match` and `best_match+ml` | Always available |

### 4.5 Data Health `/health`

```
┌ BANNER (gold hairline border) ───────────────────────────────────────────────────────── span 12 ┐
│ ✓  Report window: 3 days of retrieved data · Wed 4 Nov 00:00 – Sat 7 Nov 00:00 MYT                │
│    Collecting live since Sat 7 Nov 13:15 MYT · 288 of 288 expected samples · longest gap 15 min   │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ DAILY UPTIME BY JOB ───────────────────── span 8 ┐┌ AT A GLANCE ──────────────────── span 4 ┐
│ stacked bars per day: success / partial /        ││ Runs 1,190 · Success 97.9 %             │
│ failed / missing, one group per job              ││ Median start delay 4 min 10 s           │
└──────────────────────────────────────────────────┘└─────────────────────────────────────────┘
┌ RUN TIMELINE ──────────────────────────────────────────────────────────────────────────── span 12 ┐
│ three swim-lanes (observe / forecast / backfill), one tick per run coloured by status, brushable  │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ COVERAGE GRID · date × stream ─────────── span 7 ┐┌ HOW LATE DOES GITHUB START? ───── span 5 ┐
│ cells = coverage %, gold magnitude scale,         ││ histogram of start delay (min)          │
│ "B" glyph where backfill filled gaps              ││ explains why we poll every 10 min       │
└───────────────────────────────────────────────────┘└─────────────────────────────────────────┘
┌ LATEST RUNS (table) ─────────────────────────────────────────────────────────────────────── span 12 ┐
│ time · job · status pill · duration · rows written · failed steps · GitHub run link ↗               │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Data: `v_collection_window`, `rpc_uptime_daily`, `rpc_runs_timeline`, `v_coverage_daily`, `ingestion_runs`.

### 4.6 About `/about`

A single reading column (max 760 px):

1. the architecture diagram (an SVG exported from the Mermaid in architecture.md, re-coloured to the theme)
2. the 5-layer IoT table
3. definitions: actual, lead time, rain hour, each metric with its formula
4. data sources and attribution
5. a cost table (RM0)
6. limitations (model-based truth, a station 26 km away, a short window, IMERG latency)
7. references in IEEE style

The same text can be copied into the report.

---

## 5. Core components

| Component | Anatomy | Key props / behaviour |
|---|---|---|
| `AppShell` | Top bar, `<main>`, footer | Sets `data-theme`; preloads `v_now` and `v_rain_status` |
| `ChartCard` | Overline (12 px uppercase muted), title (16/600), subtitle (`n`, truth, lead in muted 12), action icons: ⓘ method · ⤓ CSV · ⛶ fullscreen · ▦ "view as table" | `loading`, `empty`, `error`, `stale` states (§8). The CSV action uses the loaded rows client-side, so it doesn't need FastAPI |
| `KpiTile` | Label, value (32/400, gold when it's the page's key value), unit, context line (`n = …`), optional sparkline | Clickable → scrolls or navigates to the source chart |
| `RainLamp` | 72 px circular lamp with a 2 px ring in the status colour and an inner glow, then the level word and the probabilities | `size="sm"` (top-bar badge, 12 px) or `"lg"`. Colour + icon + text |
| `LeadSlider` | Track with snap stops 1, 3, 6, 12, 24, 48, 72, 120 and 168 h; the label reads "Forecasts issued ≥ 24 h before" | Arrow keys move between stops; writes `?lead=` |
| `ModelChips` | A colour dot + model name, toggle on/off; `+ml` gets an "ML" tag | Max 5 active; at least 1 |
| `TruthSelect` | Dropdown with a description per source (kind, distance, cadence) | Writes `?truth=` |
| `DateRangePicker` | Presets + two calendars | Clamps to 31 days and to the collection window |
| `IRLoopMap` | Leaflet map, frame layers, rings, markers, controls, legend | `frames`, `index`, `playing`, `onFrame`; preloading progress |
| `ContingencyMatrix` | 2 × 2 grid with counts and percentages, tinted by share | Cells have a hover definition |
| `MetricTable` | Sortable table; the best value per column in `--gold-500` + ★ | Sticky header; numbers right-aligned and tabular |
| `StatusPill` | Icon + word in the status colour, on a 12 % tint | |
| `FreshnessBadge` | Dot + relative age | Thresholds from §3.3 |
| `WakeBanner` | Inline card: "Waking the analysis server… usually under a minute" with an indeterminate gold bar | Appears only on API-backed panels; after 75 s: "Still asleep. Showing saved results" + retry |
| `EmptyState` | A muted line icon, one sentence, an optional action | Copy in §8 |

---

## 6. Chart rules (ECharts)

### 6.1 General

- **Time axis** in MYT, labelled like `Tue 3 Nov` (day ticks) and `14:00` (hour ticks). Faint vertical lines mark midnight. **Night shading** (19:15–07:15 MYT) uses `markArea` filled with `--surface-2`, which makes the diurnal cycle and afternoon storms visible at a glance.
- **Encoding:** actual = ivory solid on top; forecasts = model colour; ML = dashed; Open-Meteo probability = dotted; rain = bars.
- **Legend:** never the ECharts default. Use `ModelChips` above the chart, so toggling a model also updates the URL.
- **Tooltip:** `axis` trigger. It shows the header time (Plex Mono), each series value with its unit, and `error = forecast − actual` with a sign and the bias colour. Forecast rows add `issued Mon 14:00 · lead 24 h`.
- **Zoom:** `dataZoom` inside (wheel or pinch) + a slider on time series. Double-click resets.
- **Low sample size:** when `n < 20`, draw at 40 % opacity with a "low n" marker; never hide the data.
- **Number formats:** temperature 1 dp · RH 0 dp · wind 1 dp · mm 1 dp · scores (POD/CSI/…) 2 dp · Brier 3 dp · probabilities as whole %.
- **Empty and partial:** gaps in the data stay as gaps (`connectNulls: false`). Hours not yet verified are not drawn for the actual series.
- **"View as table"** on every chart renders the same rows in a `MetricTable`, for accessibility and quick report numbers.

### 6.2 Specific charts

| Chart | Type | Encoding details |
|---|---|---|
| Forecast vs actual | line (bars for rain) | y-axis unit in the title; optional error band = shaded area between forecast and actual in the bias colour at 15 % |
| Error vs lead | line + symbols | x = ordered bucket labels ("0–6 h"…); symbol size ∝ √n; Bias/MAE/RMSE toggle |
| Skill vs persistence | bars | y clamped to [−1, 1]; gold 0-line labelled "persistence" |
| Leaderboard | table | Not a chart; see `MetricTable` |
| Error heatmap | heatmap | x = hour 00–23, y = date; diverging scale with a symmetric domain; cells with n = 0 left blank |
| Reliability | scatter + line | 1 : 1 gold dashed diagonal; inset bar histogram of forecast counts; axes 0–100 % |
| ROC | line | Model in gold 2 px; baselines in muted, dotted/dashed; diagonal for chance; AUC in the chip labels |
| Importance | horizontal bars | Coloured by feature family: satellite = sky, weather = teal, calendar = muted |
| Waterfall | bars | Base value → contributions (gold = toward rain, muted = away) → final probability |
| Uptime | stacked bars | Status colours; the missing segment is `--surface-3` with hatching |
| Run timeline | custom series (ticks) | One lane per job; tick colour = status; brushable |
| Coverage grid | heatmap | Gold magnitude scale 0–100 %; "B" label where backfilled |

### 6.3 Satellite legend

The B13 colour bar (GIBS palette) runs horizontally under the map, with tick marks and labels at **235 K "rain cloud"** and **221 K "deep storm"**, and °C equivalents (−38 °C and −52 °C) in muted text.

### 6.4 ECharts theme (dark excerpt)

```ts
export const iwwDark = {
  color: ['#D4AF37', '#5AA9E6', '#E8775A', '#4FC1A6', '#A88BEB', '#E58FB4'],
  backgroundColor: 'transparent',
  textStyle: { fontFamily: 'IBM Plex Sans', color: '#A39E93', fontSize: 12 },
  title: { textStyle: { color: '#F3EFE6', fontWeight: 600, fontSize: 16 } },
  grid: { left: 48, right: 16, top: 24, bottom: 40, containLabel: true },
  categoryAxis: { axisLine: { lineStyle: { color: '#2A2A2F' } }, splitLine: { show: false } },
  valueAxis: { axisLine: { show: false }, splitLine: { lineStyle: { color: '#1F1F23' } } },
  timeAxis: { axisLine: { lineStyle: { color: '#2A2A2F' } }, splitLine: { show: false } },
  tooltip: { backgroundColor: '#1A1A1D', borderColor: '#2A2A2F', textStyle: { color: '#F3EFE6' } },
  dataZoom: { borderColor: '#2A2A2F', fillerColor: 'rgba(212,175,55,0.12)', handleStyle: { color: '#D4AF37' } },
};
```

### 6.5 CSS variables (excerpt)

```css
:root[data-theme='dark'] {
  --bg:#0A0A0B; --surface-1:#121214; --surface-2:#1A1A1D; --surface-3:#232327;
  --border:#2A2A2F; --grid:#1F1F23; --text:#F3EFE6; --text-muted:#A39E93;
  --gold-500:#D4AF37; --gold-400:#E3C463; --gold-300:#F0DC9A; --gold-700:#8A6D1F; --gold-900:#2B2209;
  --gold-text:#D4AF37; --on-gold:#0A0A0B;
  --ok:#3FB68B; --watch:#F08A24; --alert:#E5484D; --unknown:#6E6A62;
}
:root[data-theme='light'] {
  --bg:#F7F4EC; --surface-1:#FFFFFF; --surface-2:#FBF9F4; --surface-3:#F0ECE2;
  --border:#E2DCCD; --grid:#EEE9DD; --text:#17150F; --text-muted:#5F5A4F;
  --gold-500:#C9A227; --gold-400:#D8B443; --gold-300:#8A6510; --gold-700:#8A6510; --gold-900:#F6EED3;
  --gold-text:#8A6510; --on-gold:#17150F;
  --ok:#1F8A63; --watch:#B85F0B; --alert:#C62A2F; --unknown:#8E887B;
}
```

---

## 7. Responsive behaviour

| Breakpoint | Layout |
|---|---|
| ≥ 1280 px | The 12-column layouts above |
| 768–1279 px | Two columns: span-12 cards stay full width, everything else pairs as 6 + 6. The top bar collapses the date range into an icon button |
| < 768 px | One column. Tabs become a horizontally scrolling strip. The Overview order is Rain indicator → Now → KPIs → Next 24 h. The IR map is 60 vh with controls below it. Tables scroll horizontally with a sticky first column |

Overview and Rain must be fully usable on a phone, since a marker might open the URL there. Accuracy and Health are acceptable as scroll-heavy pages.

---

## 8. States and microcopy

| State | Treatment | Example copy |
|---|---|---|
| Loading | Card-shaped skeletons with a faint gold shimmer (disabled under reduced motion) | — |
| Empty (just started) | `EmptyState` | "Not enough verified hours yet. Accuracy appears about an hour after collection starts, and gets meaningful after a day." |
| Empty (filter) | `EmptyState` + reset | "No pairs for ICON at 120–168 h in this range. Try a longer range or a shorter lead." |
| Stale data | Orange `FreshnessBadge` + card subtitle warning | "Latest observation is 47 min old. GitHub may be running late; the backfill will fill the gap." |
| Nowcast unknown | Grey lamp, `UNKNOWN` | "No nowcast in the last 30 min." |
| API waking | `WakeBanner` | "Waking the analysis server… usually under a minute." |
| API failed | Inline note + retry; the fallback data stays visible | "Live evaluation unavailable. Showing the offline test results saved with the model." |
| Error (Supabase) | Card-level error with retry and the error code in Plex Mono | "Couldn't load metrics (57014: query took too long). Try a shorter range." |

**Glossary popovers** (used by ⓘ, written once in `copy/glossary.ts`):

- **Actual:** Open-Meteo's 15-minute analysis for the Seri Iskandar grid cell. It comes from a model, not a rain gauge, so we cross-check it against Ipoh airport's instruments (26 km away) and NASA satellite rain.
- **Lead time:** how far ahead the forecast was made. "24 h" means the forecast was issued at least 24 hours before that hour.
- **MAE:** the average size of the error, ignoring sign. Lower is better.
- **Bias:** the average signed error. Positive means the forecast runs too high (e.g. too warm).
- **RMSE:** like MAE, but punishes big misses more.
- **POD:** the share of rain hours that were forecast.
- **FAR:** the share of forecast rain hours that stayed dry.
- **CSI:** hits ÷ (hits + misses + false alarms). 1 is perfect.
- **Brier score:** the mean squared error of rain probabilities. 0 is perfect.
- **Reliability:** when the forecast says 70 %, does it rain about 70 % of the time?
- **Skill vs persistence:** how much better than simply assuming "same as yesterday".

---

## 9. Accessibility

- WCAG 2.2 AA contrast for every text token (ratios in §2). Gold text on white uses `--gold-text` only.
- A visible focus ring everywhere: 2 px `--gold-500`, 2 px offset. It is never removed.
- Full keyboard support for tabs, pickers, the lead slider (arrows), the IR loop (Space, ←/→) and table sorting (Enter on a header).
- Every chart has an `aria-label` summary (e.g. "Temperature MAE rises from 0.8 °C at 0–6 h to 2.1 °C at 120–168 h") plus "View as table".
- Rain level changes are announced through `aria-live="polite"`. Animation respects `prefers-reduced-motion`.
- Colour is never the only signal: statuses carry an icon and a word, and the ML series is dashed as well as coloured.

---

## 10. Report and video support

- **Capture mode `?capture=1`:** hides the date picker and freshness, fixes the content width to 1600 px, removes skeleton shimmer and adds a small caption under each card ("Fig. n: …" placeholder). Use it with the **light theme** for the report and the dark theme for the video.
- **Deep links:** every filter is in the URL, so the demo script ([tasks.md](tasks.md)) can jump straight to "Accuracy, temperature, lead 24 h, all models" or "Storm replay 3 Nov".
- **Screenshot list for the report** (4–5 figures): Overview (hero) · Forecast vs actual + error vs lead · Rain scorecard + reliability · Health banner + uptime · ML raw vs corrected.

---

## 11. Implementation notes

- Tailwind v4 maps the CSS variables to utilities (`bg-surface-1`, `text-muted`, `border-border`, `text-gold`); shadcn/ui components are restyled through the same variables.
- Chart wrapper: one `useEChart(option, theme)` hook (init, resize observer, theme switch, dispose). Register only `LineChart`, `BarChart`, `HeatmapChart`, `ScatterChart` and `CustomChart` plus the needed components.
- Icons: `lucide-react`. Map WMO weather codes to icons in `lib/wmo.ts` (0 Sun · 1–3 CloudSun/Cloud · 45/48 CloudFog · 51–57 CloudDrizzle · 61–67, 80–82 CloudRain · 95–99 CloudLightning).
- Dates: `date-fns` + `date-fns-tz`. All formatting goes through `fmtMYT()`, and **no raw `Date#toString()`** is ever shown.
- Keep business logic out of components: metrics come computed from SQL, and the UI only formats them.
