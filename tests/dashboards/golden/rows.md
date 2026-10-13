Prose before the rows chart.
<!-- fitdocs:chart
id: listed
kind: bar
mode: relative
title: Title of listed
window: last 3 weeks
show_rows: true
sql: |
  select listed
channels: 
  x: day
  y: distance_km
-->
<!-- fitdocs:begin:chart:listed -->
![Title of listed](assets/rows/listed.svg)

*last 3 weeks · through 2031-03-17*

| day | distance (km) |
| --- | ---: |
| 2031-03-17 | 40.5 |
| 2031-03-03 | 31.2 |
| 2031-03-10 | 52.0 |

<!-- fitdocs:end:chart:listed -->
Prose after.
