# Iskandar Weather Watch — Phased Build Checklist (solo)

**Written 31 Oct 2026, scope updated 7 Nov 2026 · Builds what [architecture.md](architecture.md), [api-spec.md](api-spec.md) and [spec.md](spec.md) describe**

> **Scope change, 7 Nov 2026.** The deadline is **Sun 8 Nov 2026, 23:59 MYT**. Data is **retrieved retrospectively from Wed 4 Nov**, then collected live, because the project uses no hardware and every source keeps its own history. One temperature model is trained on history. Himawari is dropped. **The live checklist and schedule are now [Implementation-plan.md](Implementation-plan.md) §4 and §6.** The phases below stay as the full design; a task that isn't in that checklist is out of scope.

**Schedule:** see [Implementation-plan.md](Implementation-plan.md) §4. The D-numbers below are the original offsets and no longer map to dates.

**Priority:** P0 = needed for the core rubric · P1 = bonus marks, planned · P2 = only if time is left.
**Rule 1:** get retrieved data into the database and the live jobs running first. Nothing else can be shown until that's done.
**Rule 2:** finish every P0 before starting a P1. If you're behind, use the overrun order in the plan's §4.

---

## Cut-lines (original, replaced by the plan's §1)

| Days from D1 to deadline | What to build | Data window to freeze |
|---|---|---|
| **≤ 7** | P0 only: Phases 0, 1, 3 (views), 4 (Overview, Accuracy, Health) and 8. The rain indicator uses the **v0 235 K rule** (T2.4). No ML training, no FastAPI | 3–4 full days |
| **8–11** | + Phase 2 (satellite), the Rain page, bias correction for **temperature only**, and a **weather-only** nowcast (T5.4 fallback). FastAPI is skipped; the ML Lab reads Supabase only | 5–7 full days |
| **12–15** | The full plan (P0 + P1) | 7 full days |
| **16+** | + P2: CNN nowcast, AIFS/JMA models, storm replay, backup trigger, mobile polish | 7–10 full days |

---

## Phase 0 — Setup (D1 morning, about 2 h)

- [ ] **T0.1** (P0) Create a **public** GitHub repo `iww` with the layout in architecture §14, plus `.gitignore` (`node_modules`, `.venv`, `dist`, `.cache`, `*.DAT*`, `.env`). _Done when:_ the repo is pushed and the README has a one-paragraph description.
- [ ] **T0.2** (P0) Create the Supabase project (region **Singapore**). Copy the **session pooler** URI, the project URL and the anon / publishable key. _Done when:_ `psql "$SUPABASE_DB_URL" -c 'select 1'` works from your laptop.
- [ ] **T0.3** (P0) Add the GitHub Secrets `SUPABASE_DB_URL` and `CONTACT_EMAIL`. _Done when:_ a test workflow prints `select now()` from the DB.
- [ ] **T0.4** (P1) Register a NASA Earthdata account, approve "NASA GESDISC DATA ARCHIVE" in its applications, and add the `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` secrets. _Done when:_ `earthaccess.login()` succeeds locally.
- [ ] **T0.5** (P0) Create a Render account (**no card**). _Done when:_ you can create a static site.
- [ ] **T0.6** (P1) Set up a Kaggle and/or Colab account for training. Kaggle gives 12 h sessions and is better for the satellite dataset.

## Phase 1 — Ingestion live: the data clock starts (D1)

