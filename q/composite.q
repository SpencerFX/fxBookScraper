/ ============================================================
/ fxBookScraper + mqlScraper - composite trade table
/ Unions myfxbook's closed-trade history (trades.csv + losingAccounts.csv) with
/ mql5's signal trade history (../mqlScraper/data/csv/trades.csv) into one
/ external, date-partitioned kdb+ HDB with a single `ctrade` table.
/ -
/   q q/composite.q -hdb C:/data/retail_composite -fxcsv data/csv ^
/       -mqlcsv C:/Users/giant/Downloads/Work/Git/mqlScraper/data/csv
/ -
/ Excludes any fxbook systemId listed in -exclude (default
/ data/state/bad_action_systems.txt): those accounts render a myfxbook
/ history-table variant with an extra leading <td> that the old parser read
/ positionally, silently shifting symbol/action/lots/sl/tp into the wrong
/ columns. The parser is fixed (parser/system.py, action-cell-anchored) but
/ the ~97k rows already collected under the old parser can't be repaired
/ locally - only page 1 of each system's history was ever saved to raw HTML,
/ so a real fix needs those systems re-walked from myfxbook again. Until that
/ re-walk happens, this loader just leaves them out rather than mix in rows
/ with a known-wrong symbol/action/lots/sl/tp.
/ ============================================================

