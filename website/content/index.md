---
title: Why fitdocs?
description: Turn .fit files into markdown workout pages you own.
section: Home
order: 0

hero_title: fitdocs
hero_tagline: A training log for AI-assisted analysis and planning.
---

Fitdocs takes your workout files and builds a training log and an analytics database, in a format LLMs read well. It runs locally on your computer, and works with any AI agent without additional setup. Use it as a standalone training log, or integrate it into a markdown knowledge base you already keep, like an Obsidian vault, a git-tracked wiki, or an LLM-maintained "second brain." All major fitness wearables output .fit files, so you can connect your fitness data from Garmin, Coros, Polar, Stryd, Apple, and more.

```sh
uv tool install fitdocs
```
		 
		 
## Analyze your training with AI
Large language models (LLMs) can help you analyze and plan your training. Fitdocs turns the workout files from your wearable into a format built for LLMs, and includes an analytics database for finding patterns across years of training. The knowledge store is a local directory of linked markdown files alongside a DuckDB analytics database. 

## Fitdocs runs the numbers, LLMs make the connections
LLMs are good at reading, connecting, and explaining, but they aren't reliable at arithmetic. Fitdocs calculates load, zones, splits, benchmarks, and fitness curve without any AI. Your LLM put the stats from your latest workout into context, identifies fitness trends over time, and writes the training plan you describe into the wiki, where it’s matched with 
