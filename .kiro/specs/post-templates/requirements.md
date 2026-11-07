# Requirements Document

## Project Description (Input)
Post templates whose variables are SQL over the analytics index. The athlete writes one template file: the post's text in the existing `{name}` grammar plus one SQL definition per variable, bound to `$as_of` (the workout's recorded start) and `$page_key`. After `fitdocs sync`, each new page's user-owned `post` region holds the finished text, written once by a fill pass that runs after the index refresh. `fitdocs publish` sends that text through its existing path and stays offline. `fitdocs regen` carries the text byte for byte; re-querying happens only on request. Text the athlete wrote or edited is never overwritten. Discovery context, decisions and viability evidence: `brief.md`.

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