/ ctrade: common schema across both sources (one-line literal on purpose)
ctrade:([] source:`$(); sourceId:`long$(); ckey:`$(); symbol:`$(); action:`$(); openTime:`timestamp$(); closeTime:`timestamp$(); openPrice:`float$(); closePrice:`float$(); sl:`float$(); tp:`float$(); volume:`float$(); pips:`float$(); profit:`float$(); gainPct:`float$(); durationSec:`long$(); swap:`float$(); commission:`float$(); cancelled:`boolean$(); comment:`$(); collectedAt:`timestamp$())

.ct.args:.Q.opt .z.x
.ct.hdb:$[count .ct.args`hdb; first .ct.args`hdb; "C:/data/retail_composite"]
.ct.fxCsv:$[count .ct.args`fxcsv; first .ct.args`fxcsv; "data/csv"]
.ct.mqlCsv:$[count .ct.args`mqlcsv; first .ct.args`mqlcsv; "C:/Users/giant/Downloads/Work/Git/mqlScraper/data/csv"]
.ct.excludeFile:$[count .ct.args`exclude; first .ct.args`exclude; "data/state/bad_action_systems.txt"]
.ct.root:hsym `$.ct.hdb

-1 "[composite] hdb=",.ct.hdb," fxcsv=",.ct.fxCsv," mqlcsv=",.ct.mqlCsv;

/ ---- csv reading ----------------------------------------------------------

.ct.readSafe:{[path;colz;ty]
  p:hsym `$path;
  if[()~key p; -1 "[composite] missing ",path; :flip colz!(count colz)#()];
  lines:read0 p;
  if[2>count lines; -1 "[composite] empty ",path; :flip colz!(count colz)#()];
  lines:1_lines;
  lines:lines where 0<count each lines;
  if[0=count lines; :flip colz!(count colz)#()];
  flip colz!(ty;",") 0: lines }

.ct.cFx:`tradeKey`systemId`username`systemName`ticket`symbol`action`openTime`closeTime`openPrice`closePrice`sl`tp`lots`pips`profit`gainPct`durationSec`swap`commission`collectedAt
.ct.cMql:`tradeKey`signalId`kind`action`orderType`symbol`openTime`closeTime`openPrice`closePrice`sl`tp`volume`commission`swap`profit`cancelled`comment`collectedAt

.ct.pTs:{
  s:23$'x;
  s:@[;4 7;:;"."] each s;
  s:@[;10;:;"D"] each s;
  "P"$ s }

/ ---- exclude list -----------------------------------------------------------

.ct.excluded:$[
  ()~key hsym `$.ct.excludeFile;
    0#0Nj;
    ("J"$) each read0 hsym `$.ct.excludeFile ];
-1 "[composite] excluding ",string[count .ct.excluded]," known-bad-parse fxbook systemIds";

/ ---- load + map to common schema -------------------------------------------

.ct.loadFx:{[path]
  t:.ct.readSafe[path; .ct.cFx; "SJSSSSS**",(8#"F"),"JFF*"];
  if[0=count t; :0#ctrade];
  t:delete from t where systemId in .ct.excluded;
  if[0=count t; :0#ctrade];
  t:update openTime:.ct.pTs openTime, closeTime:.ct.pTs closeTime, collectedAt:.ct.pTs collectedAt from t;
  select source:`fxbook, sourceId:systemId, ckey:(`$"fxbook_",/:string tradeKey),
    symbol:`$upper each string symbol, action, openTime, closeTime,
    openPrice, closePrice, sl, tp, volume:lots, pips, profit, gainPct, durationSec,
    swap, commission, cancelled:0b, comment:`, collectedAt
  from t }

/ mqlScraper may store trades as one flat trades.csv OR (newer) split per-signal
/ under trades/<signalId>.csv - read whichever exists.
.ct.readMqlTrades:{[dir]
  flat:hsym `$dir,"/trades.csv";
  if[not ()~key flat; :.ct.readSafe[dir,"/trades.csv"; .ct.cMql; "SJSSSS**FFFFFFFFJS*"]];
  splitDir:hsym `$dir,"/trades";
  if[()~key splitDir; -1 "[composite] no mql trades.csv or trades/ dir under ",dir; :flip .ct.cMql!(count .ct.cMql)#()];
  files:key splitDir;
  files:files where (files like "*.csv") and not files like "_index.csv";
  -1 "[composite] mql trades/: reading ",string[count files]," per-signal files";
  raze {[dir;f] .ct.readSafe[dir,"/trades/",string f; .ct.cMql; "SJSSSS**FFFFFFFFJS*"]}[dir;] each files }

.ct.loadMql:{[path]
  t:.ct.readMqlTrades[path];
  if[0=count t; :0#ctrade];
  t:select from t where kind=`trade;
  if[0=count t; :0#ctrade];
  t:update openTime:.ct.pTs openTime, closeTime:.ct.pTs closeTime, collectedAt:.ct.pTs collectedAt from t;
  t:update durationSec:`long$(closeTime-openTime) div 1000000000 from t;
  select source:`mql, sourceId:signalId, ckey:(`$"mql_",/:string tradeKey),
    symbol:`$upper each string symbol, action, openTime, closeTime,
    openPrice, closePrice, sl, tp, volume, pips:0n, profit, gainPct:0n,
    durationSec, swap, commission, cancelled:0<>cancelled, comment, collectedAt
  from t }

/ ---- writedown (same hand-rolled pattern as load.q / load_retail.q / retail.q) --

.ct.writePart:{[dt;t]
  if[`date in cols t; t:delete date from t];
  t:`sourceId xasc t;
  t:update `p#sourceId from t;
  tdir:.Q.dd[.Q.dd[.ct.root; `$string dt]; `ctrade];
  t:.Q.en[.ct.root;t];
  {[tdir;t;c] (.Q.dd[tdir;c]) set t c}[tdir;t;] each cols t;
  (.Q.dd[tdir;`.d]) set cols t; }

.ct.writePartitioned:{[t]
  if[0=count t; -1 "[composite] ctrade: no rows"; :()];
  pv:?[not null t`closeTime; t`closeTime; t`openTime];
  pv:`date$pv;
  t:update date:pv from t;
  parts:asc distinct pv where not null pv;
  {[t;pv;dt] .ct.writePart[dt; t where pv=dt] }[t;pv;] each parts;
  -1 "[composite] ctrade: ",string[count t]," rows over ",string[count parts]," partitions"; }

.ct.backfill:{[]
  root:.ct.root;
  dates:{x where x like "[12][0-9][0-9][0-9].[0-9][0-9].[0-9][0-9]"} string key root;
  {[root;d]
    tdir:.Q.dd[root;`$d];
    complete:(`ctrade in key tdir) and `.d in key .Q.dd[tdir;`ctrade];
    if[not complete; .ct.writePart["D"$d; 0#ctrade] ] }[root;] each dates; }

/ ---- run --------------------------------------------------------------

fx1:.ct.loadFx[.ct.fxCsv,"/trades.csv"];
-1 "[composite] fxbook trades.csv: ",string[count fx1]," rows (post-exclude)";
fx2:.ct.loadFx[.ct.fxCsv,"/losingAccounts.csv"];
-1 "[composite] fxbook losingAccounts.csv: ",string[count fx2]," rows (post-exclude)";
mq:.ct.loadMql[.ct.mqlCsv];
-1 "[composite] mql trades: ",string[count mq]," rows (kind=trade)";

/ NB: don't call this `all` - it shadows the q builtin `all` and top-level
/ assignment to that name throws a bare 'assign error with no useful message.
combined:fx1,fx2,mq;
combined:0!(`ckey xkey combined);   / de-dupe cross-source overlap (same trade, last wins)
-1 "[composite] union before dedupe: ",string[count fx1,fx2,mq],"  after dedupe: ",string[count combined];

.ct.writePartitioned[combined];
.ct.backfill[];
-1 "[composite] done. Load with:  q -> \\l ",.ct.hdb;
exit 0
