/ ============================================================
/ fxBookScraper - kdb+ schema
/ Empty typed templates. Column order matches the CSV headers
/ written by normalizer/normalize.py (SYSTEM_FIELDS / SNAPSHOT_FIELDS
/ / DAILY_FIELDS / TRADE_FIELDS). One-line literals on purpose:
/ multi-line / indented top-level table literals do not load reliably.
/ ============================================================

/ system registry (splayed, non-partitioned; upserted each run)
sys:([] systemId:`long$(); username:`$(); systemName:`$(); displayName:`$(); url:`$(); firstSeen:`timestamp$(); lastSeen:`timestamp$())

/ headline stats snapshot - one row per system per crawl (partition: date of ts)
snap:([] ts:`timestamp$(); systemId:`long$(); username:`$(); systemName:`$(); gain:`float$(); absGain:`float$(); daily:`float$(); monthly:`float$(); drawdown:`float$(); balance:`float$(); equity:`float$(); equityPeak:`float$(); profit:`float$(); pips:`float$(); deposits:`float$(); withdrawals:`float$(); interest:`float$(); commissions:`float$(); profitFactor:`float$(); expectancyPips:`float$(); trades:`long$(); lots:`float$(); winRatePct:`float$(); avgWin:`float$(); avgLoss:`float$(); trackingSince:`timestamp$(); firstTradeAt:`timestamp$(); lastUpdate:`timestamp$(); broker:`$(); leverage:`long$(); currency:`$(); accountType:`$(); strategyName:`$())

/ daily equity / balance / gain series (partition: date)
daily:([] systemId:`long$(); date:`date$(); balance:`float$(); equity:`float$(); gain:`float$(); profit:`float$(); pips:`float$(); lots:`float$(); floatingPL:`float$())

/ closed trades (partition: date of closeTime)
trade:([] tradeKey:`$(); systemId:`long$(); username:`$(); systemName:`$(); ticket:`$(); symbol:`$(); action:`$(); openTime:`timestamp$(); closeTime:`timestamp$(); openPrice:`float$(); closePrice:`float$(); sl:`float$(); tp:`float$(); lots:`float$(); pips:`float$(); profit:`float$(); gainPct:`float$(); durationSec:`long$(); swap:`float$(); commission:`float$(); collectedAt:`timestamp$())
