# Iskandar Weather Watch: a plain-language guide

**Open the dashboard at:** [add the website link here once it's online]

This guide explains what our system does, where its information comes from and what each part of the dashboard shows. You don't need any technical knowledge to follow it.

---

## The system in one minute

Iskandar Weather Watch is a website about the weather in **Seri Iskandar, Perak**. It answers two questions:

1. **What's the weather like right now?**
2. **How good are weather forecasts for our town?**

The second question is the heart of the project. Forecasts on phone apps come from big computer weather models run by weather agencies around the world. We collected forecasts from four of them, waited to see what the weather actually did, and measured how close each forecast came. We also built our own small correction, a "learning" program that improves one of the forecasts.

The website shows all of this in charts and tables, in three pages: **Overview**, **Accuracy** and **Data Health**.

---

## Where the information comes from

We don't use our own weather sensors. Good sensors are expensive, and free public weather services already provide what we need. Everything comes from two sources:

| Source | What it gives us | How often |
|---|---|---|
| **Open-Meteo** (a free weather service) | The weather "right now" for Seri Iskandar, and forecasts from four weather models | Every 15 minutes |
| **Ipoh airport weather station** (Sultan Azlan Shah Airport, code WMKI) | Real instrument readings: temperature, humidity, wind, pressure and whether it's raining | Every hour |

**Why two sources?** Open-Meteo's "right now" values for our town are an estimate built by computer, not a thermometer reading. The airport, about 26 km away, has real instruments. We use the airport as a second opinion, to check that our results still hold against measured weather.

### The four forecasts we compare

| Name on the dashboard | Who makes it |
|---|---|
| **Best Match** | Open-Meteo's own pick, blending the models it thinks suit our area best. This is the forecast a typical weather app would show. |
| **ECMWF IFS** | The European weather centre |
| **NOAA GFS** | The United States weather service |
| **DWD ICON** | The German weather service |
| **Best Match + ML** | Our own corrected version of Best Match (see "Our learning programs" below). It corrects temperature, humidity, wind and pressure, and says yes or no to rain for each hour. |

---

## How it works behind the scenes

Think of it as three small collectors that run on their own, on a timer, using a free online service called GitHub:

- **The observer** (every 10 minutes) writes down the current weather in Seri Iskandar and the latest airport reading.
- **The forecaster** (every hour) saves the newest forecasts from all four models for the next 7 days.
- **The repairer** (every night at 3:40 am) fills any gaps if a collector missed a turn, and tidies up old data.

Everything they collect goes into one online storage space (called Supabase). The website reads from that storage whenever someone opens it. Nothing has to be left running on anyone's laptop.

### "Retrieved" and "live" data

This is the most important thing to understand about our results.

- **Retrieved data (Wed 4 Nov to Sat 7 Nov):** the project started late, so we couldn't record these days as they happened. Instead we fetched them afterwards from Open-Meteo's public archive, which keeps the forecasts it issued in the past and the weather that followed. This is real data, but it was **collected after the event**. All of our accuracy results use these three days, called the **report window**.
- **Live data (from Sat 7 Nov, 1:15 pm):** from then on, the collectors record the weather as it happens.

The dashboard always labels which is which. Please describe it the same way: the 4–7 Nov results come from **retrieved** data, not from live collection.

We fixed the report window *before* looking at any results, based only on whether enough data was there (it was: all 72 hours were complete, including 35 hours of rain). We never moved it to make the results look better.

---

## Things you'll see on every page

**Top bar, left to right:**
- **Iskandar Weather Watch:** the site name.
- **Overview, Accuracy, Data Health:** click to switch pages.
- **"4 – 7 Nov · report window":** a reminder of which days the accuracy results cover.
- **Coloured dot with a time** (for example "6 min ago"): how fresh the latest reading is. Green means under 30 minutes old, amber means under an hour and red means older than that. Red means the collectors may have stopped.
- **Small rain badge:** a short version of the rain light (explained below).
- **Sun or moon button:** switches between dark and light colours. The site remembers your choice.

**Bottom of the page:** credits for the data sources, a note that all times are Malaysian time (MYT), and a link to the project's code on GitHub.

**The small "i" buttons:** many cards have an **i** next to the title. Click or tap it for a one-line explanation of what the card means.

**When something goes wrong:** if the website can't reach its data, the card shows an error message and a **Try again** button instead of breaking the whole page. Grey boxes that shimmer mean a card is still loading.

---

## Page 1: Overview

*"What's happening now, and how good is the forecast?"* This is the front page and gives the big picture at a glance.

### Rain indicator (the rain light)
A traffic-light style circle showing the chance of rain in the next hour, according to Open-Meteo's forecast:

| Light | Meaning |
|---|---|
| Green, **Clear** | Under 30 % chance of rain |
| Amber, **Watch: rain possible** | 30 % to 60 % chance |
| Red, **Rain likely within 1 h** | 60 % chance or more |
| Grey, **No recent forecast** | The forecast is missing or more than 2 hours old, so it isn't trusted |

Underneath, it shows the exact chance for the **next hour** and the highest chance in the **next 3 hours**, and when that forecast was issued.

The light is Open-Meteo's forecast, not a prediction we made ourselves.

### Now · Seri Iskandar
The current weather in our town: a large temperature, an icon and words for the sky (for example "Partly cloudy"), plus **humidity**, **wind** speed and direction, air **pressure** and **rain** in the last 15 minutes.

The bottom line shows the **airport check** (the temperature at Ipoh airport and whether it's raining there) and the time of the latest update.

### The row of five summary tiles
Each tile is a quick headline. Click one to jump to the page with the details.

| Tile | What it tells you |
|---|---|
| **Report window: 3 days** | Our results cover three days of retrieved data, 4–7 Nov. |
| **Live since** | When live recording started (Sat 13:15) and how many live readings have been collected so far. |
| **Temp MAE · 1 day ahead** | How far off Best Match's temperature forecast was on average, when made one day ahead. Our result: **about 1.2 °C off**. The small text says "Bias −1.05", meaning it usually forecast about 1 °C **too cold**. |
| **Rain CSI · 1 day ahead** | A score from 0 to 1 for how well Best Match predicted *which hours* it would rain, one day ahead. 1 would be perfect. Ours: **0.44**. |
| **Best model (temp)** | The model with the smallest temperature error. Ours: **NOAA GFS**. |

### Next 24 hours
A chart of the newest Best Match forecast for the coming day. The **solid line** shows the temperature and the **bars** underneath show the chance of rain each hour. The **dashed line** is the same temperature corrected by our learning program. Hover over the chart to see the exact numbers for any hour.

The dashed line is still being checked. The learning programs were trained on forecasts made 1 to 7 days ahead, and this chart only covers the next 24 hours. The Live check card on Data Health shows whether the correction helps there.

If it says "Waiting for a current forecast", the hourly collector hasn't run recently.

---

## Page 2: Accuracy

*"Forecast accuracy."* This page holds the main results of the project. Every chart uses the report window, 4–7 Nov.

### The controls at the top
These change what all the charts below show:

- **Variable tabs:** pick what to compare: **Temperature, Humidity, Wind, Pressure** or **Rain**.
- **Truth:** what counts as "what actually happened":
  - **Open-Meteo analysis:** the computer estimate for our town, every 15 minutes.
  - **Ipoh airport (METAR):** real instrument readings, every hour, 26 km away. The airport only reports rain as yes or no, not how much fell.
- **Lead slider:** how far ahead the forecast was made, from **24 h** (1 day ahead) to **144 h** (6 days ahead). Forecasts usually get worse the further ahead they look.
- **Model buttons:** switch each forecast model on or off in the charts. "Best Match + ML" works for every weather type except Rain: for rain it only says yes or no for each hour, so it has no millimetres to draw.

Your choices are saved in the page's web address, so you can copy the link and a teammate will see exactly the same view.

### Forecast vs actual
The main chart. One line per model shows what it **forecast** for each hour, and a bold line shows what **actually happened**. Where the lines sit close together, the forecast was good. The shaded stripes are night-time.

Hover over any point to see the forecast, the actual value and the difference. The subtitle tells you how many hours are being compared.

### Error vs lead time
This chart shows how each model's error grows as the forecast looks further ahead. Each line is one model, and each point on it is one lead time. Bigger points mean more hours were compared. You can switch between three ways of measuring the error:

- **MAE:** how far off it was on average, whether too high or too low. Lower is better.
- **Bias:** whether it leans one way. Below zero means it usually forecast too low (for example too cold).
- **RMSE:** like MAE, but big misses count extra.

If you choose Rain together with the airport, this card explains that it can't show anything: the airport doesn't measure rain amounts.

### Model leaderboard: "Who wins for Seri Iskandar?"
A table ranking all the models over forecasts made 1 to 6 days ahead. Columns show the average miss for **temperature** (°C), **humidity** (%), **wind** (km/h) and **pressure** (hPa), and the **rain score** (CSI). The best value in each column has a gold **star**. Click a column heading to sort by it.

"Best Match + ML" has a number in every column. Its rain score comes from its yes-or-no answer for each hour. The note under the table explains that its wind forecast is flatter than real wind, so strong winds come out too weak.

### Next-day forecast
A day-by-day table: the forecast **highest** and **lowest temperature** and **total rain**, next to what was actually observed. **"Rain day correct"** says Yes if the forecast got right whether the day would be wet (1 mm of rain or more). Use the buttons to compare forecasts made **1, 2 or 3 days ahead**.

For example, the day-ahead forecast for Wed 4 Nov said a high of 31.2 °C and 10.2 mm of rain. The actual high was 32.8 °C with 20.4 mm of rain. So the forecast was a little too cool and expected half the rain, but it correctly called it a rainy day.

---

## Page 3: Data Health

*"Where the data came from, and whether collection is still running."* This page shows that the data is complete and trustworthy.

### The gold banner
Two short statements:
- **Report window: 3 days of retrieved data.** The exact dates and how many 15-minute readings were retrieved from archives.
- **Collecting live since …** When live recording began and how many readings have arrived out of how many were expected.

### Coverage: "Data received per day"
A grid with one column per day and one row per type of data (Open-Meteo readings, airport reports, Best Match forecasts). Each square shows the percentage of expected data that arrived that day: **100 %** means nothing is missing. Darker gold means more complete. A **B** means some of that day's data was retrieved from archives or filled in by the nightly repairer. Days inside the report window are in bold.

### Daily uptime: "Scheduled runs by outcome"
A bar chart showing, for each day, how many times a collector ran on its timer and how each run ended: **Success**, **Partial** (some data came in), **Failed** or **Missing** (it should have run but didn't). Use the buttons to pick which collector to look at.

Only automatic, timed runs count here, so running a collector by hand can't make the numbers look better. If it says "No scheduled runs yet", the timers haven't started.

### Live check: "Does the ML correction help on live forecasts?"
A table comparing Best Match with our corrected version on live forecasts, for each weather type, since live collection began (up to the last 30 days). It is split into forecasts for the next 24 hours and forecasts 1 to 7 days ahead. A **gold** number means the correction did better. The table fills up as forecast hours pass, so it starts empty.

### Run log
A list of the 50 most recent collector runs: when each started, which collector it was, whether it ran on the timer or by hand, whether it worked, and how many pieces of data it saved. The **run ↗** link opens the full record of that run on GitHub.

---

## The main results

All results are for the report window, 4–7 Nov, using forecasts made 1 to 6 days ahead. The numbers show how far off each temperature forecast was on average. **Smaller is better.**

| Model | Compared with Open-Meteo analysis | Compared with Ipoh airport |
|---|---|---|
| **NOAA GFS** | **0.83 °C** (best) | **0.93 °C** (best) |
| Best Match + ML (ours) | 0.87 °C | 1.12 °C |
| DWD ICON | 1.06 °C | 1.12 °C |
| Best Match | 1.30 °C | 1.54 °C |
| ECMWF IFS | 1.39 °C | 1.61 °C |

**What this means in everyday words:**
- **The American model (GFS) forecast temperature best for Seri Iskandar** in these three days, whichever "truth" we used.
- **Best Match, the forecast a typical app shows, tended to forecast too cold**, by about 1 °C.
- **Our learning program cut Best Match's temperature error by about a third** (from 1.30 to 0.87 °C). Against the real airport thermometer the improvement was still large (1.54 to 1.12 °C).
- **Rain is harder.** The best rain score was under 0.5 out of 1. Forecasts often caught that rain was coming, but got the exact hours wrong.
- **Three days is a short test.** These results describe this one wet spell in early November. A different week could rank the models differently.

### The other learning programs on the same three days
Each line compares Best Match with our corrected version. For the first three, smaller is better. For rain, the score runs from 0 to 1 and bigger is better.

| Weather type | Compared with Open-Meteo analysis | Compared with Ipoh airport |
|---|---|---|
| Humidity | 3.92 → **3.88 %** | 6.28 → **3.83 %** |
| Wind | 2.90 → **2.11 km/h** | 3.41 → **2.61 km/h** |
| Pressure | 0.69 → **0.53 hPa** | 1.07 → **0.72 hPa** |
| Rain score | 0.48 → 0.47 | 0.12 → 0.09 |

**In everyday words:**
- **Wind and pressure improved clearly**, by about a quarter, against both kinds of truth.
- **Humidity barely changed against Open-Meteo's estimate, but improved a lot against the airport's real instruments**, where Best Match was much too humid.
- **Rain didn't improve.** Our rain program did slightly worse than Best Match itself. Scientists find the same: hourly rain in the tropics is very hard to correct. We report it as it came out.

---

## Our learning programs ("Best Match + ML")

"ML" stands for **machine learning**: a program that learns patterns from past examples.

**What it does:** Best Match keeps making the same kinds of mistakes, for example running too cold at certain times of day. Our program studied **nine months of Best Match's past forecasts** for Seri Iskandar (October 2025 to June 2026), compared each one with what actually happened, and learned those habits. It then nudges each new forecast to correct for them.

**How we know it works:** we tested it twice on days it had never seen. First on July to October 2026, where it reduced the error from 1.30 to 0.99 °C. Then on the report window, 4–7 Nov (see the results above). Testing on unseen days matters: a program graded on examples it studied would look better than it really is.

**Four more programs:** after the temperature one, we added programs for **humidity**, **wind**, **air pressure** and **"will it rain this hour?"**. They learned from a full year of past forecasts (October 2025 to October 2026). Before trying them on the report window, we tested them on past months they hadn't seen: they cut the average error by about 15–20 % for humidity, wind and pressure. Rain improved only a little. Their results on 4–7 Nov are in "The main results" above. We also made an improved temperature program for everyday use. The report's temperature result still comes from the first one, so that number doesn't change.

**They run by themselves:** every hour, straight after the newest forecasts are saved, the programs correct them. Once a month they are retrained on the latest data. A new version only replaces the old one if it does better on the most recent month, so a bad retrain can't make things worse.

**Their limits:**
- **Rain didn't improve** on the report window. Hourly rain in the tropics is very hard to forecast, and correcting it is just as hard.
- **Wind comes out too flat.** The correction gets the average right but forecasts strong winds too weak.
- **Very humid hours get slightly worse**, because the correction pulls humidity down from near 100 %.
- **They were trained on forecasts 1 to 7 days ahead.** For the next 24 hours they are still being checked (see Live check on Data Health).
- **They learned from Open-Meteo's estimate of past weather**, not from instruments. That's why we also check them against the airport.

The research behind them, with its sources, is in [ML-research.md](ML-research.md).

---

## Features at a glance

- **Live weather** for Seri Iskandar, updated every 10 minutes.
- **Rain light** showing the chance of rain in the next hour.
- **24-hour forecast** chart of temperature and rain chance.
- **Comparison of four forecast models** against what actually happened.
- **Two kinds of "truth"**: a computer estimate for the town, and real airport instruments.
- **Five weather types**: temperature, humidity, wind, pressure and rain.
- **Lead-time slider** to see how accuracy drops further ahead.
- **Model leaderboard** with the best value in each column starred.
- **Next-day table** for daily high, low and rain, including whether the rainy day was called correctly.
- **Our own learning programs** that correct temperature, humidity, wind and pressure and forecast rain hours, run every hour and retrained monthly.
- **Live check** of whether the corrections help on new forecasts.
- **Data health page** proving the data is complete and showing whether collection is still running.
- **Runs by itself** on a timer, with a nightly repair of any gaps.
- **Honest labels**: retrieved data is always marked as retrieved.
- **Shareable views**: copy the web address to share exactly what you're looking at.
- **Dark and light themes**, remembered between visits.
- **Works on phones, tablets and computers**, and can be used with a keyboard alone.
- **Built-in help**: the "i" buttons explain each card.
- **Free to run**: it uses only free services and needs no hardware.

---

## Words you'll see

| Word | Plain meaning |
|---|---|
| **Forecast model** | A large computer program run by a weather agency that predicts the weather. |
| **Actual / truth** | What the weather really did, used to mark the forecasts. |
| **Open-Meteo analysis** | Open-Meteo's best estimate of the weather that happened in our town, every 15 minutes. |
| **METAR** | The standard hourly weather report from an airport. Ours is from Ipoh (code WMKI). |
| **Lead time** | How far ahead a forecast was made. "24 h" means a day ahead. |
| **MAE** | Average miss: how far off the forecast was on average, ignoring whether it was too high or too low. Smaller is better. |
| **Bias** | Which way the forecast leans. Negative means too low, for example too cold. |
| **RMSE** | Like MAE, but big misses count extra. |
| **CSI** | A rain score from 0 to 1: how well the forecast picked the hours it rained without raising false alarms. 1 is perfect. |
| **n** | How many hours were compared. Bigger means a more reliable number. |
| **Report window** | The three days our results cover: Wed 4 Nov 00:00 to Sat 7 Nov 00:00. |
| **Retrieved** | Fetched from public archives after the event, rather than recorded as it happened. |
| **Live** | Recorded as it happened, from Sat 7 Nov onwards. |
| **Uptime** | How often the collectors ran when they were supposed to. |
| **Coverage** | How much of the expected data actually arrived. |
| **MYT** | Malaysia Time. All times on the site use it. |
| **hPa** | The unit for air pressure. Around 1010 is normal here. |

---

## Common questions

**Is this real weather data?**
Yes. It comes from Open-Meteo and the Ipoh airport station. The 4–7 Nov data was fetched from their archives after those days, which is why we call it "retrieved".

**Why no sensors of our own?**
Reliable sensors are costly, and a single cheap sensor can be less accurate than the free public sources. Comparing forecasts doesn't need our own hardware.

**Why does the airport sometimes disagree with the town's numbers?**
The airport is about 26 km away and measures at one spot. The town's numbers are a computer estimate for a wider area. Small differences are normal.

**Why can't I see "Best Match + ML" for rain?**
For rain our learning program answers yes or no for each hour, instead of forecasting millimetres. You can see how well it did in the rain score column of the leaderboard.

**Why is a chart empty or showing an error?**
Either that combination has no data (for example rain amounts at the airport, which it doesn't record), or the site couldn't reach its data for a moment. Press **Try again**. If the freshness dot in the top bar is red, the collectors may have stopped.

**Which forecast should I trust for Seri Iskandar?**
For temperature in this test, NOAA GFS was the most accurate, and our corrected Best Match came close. For rain, no model was clearly better than the others. Remember the test covered only three days.
