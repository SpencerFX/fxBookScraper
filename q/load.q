/ ============================================================
/ fxBookScraper - CSV -> on-disk partitioned kdb+ HDB loader
/ -
/   q q/load.q -hdb data/hdb -csv data/csv
/ -
/ Rebuilds every touched partition from the CSVs in full, so re-running
/ is idempotent. `sys` is written as a plain splay at <hdb>/sys.
/ Writedown is hand-rolled (.Q.en + per-column set + .d) rather than
/ .Q.dpft, whose arity is unreliable on kdb+ 4.0 w64. After the data
/ pass, every partition gets an empty splay for any missing table so
/ that `\l` registers all tables and cross-partition scans don't fault.
/ ============================================================

@[system;"l q/schema.q";{[e]@[system;"l schema.q";{[e]'"load.q: cannot locate schema.q"}]}]

.load.args:.Q.opt .z.x
.load.hdb:$[count .load.args`hdb; first .load.args`hdb; "data/hdb"]
.load.csv:$[count .load.args`csv; first .load.args`csv; "data/csv"]
.load.root:hsym `$.load.hdb

-1 "[load] hdb=",.load.hdb," csv=",.load.csv;

/ ---- csv reading ----------------------------------------------------------

.load.readSafe:{[name;colz;ty]
  path:hsym `$.load.csv,"/",name;
  if[()~key path; -1 "[load] missing ",name; :flip colz!(count colz)#()];
  lines:read0 path;
  if[2>count lines; -1 "[load] empty ",name; :flip colz!(count colz)#()];
  lines:1_lines;
  lines:lines where 0<count each lines;
  if[0=count lines; :flip colz!(count colz)#()];
  flip colz!(ty;",") 0: lines }

/ header order MUST match normalizer.normalize *_FIELDS
.load.cSys:`systemId`username`systemName`displayName`url`firstSeen`lastSeen
.load.cSnap:`ts`systemId`username`systemName`gain`absGain`daily`monthly`drawdown`balance`equity`equityPeak`profit`pips`deposits`withdrawals`interest`commissions`profitFactor`expectancyPips`trades`lots`winRatePct`avgWin`avgLoss`trackingSince`firstTradeAt`lastUpdate`broker`leverage`currency`accountType`strategyName
.load.cDaily:`systemId`date`balance`equity`gain`profit`pips`lots`floatingPL
.load.cTrade:`tradeKey`systemId`username`systemName`ticket`symbol`action`openTime`closeTime`openPrice`closePrice`sl`tp`lots`pips`profit`gainPct`durationSec`swap`commission`collectedAt

/ ---- value coercion -----------------------------------------------------

.load.pTs:{  / list of char vectors -> timestamp vector (ISO-8601 in, tz suffix ignored)
  s:23$'x;                       / pad/truncate each to 23 chars: 2026-09-08T21:43:08.597
  s:@[;4 7;:;"."] each s;        / date separators -> .
  s:@[;10;:;"D"] each s;         / T -> D
  "P"$ s }
.load.pDate:{ "D"$ @[;4 7;:;"."] each 10$'x }

/ ---- writedown ----------------------------------------------------------------

.load.writeSplay:{[tname;t]
  d:.Q.dd[.load.root;tname];
  t:.Q.en[.load.root;t];
  {[d;t;c] (.Q.dd[d;c]) set t c}[d;t;] each cols t;
  (.Q.dd[d;`.d]) set cols t;
  -1 "[load] ",string[tname]," splay: ",string[count t]," rows"; }

.load.writePart:{[tname;dt;t]
  if[`date in cols t; t:delete date from t];
  t:`systemId xasc t;
  if[`systemId in cols t; t:update `p#systemId from t];
  tdir:.Q.dd[.Q.dd[.load.root; `$string dt]; tname];
  t:.Q.en[.load.root;t];
  {[tdir;t;c] (.Q.dd[tdir;c]) set t c}[tdir;t;] each cols t;
  (.Q.dd[tdir;`.d]) set cols t; }

.load.writePartitioned:{[tname;t;partCol]
  if[0=count t; -1 "[load] ",string[tname],": no rows"; :()];
  pv:t partCol;
  parts:asc distinct pv where not null pv;
  {[tname;t;pv;dt] .load.writePart[tname;dt; t where pv=dt] }[tname;t;pv;] each parts;
  -1 "[load] ",string[tname],": ",string[count t]," rows over ",string[count parts]," partitions"; }

/ ensure every partition dir carries a splay for tname (empty one if absent)
.load.backfill:{[tname;emptyT]
  root:.load.root;
  dates:{x where x like "[12][0-9][0-9][0-9].[0-9][0-9].[0-9][0-9]"} string key root;
  {[tname;emptyT;root;d]
    if[not tname in key .Q.dd[root;`$d];
      .load.writePart[tname; "D"$d; emptyT] ] }[tname;emptyT;root;] each dates; }

/ ---- per-table processing (multi-line bodies live inside {} on purpose) -----

.load.doSys:{
  t:.load.readSafe["systems.csv"; .load.cSys; "JSSSS**"];
  if[0=count t; :()];
  t:update firstSeen:.load.pTs firstSeen, lastSeen:.load.pTs lastSeen from t;
  .load.writeSplay[`sys; t] }

.load.doSnap:{
  t:.load.readSafe["snapshots.csv"; .load.cSnap; "*JSS",(16#"F"),"JFFFF","***","SJSSS"];
  if[0=count t; -1 "[load] snap: no rows"; :()];
  t:update ts:.load.pTs ts, trackingSince:.load.pTs trackingSince, firstTradeAt:.load.pTs firstTradeAt, lastUpdate:.load.pTs lastUpdate from t;
  t:update date:`date$ts from t;
  .load.writePartitioned[`snap; t; `date] }

.load.doDaily:{
  t:.load.readSafe["daily.csv"; .load.cDaily; "J*FFFFFFF"];
  if[0=count t; -1 "[load] daily: no rows"; :()];
  t:update date:.load.pDate date from t;
  .load.writePartitioned[`daily; t; `date] }

.load.doTrade:{
  t:.load.readSafe["trades.csv"; .load.cTrade; "SJSSSSS**",(8#"F"),"JFF*"];
  if[0=count t; -1 "[load] trade: no rows"; :()];
  t:update openTime:.load.pTs openTime, closeTime:.load.pTs closeTime, collectedAt:.load.pTs collectedAt from t;
  t:update pd:`date$closeTime from t;
  t:update pd:`date$openTime from t where null pd;
  t:update date:pd from t;
  t:delete pd from t;
  .load.writePartitioned[`trade; t; `date] }

/ ---- run ------------------------------------------------------------------

.load.doSys[]
.load.doSnap[]
.load.doDaily[]
.load.doTrade[]
.load.backfill[`snap; snap]
.load.backfill[`daily; daily]
.load.backfill[`trade; trade]
-1 "[load] done. Load with:  q -> \\l ",.load.hdb;
exit 0
