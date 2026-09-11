# performance-benchmarks sources — what was read and what was not

This document restates `src/fitdocs/performance/sources.py`'s classification
table in prose, following the shape of
`docs/reference/banister-trimp-primary-sources.md`: what this project has
actually read, what it has not, and exactly what would unblock the one
constant this feature cannot ship.

> **Licensing.** No source text lives in this repo. This document records
> bibliographic facts, verification status and what a future session must do
> to resolve each open item — not the sources' own copyrighted text.

## 1. The six citations

| Key | Work | Read by this project? | Status |
|-----|------|------------------------|--------|
| `riegel_1981` | Riegel, P.S. (1981). "Athletic Records and Human Endurance." *American Scientist* 69(3):285–290. | **No** — JSTOR-only. | `SECONDARY_ATTESTATION` (tracked, see §3) |
| `drake_2024` | Drake, K.M., Finke, A.J., Ferguson, R.A. (2024). *European Journal of Applied Physiology* 124:507–526. | No. | `SECONDARY_ATTESTATION` (corroborator only; tracked, see §3) |
| `mcgehee_2005` | McGehee, J.C., Tanner, C.J., Houmard, J.A. (2005). *Journal of Strength and Conditioning Research* 19(3):553–558. | No. | `SECONDARY_ATTESTATION` (corroborator only; tracked, see §3) |
| `dumke_2006` | Dumke, C.L., et al. (2006). *Journal of Strength and Conditioning Research* 20(3):601–607. | No. | `SECONDARY_ATTESTATION` (corroborator only; tracked, see §3) |
| `performance_coggan_2003` | Coggan, A.R. (2003). "Training and racing using a power meter: an introduction" (USA Cycling coaching-education chapter). | **Yes** — this session fetched the manuscript itself (the URL carried in `COGGAN_TSS`'s own note, `src/fitdocs/load/channels/sources.py`) and read it. | `PRIMARY_TEXT` |
| `borszcz_2018` | Borszcz, F.K., et al. (2018). *International Journal of Sports Medicine* 39(10):737–742. | No. | `SECONDARY_ATTESTATION` (corroborator only; tracked, see §3) |

Of the six, only Coggan (2003) rests on primary text this project has itself
opened. The other five are recorded honestly as not read, each carrying its
own bibliographic description rather than a fabricated page or quotation, and
all five (the governing `riegel_1981` plus the four corroborators) are
tracked as non-silent exceptions in `BLOCKED_CITATIONS` (§3) — the design
names that set to cover every `SECONDARY_ATTESTATION` citation the module
carries, not only those that govern a constant.

## 2. What governs each constant

| Constant | Value | Governing record | Corroborators |
|----------|-------|-------------------|----------------|
| `RIEGEL_EXPONENT` | 1.06 | `riegel_1981` | `drake_2024` (agrees) |
| `RIEGEL_MIN_DURATION_S` | 210.0 s | `riegel_1981` | — |
| `RIEGEL_MAX_DURATION_S` | 13800.0 s | `riegel_1981` | — |
| `RIEGEL_SOLVE_TARGET_S` | 3600.0 s | fitdocs choice (`riegel_solve_target_choice`) | — |
| `LTHR_MIN_DURATION_S` | 1500.0 s | fitdocs choice (`lthr_duration_window_choice`) | `mcgehee_2005`, `dumke_2006` (omit) |
| `LTHR_MAX_DURATION_S` | 4500.0 s | fitdocs choice (`lthr_duration_window_choice`) | `mcgehee_2005`, `dumke_2006` (omit) |
| `EFFORT_SPAN_TOLERANCE` | 0.05 (5%) | fitdocs choice (`effort_span_tolerance_choice`) | — |
| `FTP_DEFINITION_MIN_DURATION_S` | 3000.0 s | `performance_coggan_2003` | `borszcz_2018` (omits) |
| `FTP_DEFINITION_MAX_DURATION_S` | 4200.0 s | `performance_coggan_2003` | `borszcz_2018` (omits) |
| `FTP_SHORT_PROTOCOL_FLOOR_S` | 900.0 s | fitdocs choice (`ftp_short_protocol_floor_choice`) | — |
| `ROUNDING_HALF_OFFSET` | 0.5 | fitdocs choice (`rounding_half_offset_choice`) | — |

Only `riegel_1981` and `performance_coggan_2003` govern a constant among the
six citations; the other four (`drake_2024`, `mcgehee_2005`, `dumke_2006`,
`borszcz_2018`) appear only as corroborators, never as a second governing
source for any value (Req 8.6).

The Coggan (2003) record in `fitdocs.performance.sources` deliberately
carries its own locator — §2 "Power-based training levels", the run-in
heading "Determination of LT power:", printed page 4 (PDF page 5) of the
revised 25 March 2003 edition, where the manuscript states "the easiest and
most direct way of estimating a rider's functional threshold power is
therefore to simply measure their average power during a ~40 km (50-70 min)
TT" — rather than the TSS section `COGGAN_TSS` in
`fitdocs.load.channels.sources` cites. No "Threshold power" subheading exists
in this manuscript. The same paragraph also states a distinct 20 km
time-trial correction factor for a shortened protocol; that factor is
**not** the 20-minute-test scaling factor Allen & Coggan's later book
defines (§4) -- a distinct 20 km time-trial correction factor, not the
20-minute factor -- and no number for it is recorded here. Both records agree on authors, year and
work, because they name the same manuscript; a test
(`tests/performance/test_sources.py::
test_coggan_record_agrees_with_the_shipped_channels_layer_record`) pins that
agreement so the two descriptions of one work cannot silently drift apart
(Req 8.8).

## 3. The tracked secondary-attestation exceptions

`BLOCKED_CITATIONS` names every citation this module carries under
`SECONDARY_ATTESTATION` — governing or corroborator — as a tracked,
non-silent exception (Req 8.4): today all five non-Coggan citations,
`riegel_1981`, `drake_2024`, `mcgehee_2005`, `dumke_2006` and `borszcz_2018`.

`riegel_1981` governs three constants (`RIEGEL_EXPONENT`,
`RIEGEL_MIN_DURATION_S`, `RIEGEL_MAX_DURATION_S`) and carries
`SECONDARY_ATTESTATION`. Riegel's 1981 *American Scientist* paper is
JSTOR-only; no session that produced this package has crossed the paywall.
The 1.06 running exponent is instead attested through Drake et al. (2024), a
peer-reviewed work that attests the same exponent — a
corroborator, never treated as a second governing source. The stated
validity window (3.5 minutes to 3.83 hours; 210 s to 13800 s) is not
attested by Drake — Drake corroborates the exponent only — but by this
feature's own discovery viability check (2026-09-09), as recorded in this
spec's `brief.md` ("valid for efforts of 3.5–230 minutes"); `research.md`
documents the same viability check without restating the window's own
numbers.

**What would resolve `riegel_1981`:** obtaining the 1981 *American
Scientist* text itself (69(3):285–290) and reading its own stated exponent,
validity window and any further constants it defines, then re-pointing
`RIEGEL_1981`'s `verification` to `PRIMARY_TEXT` with a locator naming the
page(s) actually read.

**What would resolve the four corroborators:**
- `drake_2024` — obtaining *European Journal of Applied Physiology*
  124:507–526 and reading its own stated review of Riegel's exponent.
- `mcgehee_2005` — obtaining *Journal of Strength and Conditioning Research*
  19(3):553–558 and reading its own stated protocol duration and heart-rate
  comparison method.
- `dumke_2006` — obtaining *Journal of Strength and Conditioning Research*
  20(3):601–607 and reading its own stated protocol duration and heart-rate
  comparison method.
- `borszcz_2018` — obtaining *International Journal of Sports Medicine*
  39(10):737–742 and reading its own stated limits of agreement between the
  20-minute-test estimate and directly measured FTP.

## 4. The one pending constant

The Allen & Coggan "20-minute test" power-scaling factor — used by some
FTP-estimation protocols to convert a 20-minute mean power into an estimated
one-hour functional threshold power — is recorded in `PENDING_CONSTANTS` and
**may not be written anywhere in this package**. Its suspected source is
Allen, H. & Coggan, A.R., *Training and Racing with a Power Meter*, 2nd ed.
(VeloPress, 2010), a book this project has never obtained. Coggan's own 2003
manuscript (the primary text this project *has* read, cited above as
`performance_coggan_2003`) defines the threshold-power window this feature
does ship, but does not itself state a 20-minute-test scaling factor.

No numeric value for this factor appears anywhere in
`src/fitdocs/performance/` — not as a literal, not inside a note, not inside
a docstring — enforced by
`tests/performance/test_sources.py::
test_the_number_0_95_appears_nowhere_in_the_performance_package` and
`test_no_pending_value_phrasing_appears_on_any_pending_constant_field`.

Borszcz et al. (2018) is recorded as a corroborator of the 20-minute
protocol's *measured uncertainty* (limits of agreement of roughly
±40 W against a directly measured FTP) — the figure Req 4.8 asks a derived
FTP entry's provenance to carry alongside the value it produced — but it does
not state the factor's own locator and does not unblock it.

**What would resolve it:** obtaining the Allen & Coggan book and reading the
chapter defining the 20-minute test, then recording its own stated factor
together with the page it appears on, adding a governing citation for it,
and removing its entry from `PENDING_CONSTANTS`.

**Consequence today:** every `DerivationMethod` in `BLOCKED_METHODS` —
today exactly `TWENTY_MINUTE_POWER_FACTOR` — declines by name (Req 8.5),
while every other method this feature defines (the Riegel race-equivalence
threshold pace, the sustained-effort mean-heart-rate LTHR, and the
whole-effort mean-power FTP inside the definitional window) continues to
work unaffected.

## 5. The departure not implemented

A coaching protocol for estimating LTHR — discard the first 10 minutes of a
30-minute time trial and average heart rate over the remaining 20 — is
**not** implemented. It is recorded as a `Departure` in
`fitdocs.performance.sources.DEPARTURES` rather than adopted, because the
10-minute discard is not sourced to any citation this module carries with a
verified locator, and both McGehee et al. (2005) and Dumke et al. (2006) —
the two validated protocols this feature's own duration window is informed
by — used the whole-effort average rather than a partial-discard window.
fitdocs computes the time-weighted mean heart rate over the whole recorded
effort (Req 3.2), never over a selected portion of it.
