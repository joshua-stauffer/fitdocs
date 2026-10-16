---
title: "Recovery"
type: "recovery"
generator: "fitdocs"
recovery_version: 1
baselines_version: 1
as_of: "2025-05-01"
window_start: "2025-02-01"
window_end: "2025-05-01"
---

<!-- fitdocs:generated: everything outside the notes/workout/load regions is replaced on regeneration -- see this directory's AGENTS.md -->

# Recovery
Data source: Garmin

As of 2025-05-01. Window: 2025-02-01 to 2025-05-01. Each signal is shown against the athlete's own baseline, computed separately for every source. This page describes the data and draws no conclusion from it.

## Fitness, Fatigue and Form

No workout page records a training load, so fitness, fatigue and form are not shown.

## HRV (SDNN)

![HRV (SDNN) chart](assets/recovery-hrv-sdnn.svg)

Latest: 2025-04-29, 72 ms (watch0).

7-day mean: 67 ms.

Normal range: 39 ms to 49 ms, from 60 of the 60 days before.

- 2025-04-24 to 2025-05-01: above (watch0)

Sources shown: watch0 (origins garmin) on 63 days.

## HRV (rMSSD)

![HRV (rMSSD) chart](assets/recovery-hrv-rmssd.svg)

Latest: 2025-04-29, 193 ms (watch1).

7-day mean: 181 ms.

Normal range: 105 ms to 133 ms, from 60 of the 60 days before.

- 2025-04-24 to 2025-05-01: above (watch1)

Sources shown: watch1 (origins garmin) on 63 days.

## Resting HR

![Resting HR chart](assets/recovery-resting-hr.svg)

Latest: 2025-04-29, 108 bpm (watch2).

7-day mean: 106 bpm.

Normal range: 58 bpm to 72 bpm, from 60 of the 60 days before.

- 2025-04-23 to 2025-05-01: above (watch2)

Sources shown: watch2 (origins garmin) on 63 days.

## Sleep

![Sleep chart](assets/recovery-sleep.svg)

| Signal | 2025-04-29 | 7-day mean | 60-day mean |
| --- | --- | --- | --- |
| Sleep | 12:50:46 | 12:45:35 | 7:45:03 |
| Deep sleep | 38:18 | 36:59 | 23:38 |
| Light sleep | 4:36:34 | 4:32:41 | 2:47:53 |
| REM sleep | 2:06:10 | 2:03:53 | 1:16:50 |
| Awake in sleep | 5:06 | 4:35 | 3:19 |
| Sleeping HR | 178 bpm | 161 bpm | 115 bpm |

## Other Signals

![Other signals chart](assets/recovery-other.svg)

Shown as recorded, one panel per metric and source, with no baseline.

## Coverage

| Signal | Source | Days with a value (of 90) |
| --- | --- | --- |
| HRV (SDNN) | watch0 | 61 |
| HRV (rMSSD) | watch1 | 61 |
| Resting HR | watch2 | 61 |
| Sleep | watch3 | 61 |
| Deep sleep | watch3 | 61 |
| Light sleep | watch3 | 61 |
| REM sleep | watch3 | 61 |
| Awake in sleep | watch3 | 61 |
| Sleeping HR | watch3 | 61 |
| Steps | pedometer | 1 |
| Mood (rating) | rating | 1 |

## Method

