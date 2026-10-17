# Recovery

## Run the command

Run it after a drain that archived wellness or changed the wellness series,
or when you want a fresh recovery page.

```sh
fitdocs recovery
```

Data-root resolution is `--out` > `FITDOCS_DATA` > `.fitdocs/data-root`.
Use `fitdocs recovery --out /path/to/wiki --methodology threshold` to select
a root and load methodology explicitly.

The command reads the normalized wellness series and workout documents;
it writes `recovery/recovery.md` and relative SVG images in `recovery/assets/`.
The report prints `As of`, `Window`, `Methodology`, then each relative path
with `written`, `unchanged`, `removed`, `foreign` or `failed`.
An empty wellness series writes nothing; an unreadable series reports the
error and asks you to run `fitdocs sync` or `fitdocs regen`.

## Read the page

The as-of day is the latest day in the wellness series, not today's date;
the display window is 90 calendar days including that day.

### Fitness, Fatigue and Form

Uses the same computation as `fitdocs history`, under the selected load
methodology, from loads already recorded on workout pages.
Missing load coverage stays absent, including weeks suppressed for low
coverage; without recorded load, the section explains why no chart is shown.

### HRV (SDNN), HRV (rMSSD) and Resting HR

Each available signal has its own section: a chart, latest value and source,
7-day mean, normal range, above/below runs, source changes and sources shown.

### Sleep

Shows total sleep and its 7-day mean in the chart, with no normal range.
The table uses the latest shown total-sleep night and that source: total,
deep, light, REM, awake and sleep HR appear only when present on that night,
with 7-day and 60-day means where formed. A caption names the source and the
night the table shows, and after the table the section states each source
change and each source shown with its recorded origins, as the signal
sections do.

### Other Signals

Shows recorded values in independent panels per metric and source, without
a baseline; pairs beyond the panel limit are named as not charted. One
`Sources shown` line names each charted panel's source with its recorded
origins; panels have no baseline, so no source changes are stated.

### Coverage

Counts days with a value in the display window for each metric and source,
and lists absent HRV, resting-HR and total-sleep signals.

### Method and References

Method on the generated page is the reference for constants, governing
citations, corroboration and departures; References lists the cited works.

## Method

| Constant | Value |
| --- | --- |
| `ROLLING_DAYS` | 7 |
| `MIN_ROLLING_VALUES` | 3 |
| `BASELINE_DAYS` | 60 |
| `MIN_BASELINE_VALUES` | 30 |
| `RANGE_SD_MULTIPLE` | 0.5 |

For a day D, the rolling window is D−6 through D, including D; the baseline
is D−60 through D−1, excluding D.
A rolling mean needs at least 3 present days; a baseline mean and sample SD
need at least 30 present days.

HRV (SDNN and rMSSD separately) uses natural-log means and mean ± 0.5 sample
SD on the log scale, exponentiated back to ms.
Resting HR uses linear means and mean ± 0.5 sample SD in bpm; sample SD uses
n − 1 baseline days in its denominator.
Sleep signals use linear 7-day and 60-day means, without a range.
A day is marked only when its 7-day mean is strictly below or above the
bounds, not because its single daily value is outside them.

The page cites Plews et al. (2013) for log-HRV averaging, Plews et al. (2014)
for the weekly minimum and Vesterinen et al. (2016) for the range multiplier,
with application differences stated as departures.
The preceding-60-day baseline, 30-value minimum and sample-SD denominator
are fitdocs choices; the generated Method explains the cited work's scope
and each departure rather than claiming one published method covers the
whole page.

## Sources

Each rolling mean and baseline uses one metric and one source; values from different
sources are not pooled and SDNN is not converted to or mixed with rMSSD.
The shown source is that metric's canonical source on D; if absent, use its
most recent canonical source from D−1 through D−6, otherwise show no source.
Only the source identifier is carried, never yesterday's value; a source
change immediately selects the new source's own means and range. A change is
measured against the latest earlier day of the window that had a shown source,
so a change after a gap is stated and a source that returns after a gap is not
a change.

## Missing values

Absent daily values stay absent, not zero; charts leave gaps.
Signal sections say `not shown` and give the present-day count, window
length and required minimum when a mean or range cannot form.
An unavailable signal section is omitted and named in Coverage; a formed
mean or range can still be shown on a day with no daily value.

## Garmin attribution

When any wellness value used by a printed or charted figure records Garmin
origin, an attribution line appears directly beneath `# Recovery`.
It reads `Data source: Garmin` when all such values have Garmin origin, or
`Data sources: Garmin and other sources` when origins are mixed or include
an unrecorded origin.
With no Garmin origin among values actually used, there is no attribution
line; an unformed statistic uses no values for attribution.
Chart images carry no Garmin attribution stamp.

## Descriptive limits

The page makes no readiness score, verdict, health or performance inference,
training recommendation or forecast; normal range describes the athlete's
own data, not a clinical threshold.
It runs offline as a standalone command, not as part of sync, regen, load
or history, and does not change workout pages or wellness inputs.

## Dashboard authors

The chart kind is `reference-band`: bind `x` and `y`, optionally paired
`low`/`high`, `mid`, `segment` and boolean `flag` channels.
It draws daily points, a reference band and an optional mean line; absent
daily values omit points, absent bounds break the band, absent mid values
break the mean line, and segment changes break both band and line.
Flags are caller-supplied markers, not a calculation of readiness or a
verdict; see [Dashboards](dashboards.md) for directive syntax.
