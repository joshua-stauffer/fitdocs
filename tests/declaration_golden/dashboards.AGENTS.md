<!-- fitdocs:generated: this file is maintained by fitdocs and rewritten whenever its content differs from what fitdocs would write -->
# AGENTS.md -- Dashboards

The pages in `dashboards/` belong to the athlete; fitdocs writes only the chart regions inside them and the files in `dashboards/assets/`.

A page declares a chart in a hidden `<!-- fitdocs:chart ... -->` directive written by the athlete or their assistant; directly below it, fitdocs maintains a region between `<!-- fitdocs:begin:chart:<id> -->` and `<!-- fitdocs:end:chart:<id> -->` and rewrites only the bytes between those markers, after a successful index refresh and when `fitdocs dashboard refresh` runs. Edit the prose, frontmatter and directives freely; do not edit inside a chart region.

Frozen charts are drawn from snapshot files in `dashboards/assets/`, which fitdocs never modifies or deletes; the chart images there are rewritten as needed.

Check a page with `fitdocs dashboard check`; the packaged `fitdocs-dashboards` skill (`fitdocs skill fitdocs-dashboards`) explains the directive.

## Ownership

Owner: the athlete (pages); fitdocs (chart regions and dashboards/assets/).
Ownership contract version: `12`.
Published ownership contract: https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md