- ROLLING\_DAYS: 7 — Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M (2013), Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring. Sports Med. 43(9):773–781. doi:10.1007/s40279-013-0071-8, §3, pp.774–775; §5, pp.779–780; see also Plews DJ, Laursen PB, Kilding AE, Buchheit M (2013), Evaluating training adaptation with heart-rate measures: a methodological comparison. Int J Sports Physiol Perform. 8(6):688–691. doi:10.1123/ijspp.8.6.688, Experimental Protocol and Statistical Analysis, p.689; Discussion, p.690, Statistical Analysis, p.689 (agrees; primary_text)
- MIN\_ROLLING\_VALUES: 3 — Plews DJ, Laursen PB, Le Meur Y, Hausswirth C, Kilding AE, Buchheit M (2014), Monitoring training with heart-rate variability: how much compliance is needed for valid assessment? Int J Sports Physiol Perform. 9(5):783–790. doi:10.1123/IJSPP.2013-0455, abstract, p.783; Practical Applications and Conclusions, p.789; Departure: Plews 2014, Practical Applications and Conclusions p.789: three in trained triathletes, approximately five in recreational athletes; fitdocs Require three present days for each of nine methods (One explicit missingness rule across metrics; no claim that three establishes validity for every population/signal)
- BASELINE\_DAYS: 60 — fitdocs's choice: maintainer's 2026-10-12 decision for a longer personal baseline; Departure: Vesterinen 2016, Methods “HRV guided training”, paragraphs 2–3: four-week reference periodically updated; fitdocs Use D−60 through D−1 (Approved personal as-of baseline excludes the judged day and implements the maintainer's longer-window decision)
- MIN\_BASELINE\_VALUES: 30 — fitdocs's choice: at least half the 60-day window before estimating variation
- RANGE\_SD\_MULTIPLE: 0.5 — Vesterinen V, Nummela A, Heikura I, Laine T, Hynynen E, Botella J, Häkkinen K (2016), Individual endurance training prescription with heart rate variability. Med Sci Sports Exerc. 48(7):1347–1354. doi:10.1249/MSS.0000000000000910, Methods, “HRV guided training”, paragraph 2; Discussion, “Methodological issues to use HRV in training prescription”; Departure: Vesterinen 2016, Methods “HRV guided training”, paragraphs 1–3: raw RMSSD, four weeks, training prescription; fitdocs Use 0.5 SD for log HRV and linear resting HR over preceding 60 days; descriptive marking only (Preserve approved transparent windows and separate metrics while keeping the display descriptive)
- HRV is averaged as the natural log of its values and shown back in ms. — Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M (2013), Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring. Sports Med. 43(9):773–781. doi:10.1007/s40279-013-0071-8, §3, pp.774–775; §5, pp.779–780; see also Plews DJ, Laursen PB, Kilding AE, Buchheit M (2013), Evaluating training adaptation with heart-rate measures: a methodological comparison. Int J Sports Physiol Perform. 8(6):688–691. doi:10.1123/ijspp.8.6.688, Experimental Protocol and Statistical Analysis, p.689; Discussion, p.690, Experimental Protocol, p.689 (agrees; primary_text)
- The same method is applied to SDNN, never mixed with rMSSD. — fitdocs's choice: display each HRV definition separately with one transparent method; Departure: Plews 2013 Sports Med, §3 pp.774–775: preferred index is ln rMSSD; fitdocs Apply log averaging/range independently to SDNN (Show each platform's HRV definition separately without unsupported SDNN/rMSSD conversion)
- Resting HR uses the same windows and range on its own values (no log). — fitdocs's choice: one descriptive rolling/baseline comparison on resting HR's own linear values; see also Plews DJ, Laursen PB, Kilding AE, Buchheit M (2013), Evaluating training adaptation with heart-rate measures: a methodological comparison. Int J Sports Physiol Perform. 8(6):688–691. doi:10.1123/ijspp.8.6.688, Experimental Protocol and Statistical Analysis, p.689; Discussion, p.690, Discussion, p.690 (omits; primary_text): supports weekly HR averaging but not fitdocs's full range method; Departure: Vesterinen 2016, Methods “HRV guided training”: range applied to RMSSD; Plews 2013 IJSPP Discussion p.690 supports weekly HR averaging; fitdocs Apply the approved windows/range to linear resting HR values (A single explicit descriptive comparison rule; no published claim of this exact resting-HR range)
- A day is marked when its seven-day mean lies outside the normal range. — Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M (2013), Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring. Sports Med. 43(9):773–781. doi:10.1007/s40279-013-0071-8, Fig.4, p.779; §5, pp.779–780; see also Vesterinen V, Nummela A, Heikura I, Laine T, Hynynen E, Botella J, Häkkinen K (2016), Individual endurance training prescription with heart rate variability. Med Sci Sports Exerc. 48(7):1347–1354. doi:10.1249/MSS.0000000000000910, Methods, “HRV guided training”, paragraph 2; Discussion, “Methodological issues to use HRV in training prescription”, Methods, “HRV guided training”, paragraphs 1–3 (agrees; primary_text): supports comparison of seven-day averages, not fitdocs's log/60-day descriptive method; Departure: Plews 2013 Sports Med, Fig.4 p.779: weekly ln rMSSD comparison with individual SWC and confidence intervals; fitdocs Mark a seven-day mean outside either bound, without confidence intervals or training instructions (Describe the athlete's own figures rather than infer performance, health or training decisions)
- The SD is the sample SD (n − 1) of the baseline days. — fitdocs's choice: n−1 sample estimate of baseline-day variation
- Sleep signals get a seven-day mean and a 60-day mean, no range. — fitdocs's choice: descriptive recent and longer sleep averages, no unsupported normal range
- Every computation uses one source and one metric. — fitdocs's choice: maintainer's 2026-10-12 decision because platform definitions differ
- The shown source is the day's canonical source, carried for at most six days; only the source identifier is carried, never the value. — fitdocs's choice: use canonical source and bridge only gaps within the seven-day rolling window, carrying the source identifier, never the value

## References

- Plews DJ, Laursen PB, Kilding AE, Buchheit M (2013), Evaluating training adaptation with heart-rate measures: a methodological comparison. Int J Sports Physiol Perform. 8(6):688–691. doi:10.1123/ijspp.8.6.688, Experimental Protocol and Statistical Analysis, p.689; Discussion, p.690
- Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M (2013), Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring. Sports Med. 43(9):773–781. doi:10.1007/s40279-013-0071-8, §3, pp.774–775; §5, pp.779–780
- Plews DJ, Laursen PB, Le Meur Y, Hausswirth C, Kilding AE, Buchheit M (2014), Monitoring training with heart-rate variability: how much compliance is needed for valid assessment? Int J Sports Physiol Perform. 9(5):783–790. doi:10.1123/IJSPP.2013-0455, abstract, p.783; Practical Applications and Conclusions, p.789
- Vesterinen V, Nummela A, Heikura I, Laine T, Hynynen E, Botella J, Häkkinen K (2016), Individual endurance training prescription with heart rate variability. Med Sci Sports Exerc. 48(7):1347–1354. doi:10.1249/MSS.0000000000000910, Methods, “HRV guided training”, paragraph 2; Discussion, “Methodological issues to use HRV in training prescription”