- [ ] **T1.1** (P0) Write the migrations `0001_core.sql`, `0004_rls.sql` and `0005_seed.sql` (architecture §7) and apply them. _Done when:_ every table exists, the seeds are inserted, and the anon key can `select` from `observations` but cannot insert into it.
- [ ] **T1.2** (P0) Build the `ingest` package skeleton: `config.py`, `db.py` (psycopg pool, `upsert()` helper with `ON CONFLICT`), `http.py` (timeouts, retry/backoff, User-Agent), `runlog.py` (start, step, finish). _Done when:_ unit tests for `upsert()` idempotency pass (running twice gives the same row count).
- [ ] **T1.3** (P0) `sources/openmeteo.py` `current` parser + the `observe` job, step 1 (spec-api §5.1). _Done when:_ `--dry-run` prints 1 row whose `observed_at` matches the `current.time` value in UTC.
- [ ] **T1.4** (P0) `sources/metar.py` + `observe` step 2 (spec-api §5.5), with tests for knots → km/h, Magnus RH and `wxString` parsing (`-RA`, `TSRA`, `VCSH`, missing). _Done when:_ the tests pass and live rows appear.
- [ ] **T1.5** (P0) `forecast` job steps 1–2: `meta.json` due-check, multi-model vault, daily table, `raw_responses` (spec-api §5.2–5.3). _Done when:_ one run inserts about 168 rows per due model and 7 daily rows, and an immediate re-run inserts **only** best_match (the other models aren't due).
- [ ] **T1.6** (P0) Workflows `observe.yml` (`7-59/10 * * * *`) and `forecast.yml` (`17 * * * *`) with `concurrency`, `timeout-minutes` and the pip cache (architecture §6.5). _Done when:_ **3 consecutive scheduled runs** of each are green and `ingestion_runs` shows them.
- [ ] **T1.7** (P0) 🕐 **Milestone: LIVE COLLECTION STARTED.** Write the start time here: `________ MYT`. Data before this time is retrieved, not live. Then do the daily ops checklist (below) every day until grading ends.
- [ ] **T1.8** (P0) Verify the 15-min precipitation semantics (✔ `interval: 900`) and the hour bucketing with a hand check: 4 samples → 1 hourly row in a scratch query.

## Phase 2 — Satellite features + v0 rain indicator (D2)

- [ ] **T2.1** (P0) `sources/himawari.py`: list the AWS prefixes, download S05 B13 R20, decompress with bz2, load with satpy. _Done when:_ a local script prints the BT range (~190–300 K) for one slot.
- [ ] **T2.2** (P0) **Verify V1** (architecture §16): print the lat/lon at the mask centre and edges, then build and cache `masks_S05_R20.npz` (discs + 8 upwind sectors). _Done when:_ the r10/r25/r50 pixel counts are plausible (about 45–60 / 290–370 / 1,150–1,500, since pixels here are ~2.3–2.6 km wide, 40° off the satellite's sub-point). Record the real numbers.
- [ ] **T2.3** (P0) `features/satellite.py` + `observe` step 3, including catch-up (≤ 12 slots) and the `d_bt_*` trends. _Done when:_ `satellite_features` gains 3 rows per 10-min slot, and one observe run takes < 3 min including install.
- [ ] **T2.4** (P0) The `v0-rule` nowcast in `ml/nowcast.py` (architecture §9.1) + `observe` step 4 → `predictions`. _Done when:_ the `v_rain_status` query (T3.3) returns a level for the latest slot.
- [ ] **T2.5** (P1) Write the backfill job steps `om_gapfill`, `reanalysis`, `himawari_gaps` and `retention`, plus `backfill.yml` (`40 19 * * *`). _Done when:_ deleting one 15-min row and re-running the backfill restores it with `is_backfill = true`.
- [ ] **T2.6** (P1) IMERG: `sources/imerg.py` (**verify V3**), `forecast` step 4 and backfill `imerg_catchup`. _Done when:_ `imerg_early` rows arrive with ~4–6 h latency.
- [ ] **T2.7** (P2) Backfill `previous_runs` step (origin `previous_runs`). _Done when:_ a forced gap in `forecasts` is rebuilt.

## Phase 3 — Analytics in the database (D3)

- [ ] **T3.1** (P0) `0002_views.sql`: `lead_bucket`, `v_actual_hourly`, `v_forecasts_all`, `v_pairs`, `v_now`. _Done when:_ `select count(*) from v_pairs` returns more than 0 after D1's first verified hours.
- [ ] **T3.2** (P0) `0003_rpc.sql`, part A (Accuracy): `rpc_forecast_vs_actual`, `rpc_metrics_by_lead`, `rpc_rain_contingency`, `rpc_brier`, `rpc_reliability`, `rpc_leaderboard`, `rpc_daily_pairs`, `rpc_kpis`, `rpc_next_24h`. _Done when:_ each runs as **anon** in < 1 s on the data so far (`EXPLAIN ANALYZE`, **V6**).
- [ ] **T3.3** (P0) Part B (Rain + Health): `v_rain_status`, `v_collection_window`, `v_coverage_daily`, `rpc_uptime_daily`, `rpc_runs_timeline`, `rpc_nowcast_timeline`, `rpc_rain_heatmap`, `rpc_error_heatmap`.
- [ ] **T3.4** (P1) Part C: `rpc_skill_vs_persistence`, `rpc_bias_eval`.
- [ ] **T3.5** (P0) **Sanity notebook** `ml/notebooks/00_sanity.ipynb`: recompute MAE, bias and CSI in pandas from raw rows and compare them with the RPC output. _Done when:_ they match to 3 decimals. Screenshot this for the report as evidence that the metrics are computed correctly.
- [ ] **T3.6** (P0) `python -m iww_ingest.tools.check` prints the row counts, the last run per job and the streak.

## Phase 4 — Dashboard (D4–D7)

- [ ] **T4.1** (P0) Scaffold `web/` with Vite + React + TS, Tailwind v4, shadcn/ui, React Router, TanStack Query and supabase-js; generate the Supabase types; add the self-hosted fonts (Fraunces, IBM Plex Sans/Mono). _Done when:_ `npm run build` passes in CI.
- [ ] **T4.2** (P0) Theme tokens (design-spec §2, §6.5), the dark/light toggle, `AppShell`, top bar, tabs and footer attribution. _Done when:_ both themes pass a contrast spot-check.
- [ ] **T4.3** (P0) **Deploy early:** a Render Static Site with the `/*` → `/index.html` rewrite and env vars set. _Done when:_ the public URL loads and a deep link to `/accuracy` doesn't 404. Write the URL here: `________`.
- [ ] **T4.4** (P0) Shared pieces: the `useEChart` hook + ECharts themes, `ChartCard` (ⓘ / CSV / fullscreen / table view), `KpiTile`, `StatusPill`, `FreshnessBadge`, `EmptyState`, skeletons, URL-state helpers, `fmtMYT()`, the glossary.
- [ ] **T4.5** (P0) **Overview** page (design-spec §4.1): Now card, `RainLamp`, mini map, KPI row, next 24 h, last 72 h.
- [ ] **T4.6** (P0) **Accuracy** page (§4.2): filter bar (variable, `ModelChips`, `TruthSelect`, `LeadSlider`), forecast vs actual, error vs lead, leaderboard, next-day table. _Done when:_ moving the lead slider visibly changes the forecast line and the URL.
- [ ] **T4.7** (P0) **Data Health** page (§4.5): banner, uptime, run timeline, coverage grid, latest runs table.
- [ ] **T4.8** (P1) **Rain & Satellite** page (§4.3): `IRLoopMap` with GIBS frames, latest-frame probing, rings, scrubber and keyboard controls; nowcast timeline synced with the loop; scorecard; reliability; rain heatmap.
- [ ] **T4.9** (P1) Accuracy extras: skill vs persistence and the error heatmap.
- [ ] **T4.10** (P1) **About** page (§4.6), with an architecture SVG exported from Mermaid.
- [ ] **T4.11** (P1) Responsive pass (design-spec §7) and an accessibility pass (focus rings, keyboard, `aria-live`, reduced motion).

## Phase 5 — ML training (D4–D9, runs in the background alongside Phase 4)

**Nowcast**

- [ ] **T5.1** (P1) **Verify V4/V7:** the Himawari archive covers Oct–Dec 2025 and IMERG Final labels are reachable.
- [ ] **T5.2** (P1) `01_nowcast_dataset.ipynb` (Kaggle): stream Oct–Dec 2025 B13 S05 → the same `features/satellite.py` → Parquet, month by month; join the weather features (Open-Meteo Historical Forecast / reanalysis) and the IMERG labels. **Start it on D4**, since it takes hours. _Done when:_ the Parquet has about 13k rows, a recorded label base rate, and no NaN explosions.
- [ ] **T5.3** (P1) `02_nowcast_train.ipynb`: time-blocked split; the three baselines (OM probability, persistence, 235 K rule); logistic regression; LightGBM; threshold selection; metrics (AUC, Brier, BSS, POD/FAR/CSI, warning lead); importance. _Done when:_ LightGBM beats **all three** baselines on validation Brier, or you write down honestly why it doesn't.
- [ ] **T5.4** (P1) _Fallback if T5.2 is late:_ a weather-only nowcast trained on hourly Open-Meteo history. Register it as `v1.0-wx`.

**Bias correction**

- [ ] **T5.5** (P1) `03_bias_train.ipynb`: Previous Runs API Mar 2024 – Sep 2026 (best_match, day 0–7) → LightGBM L1 per variable (temperature first, then RH and wind). _Done when:_ validation MAE improves at each day-lead and the numbers are recorded in `card.json`.

**Deploy the models**

- [ ] **T5.6** (P1) Save `models/<name>/<version>/model.txt` + `card.json`, and write `register_model.py` (insert, activate, sha256).
- [ ] **T5.7** (P1) Inference: `observe` step 4 uses the active LightGBM with `pred_contrib` → `explain`; `forecast` step 3 writes `best_match+ml` predictions. _Done when:_ `v_rain_status.model_version = 'v1.0'` and `best_match+ml` appears in `rpc_leaderboard`.
- [ ] **T5.8** (P2) A small CNN on 64 × 64 IR patches. Only attempt it if T5.3 finished by D7.

## Phase 6 — FastAPI extras + ML Lab (D8–D9)

- [ ] **T6.1** (P1) Create the `api_reader` role (architecture §7.9) and the FastAPI skeleton: settings, psycopg pool, TTL cache, error envelope, CORS, `slowapi`, `/health`, `/meta`. _Done when:_ `/docs` renders locally.
- [ ] **T6.2** (P1) `/models`, `/models/{name}`, `/nowcast/latest`, `/nowcast/evaluation`, `/bias/evaluation` (spec-api §4.2). _Done when:_ a pytest per endpoint passes against a seeded test DB (or recorded fixtures).
- [ ] **T6.3** (P1) `/export/{dataset}.csv` and `/report/summary`.
- [ ] **T6.4** (P1) Deploy `iww-api` on Render (`render.yaml`). _Done when:_ the cold start is < 75 s and memory stays < 350 MB (Render metrics).
- [ ] **T6.5** (P1) **ML Lab** page (design-spec §4.4) with `WakeBanner` and the Supabase fallbacks. _Done when:_ the page is still useful with the API stopped.
- [ ] **T6.6** (P2) `/analytics/onset`, `/analytics/agreement`, `/events` + the **storm replay** UI.

## Phase 7 — Polish (D10)

- [ ] **T7.1** (P1) Capture mode `?capture=1` (design-spec §10).
- [ ] **T7.2** (P1) Copy pass: every ⓘ popover filled in from the glossary; `n` shown on every chart.
- [ ] **T7.3** (P2) Optional models `ecmwf_aifs025_single` (an AI model) and `jma_seamless`: set `is_active` and confirm the vault stores them (**V2**). This makes a nice "AI vs physics" leaderboard story.
- [ ] **T7.4** (P2) A backup trigger: a cron-job.org job calling `workflow_dispatch` with a fine-grained PAT (Actions: write, on this repo only).
- [ ] **T7.5** (P1) Lighthouse check on the Overview page: performance ≥ 80 and accessibility ≥ 95.

## Phase 8 — Freeze, report, video, submit (D10–D13)

- [ ] **T8.1** (P0) **Freeze the data window:** `Wed 4 Nov 00:00 → Sat 7 Nov 00:00 MYT`, or `Sun 1 Nov 00:00 → Sat 7 Nov 00:00 MYT` if the data check fails ([plan §5.3](Implementation-plan.md)). Final window: `________`. Every report number uses exactly this range (set in `FROZEN_WINDOW`). Live collection **keeps running**; only the report uses the frozen window.
- [ ] **T8.2** (P0) Export the evidence: dashboard screenshots, the `ingestion_runs` uptime, the Health banner, and the sanity-notebook comparison.
- [ ] **T8.3** (P0) Write the report (≤ 8 pages, Arial 11, references Arial 8 in IEEE style). Suggested page budget:

  | Section | Pages | Source material |
  |---|---|---|
  | 1. Introduction | 0.5 | suggestion.md §1–2 |
  | 2. Problem statement (incl. duration, how the data was retrieved, what "actual" means) | 0.5 | suggestion.md §2 "actual weather problem", plan §5.3 |
  | 3. System design (5-layer diagram, components, data flow) | 1.5 | architecture §3, §3.1, §3.2 |
  | 4. Database design (ER diagram, forecast vault, views, why Postgres) | 1.5 | architecture §7, §11 |
  | 5. Data visualization (tools + 4 figures) | 1.5 | design-spec, screenshots |
  | 6. Cost (RM0 table + paid comparison) | 0.5 | architecture §15.3 |
  | 7. Conclusion (findings, best model, ML result, limitations) | 0.75 | `rpc_leaderboard`, `card.json` |
  | References | 0.25 | suggestion.md sources (re-check secondary ones) |

  The brief says to put the **marking rubric on the last page**. The report stays within 8 pages including it.
- [ ] **T8.4** (P0) Record the video: **≤ 2 min**, you presenting (solo). Follow the demo script below.
- [ ] **T8.5** (P0) Make the source zip with `git archive --format=zip -o iww-source.zip HEAD`. It contains tracked files only, so there's no `node_modules`, `.venv`, `dist` or executables. Check that the zip has **no** `.exe` or `.dll` files and no secrets (`.env` is not tracked).
- [ ] **T8.6** (P0) Submit: zip + deployed URL + report PDF + video. Keep the jobs running until grading is done.

---

## Daily ops checklist (5 min, every day from D1 to grading)

- [ ] `/health`: is live collection still running? Any red days?
- [ ] GitHub → Actions: any failing workflow? (GitHub also emails on failure.)
- [ ] Supabase → Usage: DB size (< 100 MB expected) and no pause warnings.
- [ ] Render → bandwidth (< 5 GB per month) and that the site is not suspended.

## Verification items (from architecture §16)

| ID | Item | Task |
|---|---|---|
| V2 | `meta.json` keys match the seamless models | T1.5 / T7.3 |
| V6 | RPCs < 1 s as anon | T3.2 |

V1, V3, V4, V5 and V7 covered Himawari and IMERG, which are out of scope since 7 Nov.

---

## Demo script (≤ 2 min, solo)

| Time | Show | Say |
|---|---|---|
| 0:00–0:12 | Overview, dark theme | "Iskandar Weather Watch monitors Seri Iskandar every 10 minutes and checks how good the forecast really is." |
| 0:12–0:30 | Architecture diagram | "GitHub Actions pulls Open-Meteo and the Ipoh airport station, stores everything in Postgres, and the metrics are computed in SQL. Total cost: RM0." |
| 0:30–0:55 | Accuracy: move the lead slider 24 → 144 h; leaderboard | "We retrieved past forecasts from Open-Meteo's archive of earlier model runs, so we can see accuracy decay with lead time, and which model wins for Seri Iskandar." |
| 0:55–1:15 | Overview: rain lamp and METAR cross-check | "The rain lamp shows Open-Meteo's own probability, and we cross-check the model against a real airport station." |
| 1:15–1:40 | Accuracy: `best_match` vs `best_match+ml` | "We trained a bias-correction model on over two years of past forecasts and tested it on days it never saw. It changed temperature error by X %." |
| 1:40–1:55 | Data Health banner + uptime | "The report window is three days of retrieved data from 4 November. Live collection has run since 7 November with Y % uptime, gaps repaired automatically." |
| 1:55–2:00 | URL on screen | "Thanks. The link is in our report." |

Fill in X from the frozen window and Y from `rpc_uptime_daily`. If the data check extends the window, change "three days" and "4 November" to match. If the model didn't help, say so.

## Definition of Done (every task)

- Code is committed to `main`, CI is green, and no secrets are in the diff.
- For anything that writes data: it is idempotent (a re-run adds no duplicates) and it logs to `ingestion_runs`.
- For anything a user sees: both themes work, `n` is shown, and loading, empty and error states exist.
- Numbers shown match the SQL (spot-checked against the sanity notebook).

## Rubric checklist

| Rubric (marks) | Evidence in this build | Tasks |
|---|---|---|
| Introduction (5) | Background on tropical convective rain; objectives | T8.3 |
| Problem statement (5) | 3 days of retrieved data, stated openly; the challenges (model-based "actual", schedule delays) | T8.3, T4.7 |
| System & DB design (30) | 5-layer diagram, data flow, ER diagram, forecast store, views and RPCs, RLS, run log | Phases 1–3, T8.3 |
| Data visualization (15) | Three interactive tabs, lead slider, leaderboard, themes | Phase 4 |
| Cost (5) | RM0 table with free-tier limits + paid comparison | T8.3 |
| Conclusion (5) | Best model, error vs lead, rain skill, ML result, limitations | T8.1, T8.3 |
| Technical implementation (20) | Working jobs, 72 h window with retrieved vs live data shown, correct metrics (sanity notebook) | Phases 1–3, T3.5 |
| Report format (5) | ≤ 8 pages, Arial 11, IEEE references at 8 pt, rubric on the last page | T8.3 |
| Presentation (10) | 2-min video following the demo script | T8.4 |
| **Bonus (b)** | Multi-variable, multi-model, lead-time metrics, CSI. Brier is live data only | T3.2, T4.6 |
| **Bonus (c)** | Bias-correction ML, data-health proof | Plan Phase 5 |
| Bonus (a) | Not attempted (no hardware) | — |
