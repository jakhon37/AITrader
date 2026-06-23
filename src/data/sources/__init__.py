"""D02-DATA — data sources sub-package.

Three source adapters, each runnable as a background async task:
  news_fetcher  — NewsAPI + RSS ingestion
  calendar      — Forex Factory economic calendar scraper
  fred          — FRED API macro data (DFF, CPI, UNRATE, T10Y2Y)

All adapters write into DataStore and optionally publish to the Bus.
"""
