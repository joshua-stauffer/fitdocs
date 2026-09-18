---
id: 2026-09-18-setting-coverage-range-text-unpinned-load-channels
title: load-channels' own _setting_coverage range-error text is unpinned, though its byte-identical sibling in activity-qa-flags now is
status: open
importance: medium
importance_why: Req 6.5's four-part error-message contract (file, key, value, admissible range) was the exact defect class that cost activity-qa-flags task 1.3 a review round; the identical wording in load-channels' own original helper has the same gap and nothing currently catches it.
effort: S
kind: gap
area: load-channels, src/fitdocs/load/settings.py, tests/load/test_settings.py
created: 2026-09-18
surfaced_by: /kiro-impl activity-qa-flags task 1.3 review (round 1 rejection led to discovering the sibling gap), re-confirmed at feature-level validation
pinned_at: d26b682
resume_command: "do: add an assertion pinning the admissible-range text in _setting_coverage's LoadSettingsError message (src/fitdocs/load/settings.py:296), mirroring the pattern already added for _setting_flag_unit_float in tests/load/test_settings.py (search test_unit_range_flag_rejects_zero)"
context:
  - src/fitdocs/load/settings.py
  - tests/load/test_settings.py
---

## What

`src/fitdocs/load/settings.py:296` (`_setting_coverage`, load-channels' own
helper, projecting `[load.sufficiency]`) builds an error message containing
the literal text `"above zero and at or below one"` when a coverage setting
is out of range. No test in `tests/load/test_settings.py` asserts this text
appears in the raised error -- only that the error is raised at all.

The byte-identical phrase now also appears in `_setting_flag_unit_float`
(`src/fitdocs/load/settings.py:488`, `activity-qa-flags` task 1.3), and
*that* copy **is** pinned (`tests/load/test_settings.py:1230,1247`,
`test_unit_range_flag_rejects_zero`/`_rejects_above_one`) -- because task
1.3's own review caught the identical gap on its own new code and fixed it
there. The older, load-channels-owned copy was never revisited.

## Why it matters

Requirement 6.5 (this spec's shape of it; load-channels' own settings
requirements carry the equivalent obligation) requires an out-of-range
configuration error to name the file, the key, the offending value, **and
the admissible range**. Stripping the range text from `_setting_coverage`'s
message today leaves the whole suite green -- the same defect class that
took activity-qa-flags task 1.3 a full review round to close on its own
validators.

## Evidence

Verified directly at `d26b682`:

```
$ grep -n "above zero and at or below one" src/fitdocs/load/settings.py
296:            f"above zero and at or below one, got {value!r} "
488:            f"above zero and at or below one, got {value!r} "

$ grep -n "above zero and at or below one" tests/load/test_settings.py
1230:    assert "above zero and at or below one" in body  # Req 6.5: the admissible range
1247:    assert "above zero and at or below one" in body  # Req 6.5: the admissible range
```

Both pinned assertions are inside `test_unit_range_flag_rejects_zero` /
`test_unit_range_flag_rejects_above_one` -- both exercise
`_setting_flag_unit_float` (line 488's sibling), not `_setting_coverage`
(line 296). No test in the file asserts on `_setting_coverage`'s own error
message content; `grep -n "def test.*coverage.*reject\|min_stream_coverage"`
shows only value-mapping tests for that setting, none asserting rejection
message text.

## How to pick it up

1. Find `_setting_coverage` in `src/fitdocs/load/settings.py` and its
   existing rejection tests in `tests/load/test_settings.py` (search
   `min_stream_coverage`).
2. Add a rejection-message-content assertion mirroring
   `test_unit_range_flag_rejects_zero`'s pattern: construct an out-of-range
   `min_stream_coverage` (or one of its three per-channel overrides, which
   share the same helper), catch the raised `LoadSettingsError`, assert the
   range text appears in its message.
3. Verify by stripping the range clause from `_setting_coverage`'s f-string
   and confirming the new assertion reds.

Done looks like: `_setting_coverage`'s admissible-range text is pinned the
same way its newer sibling's already is.

## Open questions

None.
