/ ============================================================
/ fxBookScraper - in-memory ingest helpers
/ -
/ Optional. The normal path is CSV -> q/load.q -> HDB. These helpers
/ are for pushing parsed rows straight into in-memory tables (tests,
/ ad-hoc sessions, a future live feed). Load q/schema.q first.
/ ============================================================

if[not `trade in tables[]; @[system;"l q/schema.q";{[e] @[system;"l schema.q";{[e] '"load q/schema.q first"}]}]]

/ upsert one registry row (dict or 1-row table), keeping firstSeen stable
.fx.upsertSystem:{[s]
  s:$[98h=type s; first s; s];
  id:s`systemId;
  $[id in exec systemId from sys;
    [ `sys upsert update lastSeen:s`lastSeen from sys where systemId=id ];
    [ `sys insert s ] ];
  }

/ insert closed trades, skipping tradeKeys already present
.fx.insertTrades:{[t]
  if[0=count t; :0];
  fresh:select from t where not tradeKey in exec tradeKey from trade;
  `trade insert fresh;
  count fresh }

/ replace a system's daily rows (delete then insert - daily is a full snapshot)
.fx.replaceDaily:{[sid;t]
  delete from `daily where systemId=sid;
  if[count t; `daily insert t];
  count t }

/ append a headline snapshot row
.fx.addSnapshot:{[s]
  `snap insert $[98h=type s; s; enlist s];
  count s }
