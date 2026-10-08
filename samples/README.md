# Real-source editorial example

This is an assistant-edited static sample from publisher articles retrieved on October 7, 2026 (America/New_York). It contains 12 events and references 13 original reports from BBC, NPR, Al Jazeera, and The Guardian. It is not an automated Ollama run or proof of delivery.

- `briefing.html`: responsive Simplified Chinese sample.
- `briefing.txt`: plain-text fallback.
- `edition.json`: stories, ranking scores and claim citations.
- `evidence.json`: publisher metadata and short exact supporting excerpts.
- `concise-copy.json`: the shorter Chinese copy used when rebuilding the sample.

The weather header is a separately timed Open-Meteo forecast for Hanover, New Hampshire. It uses Celsius and the daily maximum hourly precipitation probability, including snow. The sample preserves its actual weather/news cutoff times and should not be treated as live when read later.

The live source URLs were successfully requested by the collector. The revised sample groups 3 politics/international, 3 economics/markets, 4 companies/business and 2 technology stories. It includes one conflict story. The sample retains attribution for disputed claims, distinguishes forecasts and plans from realized outcomes, and merges related coverage. Each selected primary publisher timestamp falls within 24 hours of the displayed collection cutoff; current readers should treat it as a dated sample. Some details are single-source reporting and are labeled accordingly. No assertion of independent verification is inferred merely from the number of links.

To rebuild from that collection, run `python scripts/build_sample.py`. This deliberately fails if titles or exact supporting excerpts no longer match. Automated daily generation uses `news_agent preview` instead; a static sample is never silently used as a fresh daily edition.
