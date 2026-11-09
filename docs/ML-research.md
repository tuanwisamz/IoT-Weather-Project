# IoT Weather Project — Research: more correction models, live running and retraining

**Written 7 Nov 2026 · Status: built the same day (Phase 5b, ML1–ML7); window result in §3.6 · Build plan: Implementation-plan.md (kept locally) §5.8 and Phase 5b**

This document answers three questions:

1. How should we build correction models for **humidity, wind speed, pressure** and **rain occurrence** ("will it rain this hour?"), next to the existing temperature model?
2. How much would each one actually help in Seri Iskandar?
3. How should the models **run live** on new forecasts, and **retrain** as the weather models change?

It combines published methods (§2) with a test on our own data (§3). The test used only data up to 31 Oct 2026, so the report window (4–7 Nov) is still unseen by every model and stays the final test.

---

## 1. Summary

| Model | Method | Gain in our test (13-month cross-validation) | Decision |
|---|---|---|---|
| Humidity | LightGBM on the forecast error, L1 loss, clipped to 0–100 % | Average error 5.75 → **4.92 %** (−14 %) | Build |
| Wind speed | LightGBM on the forecast error, L1 loss, clipped at 0 | 2.89 → **2.32 km/h** (−20 %), but strong winds are forecast too weak | Build, best average error (owner's choice) |
| Pressure | LightGBM on the forecast error, L1 loss | 0.72 → **0.58 hPa** (−20 %), almost all of it from a time-of-day pattern | Build |
| Rain occurrence | LightGBM classifier giving a chance of rain, plus a yes/no cut-off | Rain score (CSI) 0.34 → **0.38**, rain-chance score 7 % better than the hourly average. **No gain** when the season was missing from training | Build, report honestly (owner's choice) |
| Temperature v1.1 | As v1.0, without day-of-year inputs, trained to 31 Oct | 1.16 → **0.89 °C** (v1.0's setup: 0.92) | Retrain for live use. v1.0 stays the report's result |

**Main finding:** the **day-of-year inputs** hurt. We have only 13 months of usable history (Best Match changed in mid-2025), so day of year lets a model memorise one year's seasons instead of learning the forecast's habits. Without it, every variable beats both baselines in every test.

**Live running:** score each new Best Match forecast every hour, inside the `forecast` workflow.

**Retraining:** automatic, monthly. A new version only switches on if it beats the current one on the most recent month, and the 4–7 Nov results always keep using the versions trained before November.

---

## 2. What the literature says

Reading depth is noted in the reference list (§8). Most sources were read at abstract level, so the claims below stay at that level.

### 2.1 Correcting forecasts with statistics is standard practice

Correcting a weather model's output with statistics learned from its past errors is called **post-processing**. The classic form is **Model Output Statistics (MOS)**: a regression from the model's forecast to the observed weather (Glahn & Lowry, 1972). Post-processing is now a standard step at many national weather services, from simple bias corrections to methods that adjust the whole forecast distribution (Vannitsem et al., 2021). Our temperature model is a MOS-style correction: it learns the forecast error (truth minus forecast) and adds it back.

Two families matter here:
- **Distribution-based methods** such as EMOS correct the mean and the spread of an ensemble (Gneiting et al., 2005). For wind speed, which can't be negative, the normal distribution is replaced by a truncated one (Thorarinsdottir & Gneiting, 2010). These need an *ensemble*: many runs of the same model. Open-Meteo's Previous Runs archive gives us one deterministic forecast per lead, so these methods don't apply directly. They are the natural next step if ensemble data is ever added.
- **Machine-learning methods** such as gradient-boosted trees and neural networks can use many extra inputs and non-linear relationships (Rasp & Lerch, 2018). In a systematic comparison for wind gusts, the machine-learning methods that use extra inputs, gradient boosting among them, clearly beat the simpler statistical ones (Schulz & Lerch, 2022).

### 2.2 Gradient-boosted trees work for humidity, wind and temperature at single sites

- The Finnish Meteorological Institute runs a gradient-boosted tree correction (XGBoost) operationally for 2 m temperature, 2 m humidity, 10 m wind speed and gusts. It reports a 24–29 % smaller error (RMSE) than the raw model, even with a modest set of inputs (Hieta & Partio, 2025).
- A single-station LightGBM correction of temperature and wind forecasts is described by Tang et al. (2022).
- LightGBM itself is a fast implementation of gradient-boosted decision trees (Ke et al., 2017). It's already used for our temperature model.

**Inference:** a LightGBM error model per variable, like our temperature one, is a well-supported choice for this project's single site and deterministic forecasts.

### 2.3 Known weak spots, and how others handle them

- **Strong winds come out too weak.** A model trained to minimise average error pulls forecasts toward typical values. FMI reports exactly this for wind and adds **quantile mapping** to restore the high end (Hieta & Partio, 2025, via their EMS 2024 abstract). Our test shows the same effect (§3.4).
- **Humidity has hard limits** (0–100 %) and is tied to temperature. Common approaches are to correct the dew point and derive humidity from it, or to build the physical link into the model (Zanetta et al., 2023). We clip to 0–100 % for now and list the dew-point route as an upgrade.
- **Pressure** at low latitudes has a strong daily cycle, the atmospheric pressure tides, with 24-hour and 12-hour components (Dai & Wang, 1999). That is why the hour of day matters so much for pressure (§3.4).
- **Probabilities from boosted trees are often miscalibrated**: they tend to avoid values near 0 and 1. Platt scaling or isotonic regression can fix this. Isotonic regression overfits when data is scarce (Niculescu-Mizil & Caruana, 2005). Rain-chance forecasts are scored with the **Brier score** (Brier, 1950). Logistic regression is the classic MOS method for rain probability (Wilks, 2009).

### 2.4 Rain in the tropics is hard: the main counterpoint

- Across the tropics, raw global ensemble rainfall forecasts show only modest skill, and post-processing changed that skill little. In several, mostly drier, regions neither raw nor corrected forecasts improved over almost a decade (Vogel et al., 2020).
- Over northern tropical Africa, a simple statistical model using recent observed rainfall beat global model forecasts, even after post-processing (Vogel et al., 2021).
- Over Southeast Asia, including Malaysia, high-resolution ensembles forecast 3-hour rainfall skilfully only at scales above about 200 km (Ferrett et al., 2021). Seri Iskandar is a single point.

**Inference:** a large gain for hourly rain at one point is unlikely. A small gain, or none, is a normal and reportable result. Our test agrees (§3.4).

### 2.5 Weather models change, so corrections must be retrained

Changes to the weather model alter the correction a post-processing method needs (Vannitsem et al., 2021). Canada's **Updateable MOS** was designed for this: it re-fits regularly and phases out data from the old model version as data from the new one builds up (Wilson & Vallée, 2002). We have seen this ourselves: Best Match switched from forecasting too hot to too cold around Q3 2025, which forced training to start in Oct 2025 (Implementation-plan.md §5.4, kept locally).

---

## 3. Test on our data

### 3.1 Setup

| Item | Value |
|---|---|
| Source | Open-Meteo Previous Runs, Best Match, Seri Iskandar (4.35993, 100.98491) |
| Truth | Day-0 value of each variable (Open-Meteo's newest run), as for temperature. For rain: day-0 precipitation ≥ 0.1 mm in the hour |
| Forecast | `<variable>_previous_day1..7`, so leads of 24–168 h |
| Inputs | Forecast temperature, humidity, wind speed, wind direction (sin/cos), precipitation, pressure, cloud cover, CAPE, dew point, lead, local hour (sin/cos), and day of year (sin/cos) in some runs |
| Period | 1 Oct 2025 → 31 Oct 2026, 66,441 rows (hours × 7 leads). **Nothing from November** |
| Baselines | The raw forecast · a constant correction · a **time-of-day correction** (median error per lead day and local hour, the classic MOS-style baseline) · for rain, the hourly rain frequency (climatology) |
| Model settings | The temperature model's LightGBM settings (L1 loss for the regressions, log-loss for rain), 200 rounds in cross-validation |
| Code | Research scripts in a scratch folder, not in the repo. The built version is `server/ml/train_models.py`, which reproduces §3.3 within 1 % |

The pipeline was checked first: it reproduces the temperature model's validation numbers exactly (raw 1.298 → model 0.987 °C).

### 3.2 First test: the temperature model's split, with day of year

Train 1 Oct 2025 → 30 Jun 2026, validate 1 Jul → 31 Oct 2026. Average error (MAE) on validation:

| Variable | Raw | Constant correction | LightGBM, with day of year | LightGBM, without |
|---|---|---|---|---|
| Humidity (%) | 6.38 | 5.68 | 5.93 ✗ | **5.44** |
| Wind (km/h) | 2.90 | 2.84 | 2.40 | **2.42** |
| Pressure (hPa) | 0.73 | 0.72 | 0.67 | **0.59** |
| Rain score, CSI (higher is better) | 0.358 | — | 0.323 ✗ | **0.374** |
| Rain-chance skill vs hourly average | — | — | −14 % ✗ | −1 % |

With day of year, humidity lost to a constant correction, and rain lost to the raw forecast. Validation (Jul–Oct) is a season that training (Oct–Jun) never saw, so day of year asked the models to guess about months they had no data for. Without it, humidity, wind and pressure beat both baselines. Rain only ties.

### 3.3 Second test: month-by-month cross-validation

Each of the 13 months was predicted by a model trained on the other 12, with a 3-day gap on each side. This matches how the live models will be used: trained on every season, then applied to the next month.

| Average error | Raw | Time-of-day correction | LightGBM, with day of year | LightGBM, without day of year |
|---|---|---|---|---|
| Temperature (°C) | 1.163 | 0.951 | 0.918 | **0.893** (−23 %) |
| Humidity (%) | 5.752 | 5.215 | 5.214 | **4.917** (−15 %) |
| Wind (km/h) | 2.889 | 2.823 | 2.358 | **2.317** (−20 %) |
| Pressure (hPa) | 0.717 | 0.588 | 0.598 | **0.575** (−20 %) |

| Rain occurrence | Hourly average | Raw ≥ 0.1 mm | LightGBM, with day of year | LightGBM, without day of year |
|---|---|---|---|---|
| Brier score (lower is better) | 0.2045 | — | 0.2066 | **0.1908** (7 % better than the hourly average) |
| Rain score, CSI | — | 0.341 | 0.326 | **0.381** |
| CSI, 1 day ahead | — | 0.394 | 0.349 | **0.408** |
| CSI, 7 days ahead | — | 0.318 | 0.316 | **0.370** |
| Rain hours forecast ÷ rain hours observed | — | 1.17 | 1.10 | 1.44 |

**Month by month:** temperature, wind and pressure improve in every month or tie. Humidity loses slightly in Apr 2026 (5.31 vs raw 5.27), and in Oct 2026 the simple time-of-day correction beats LightGBM (4.49 vs 4.71).

### 3.4 What the numbers mean

- **Humidity:** a solid gain of about 14–15 %, mostly from removing a bias. The raw forecast is about 3 % too humid on average. Very humid hours get *worse*: on the most humid 10 % of hours, the error rises from 1.95 to 3.63 %, because the correction pulls values down from near saturation. Quantile mapping recovers part of that (2.92 %) at a small cost overall (5.08 %).
- **Wind:** about 20 % smaller average error, in every month. But the corrected forecast is much flatter than real wind: its spread is less than half the real one (1.49 vs 3.20 km/h), so strong winds are forecast too weak. Quantile mapping restores the spread (3.11 km/h) and cuts the error on the windiest 10 % of hours from 5.42 to 4.31 km/h, but the average gain drops to about 5 % (2.74 km/h). **Owner's decision: use the best-average version and state the flattening.**
- **Pressure:** about 20 % smaller error, but the time-of-day correction alone gets almost all of it (0.588 vs 0.575). The pressure error is mostly a daily cycle, which fits the pressure tides (§2.3). We keep LightGBM so all models share one code path, and we report the time-of-day baseline next to it.
- **Rain:** a small gain when the season is in training: 12 % on CSI and 7 % on Brier against the hourly average. **No gain** when it isn't (§3.2). The model also forecasts rain about 44 % more often than it happens, because the cut-off is tuned for CSI. Platt scaling didn't help (Brier 0.1933 vs 0.1908): with every month in training, the probabilities are already fairly calibrated. This matches the literature (§2.4). **Owner's decision: build it and report the result as it is.**
- **Temperature:** dropping day of year helps in cross-validation (0.918 → 0.893 °C) but not on the original split (0.987 → 1.029 °C). That's mixed evidence, so v1.0 stays untouched as the report's model. v1.1 (no day of year, trained to 31 Oct) is used for live forecasts only, because live use matches the cross-validation setup.

### 3.5 Limits of this test

- **The truth is a model analysis, not an instrument**, for every variable. For rain it is Open-Meteo's own rain, so the rain model partly learns to predict Best Match's own day-0 rain. The window test therefore also checks against Ipoh airport (METAR), which has real temperature, humidity, wind, pressure and a yes/no rain report.
- **One year of data.** The months are not independent, and a single unusual season can sway the result.
- **Settings were not tuned.** The temperature model's settings and a fixed 200 rounds were used throughout, so results are slightly pessimistic.
- **Leads are whole days.** Live forecasts have leads of 1–168 h. Below 24 h the models have no training data at all (§4.3).

### 3.6 Result on the report window (scored once, after the configuration was recorded)

The configuration was written in the plan's §10 before scoring. 4–7 Nov, leads 24–144 h, n = 432, `best_match` → `best_match+ml`:

| Variable | Against the analysis | Against METAR (Ipoh airport) |
|---|---|---|
| Humidity (%) | 3.919 → 3.881 | 6.275 → **3.828** |
| Wind (km/h) | 2.904 → **2.109** | 3.410 → **2.612** |
| Pressure (hPa) | 0.692 → **0.533** | 1.074 → **0.720** |
| Rain CSI (higher is better) | 0.482 → 0.471 | 0.121 → 0.088 |
| Rain Brier vs hourly climatology | 0.2166 vs 0.2478 | 0.2510 vs 0.1696 |
| Temperature v1.1 (secondary; v1.0 is the report's) | 1.296 → 0.860 | 1.545 → 1.081 |

Wind and pressure improve against both truths. Humidity barely moves against the analysis but improves strongly against the airport, where raw Best Match is far too humid. Rain doesn't help: CSI drops slightly against both truths, and the Brier score beats climatology only against the analysis. The airport reported rain in 12.5 % of the window's hours and the analysis in 48.6 %, so a model trained on the analysis's rain over-forecasts the airport's. This matches §2.4.

---

## 4. Design

### 4.1 The models

| Name | Target | Loss | Output | Notes |
|---|---|---|---|---|
| `bias_humidity` v1.0 | Humidity error (%) | L1 | Corrected humidity, clipped 0–100 | Dew-point route is a later upgrade |
| `bias_wind` v1.0 | Wind speed error (km/h) | L1 | Corrected wind, clipped ≥ 0 | Flattening stated on the dashboard and in the report |
| `bias_pressure` v1.0 | Pressure error (hPa) | L1 | Corrected pressure | Time-of-day baseline reported next to it |
| `rain_occurrence` v1.0 | Day-0 rain ≥ 0.1 mm in the hour | Log-loss | Chance of rain (0–1) + yes/no at a cut-off | Cut-off chosen in cross-validation for best CSI, stored in `card.json` |
| `bias_temperature` v1.1 | Temperature error (°C) | L1 | Corrected temperature | Live only. v1.0 stays the report's model |

**Shared rules**
- Same inputs for every model: the forecast's temperature, humidity, wind speed and direction, precipitation, pressure, cloud cover, CAPE and dew point, plus lead and local hour. **No day of year.** Every input is stored for both retrieved and live forecasts, so training and live scoring use identical inputs.
- Training: 1 Oct 2025 → 31 Oct 2026. Rounds and the rain cut-off are chosen by the 13-month cross-validation, never by the report window.
- The configuration is **written down in §10 of the plan before the window is scored**, then scored once on 4–7 Nov against both truths, like temperature.

### 4.2 Storing and showing the results

- Predictions go to the existing `predictions` table: `humidity_pct`, `wind_speed_kmh`, `pressure_hpa`, `rain_prob` and `rain_yes`.
- Migration `0008` changes `v_forecasts_all` so the `best_match+ml` row also carries pressure, rain chance and rain yes/no. Before it, the view passed only temperature, humidity and wind. ML rain amounts are left out of the millimetre error charts, because the model forecasts yes/no, not millimetres.
- **The report window keeps its numbers.** Before `0008` the view only showed predictions from the *active* version, so activating v1.1 would have silently replaced v1.0's window results. `0008` instead keeps every scored prediction and picks one per forecast hour and variable: versions flagged `is_report` (v1.0 of every model) first, then the newest. The window is never re-scored, so it keeps its report versions. Live hours show the version that was active when they were scored.
- Dashboard: the ML button works for every variable except rain amounts; the leaderboard gains a pressure column and ML rain scores; the "Next 24 hours" chart gets the corrected temperature line (`rpc_next_24h` already returns it); a "Live check" card on Data Health compares raw and corrected error since live collection began (up to the last 30 days).

### 4.3 Live running

- **Where:** a `score` step in `forecast.yml` (`python -m iww_ingest.jobs.score`), run straight after the forecast job every hour. `lightgbm` comes from `server/ingest/requirements-score.txt`, installed only by that step.
- **What:** each Best Match forecast (origin `snapshot`) from the last 6 hours that has no prediction yet, for each active model. To bound growth, live predictions older than 3 hours are thinned to the forecasts issued at 00, 06, 12 and 18 UTC; the report window is never touched. The step is idempotent and logs to `ingestion_runs` like every other job.
- **Leads under 24 h:** the models never saw them. In LightGBM these leads fall into the 24 h branch, so they get the day-1 correction. Against Open-Meteo's analysis, that probably over-corrects at very short leads, since the error shrinks toward zero there. **As built:** they are scored and shown in their own lead buckets on the Live check card. After 14 days of live data (about 21 Nov), compare raw and corrected error in the 0–6, 6–12 and 12–24 h buckets, and keep them only where the correction helps (plan task ML8).

### 4.4 Monthly retraining

Following the Updateable-MOS idea (§2.5):

1. **When:** a GitHub workflow `retrain.yml` runs on the 2nd of each month, plus a manual button.
2. **Data:** Previous Runs from 1 Oct 2025 to the end of last month, so the window grows each month. If Best Match changes again, the start date moves forward, as it did in 2025.
3. **Challenger vs champion:** train a challenger on everything *before* last month and score it on last month. Score the current active version on the same month.
4. **Switch only if better:** if the challenger wins, refit it on all the data, including last month, and activate it as the next version (v1.1 or v1.2, …). If not, keep the current version. Record the comparison either way (`metrics.retrain_checks` on the champion). A champion trained on the month being judged is never replaced, so the first run on 2 Dec is a tie by design, and 2 Jan is the first that can change a model.
5. **Storage:** the model text goes into the database (a new `ml_models.artifact` column), so the workflow never has to push to the repo. The live `score` step loads the active model from there.
6. **The report never changes:** retrained versions aren't flagged `is_report` and never score the window, so the 4–7 Nov figures keep their report versions (§4.2).

---

## 5. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| A model loses to the raw forecast on 4–7 Nov | Nothing to show for it | Report it. It's still a fair out-of-sample test, and rain is expected to be weak (§2.4) |
| Three days is a small test | Results are noisy | Show `n`, and report the cross-validation next to the window result |
| Short leads (< 24 h) over-corrected | Worse "Next 24 hours" line | Show them separately, check after 14 days, switch off where they don't help (§4.3) |
| A retrain picks a worse model | Live accuracy drops | Challenger must beat the champion on last month; rollback = activate the old version |
| Best Match changes again | Corrections go wrong | The monthly comparison catches it; move the training start date |
| Previous Runs is slow or times out | Retrain fails | Chunked fetch with retries (already used); a failed retrain keeps the current version |
| v1.1 silently replaces v1.0 in the report | Report numbers change | `0008` pins the report version for 4–7 Nov, with a DB test |

---

## 6. What this changes elsewhere

- Implementation-plan.md (kept locally): decision 12, design §5.8, tasks in Phase 5b, risks 11–13, the progress log.
- architecture.md (kept locally) §9.2: the variable list, live scoring and retraining.
- [Overview.md](Overview.md): the plain-language results and limits.

---

## 7. Sources at a glance

| Source | Type | Supports |
|---|---|---|
| Glahn & Lowry (1972) | Journal paper, foundational | MOS: regression from model output to observed weather |
| Vannitsem et al. (2021) | Review | Post-processing is standard practice; model changes alter corrections |
| Gneiting et al. (2005); Thorarinsdottir & Gneiting (2010) | Journal papers | EMOS, truncated distributions for wind (need an ensemble) |
| Rasp & Lerch (2018); Schulz & Lerch (2022) | Journal papers | Machine learning beats simpler methods when it can use extra inputs |
| Hieta & Partio (2025) | Journal paper, operational | Boosted trees for temperature, humidity, wind at FMI; 24–29 % lower RMSE |
| Tang et al. (2022) | Journal paper | Single-station LightGBM correction of temperature and wind |
| Ke et al. (2017) | Conference paper | LightGBM |
| Zanetta et al. (2023) | Journal paper | Humidity must stay consistent with temperature |
| Dai & Wang (1999) | Journal paper | Daily pressure tides |
| Niculescu-Mizil & Caruana (2005); Brier (1950); Wilks (2009) | Conference and journal papers | Calibrating and scoring rain probabilities |
| Vogel et al. (2020, 2021); Ferrett et al. (2021) | Journal papers | Rain forecasts in the tropics and Southeast Asia have limited skill |
| Wilson & Vallée (2002) | Journal paper, operational | Regular re-fitting as weather models change |

---

## 8. References

Every entry was found in Crossref by its DOI or title, and the authors, year, title, journal, volume and pages match that record. Ke et al. (2017), which has no DOI, was checked on the NeurIPS proceedings site. **[Metadata verified]** means the record was confirmed but only the abstract or a summary was read, so the claims above stay at abstract level. Read the full papers before quoting numbers beyond those given here.

- Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review, 78*(1), 1–3. https://doi.org/10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2 **[Metadata verified]**
- Dai, A., & Wang, J. (1999). Diurnal and semidiurnal tides in global surface pressure fields. *Journal of the Atmospheric Sciences, 56*(22), 3874–3891. https://doi.org/10.1175/1520-0469(1999)056<3874:DASTIG>2.0.CO;2 **[Metadata verified]**
- Ferrett, S., Frame, T. H. A., Methven, J., Holloway, C. E., Webster, S., Stein, T. H. M., & Cafaro, C. (2021). Evaluating convection-permitting ensemble forecasts of precipitation over Southeast Asia. *Weather and Forecasting, 36*(4), 1199–1217. https://doi.org/10.1175/WAF-D-20-0216.1 **[Metadata verified]**
- Glahn, H. R., & Lowry, D. A. (1972). The use of model output statistics (MOS) in objective weather forecasting. *Journal of Applied Meteorology, 11*(8), 1203–1211. https://doi.org/10.1175/1520-0450(1972)011<1203:TUOMOS>2.0.CO;2 **[Metadata verified]**
- Gneiting, T., Raftery, A. E., Westveld, A. H., & Goldman, T. (2005). Calibrated probabilistic forecasting using ensemble model output statistics and minimum CRPS estimation. *Monthly Weather Review, 133*(5), 1098–1118. https://doi.org/10.1175/MWR2904.1 **[Metadata verified]**
- Hieta, L., & Partio, M. (2025). Operational machine learning post-processing of short-range temperature, humidity, wind speed and gust forecasts. *Meteorological Applications, 32*(4). https://doi.org/10.1002/met.70074 **[Metadata verified]**
- Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q., & Liu, T.-Y. (2017). LightGBM: A highly efficient gradient boosting decision tree. In *Advances in Neural Information Processing Systems 30* (pp. 3146–3154). https://proceedings.neurips.cc/paper/2017/file/6449f44a102fde848669bdd9eb6b76fa-Paper.pdf **[Metadata verified]**
- Niculescu-Mizil, A., & Caruana, R. (2005). Predicting good probabilities with supervised learning. In *Proceedings of the 22nd International Conference on Machine Learning* (pp. 625–632). ACM. https://doi.org/10.1145/1102351.1102430 **[Metadata verified]**
- Rasp, S., & Lerch, S. (2018). Neural networks for postprocessing ensemble weather forecasts. *Monthly Weather Review, 146*(11), 3885–3900. https://doi.org/10.1175/MWR-D-18-0187.1 **[Metadata verified]**
- Schulz, B., & Lerch, S. (2022). Machine learning methods for postprocessing ensemble forecasts of wind gusts: A systematic comparison. *Monthly Weather Review, 150*(1), 235–257. https://doi.org/10.1175/MWR-D-21-0150.1 **[Metadata verified]**
- Tang, R., Ning, Y., Li, C., Feng, W., Chen, Y., & Xie, X. (2022). Numerical forecast correction of temperature and wind using a single-station single-time spatial LightGBM method. *Sensors, 22*(1), 193. https://doi.org/10.3390/s22010193 **[Metadata verified]**
- Thorarinsdottir, T. L., & Gneiting, T. (2010). Probabilistic forecasts of wind speed: Ensemble model output statistics by using heteroscedastic censored regression. *Journal of the Royal Statistical Society: Series A (Statistics in Society), 173*(2), 371–388. https://doi.org/10.1111/j.1467-985X.2009.00616.x **[Metadata verified]**
- Vannitsem, S., Bremnes, J. B., Demaeyer, J., Evans, G. R., Flowerdew, J., Hemri, S., Lerch, S., Roberts, N., Theis, S., Atencia, A., Ben Bouallègue, Z., Bhend, J., Dabernig, M., De Cruz, L., Hieta, L., Mestre, O., Moret, L., Plenković, I. O., Schmeits, M., … Ylhaisi, J. (2021). Statistical postprocessing for weather forecasts: Review, challenges, and avenues in a big data world. *Bulletin of the American Meteorological Society, 102*(3), E681–E699. https://doi.org/10.1175/BAMS-D-19-0308.1 **[Metadata verified]**
- Vogel, P., Knippertz, P., Fink, A. H., Schlueter, A., & Gneiting, T. (2020). Skill of global raw and postprocessed ensemble predictions of rainfall in the tropics. *Weather and Forecasting, 35*(6), 2367–2385. https://doi.org/10.1175/WAF-D-20-0082.1 **[Metadata verified]**
- Vogel, P., Knippertz, P., Gneiting, T., Fink, A. H., Klar, M., & Schlueter, A. (2021). Statistical forecasts for the occurrence of precipitation outperform global models over northern tropical Africa. *Geophysical Research Letters, 48*(3), e2020GL091022. https://doi.org/10.1029/2020GL091022 **[Metadata verified]**
- Wilks, D. S. (2009). Extending logistic regression to provide full-probability-distribution MOS forecasts. *Meteorological Applications, 16*(3), 361–368. https://doi.org/10.1002/met.134 **[Metadata verified]**
- Wilson, L. J., & Vallée, M. (2002). The Canadian Updateable Model Output Statistics (UMOS) system: Design and development tests. *Weather and Forecasting, 17*(2), 206–222. https://doi.org/10.1175/1520-0434(2002)017<0206:TCUMOS>2.0.CO;2 **[Metadata verified]**
- Zanetta, F., Nerini, D., Beucler, T., & Liniger, M. A. (2023). Physics-constrained deep learning postprocessing of temperature and humidity. *Artificial Intelligence for the Earth Systems, 2*(4). https://doi.org/10.1175/AIES-D-22-0089.1 **[Metadata verified]**
- Open-Meteo. (n.d.). *Previous Runs API*. Retrieved 7 November 2026, from https://open-meteo.com/en/docs/previous-runs-api
