/ ============================================================
/ fxBookScraper - CSV -> external on-disk partitioned kdb+ HDB
/ Builds the standalone HDB at C:/data/retail_myfxbook (or whatever -hdb
/ points at), separate from the in-repo data/hdb used by the main pipeline.
/ Same 4 tables as q/load.q (sys/snap/daily/trade) PLUS `losingTrade`,
/ sourced from data/csv/losingAccounts.csv (the filtered-search backfill).
/ Forked rather than sharing code with q/load.q so that script's contract
/ (used by the running supervisors) stays untouched.
/ -
/   q q/load_retail.q -hdb C:/data/retail_myfxbook -csv data/csv
/ ============================================================

@[system;"l q/schema.q";{[e]@[system;"l schema.q";{[e]'"load_retail.q: cannot locate schema.q"}]}]

/ losingTrade: same shape as trade, empty typed template (one-line literal on purpose)
losingTrade:([] tradeKey:`$(); systemId:`long$(); username:`$(); systemName:`$(); ticket:`$(); symbol:`$(); action:`$(); openTime:`timestamp$(); closeTime:`timestamp$(); openPrice:`float$(); closePrice:`float$(); sl:`float$(); tp:`float$(); lots:`float$(); pips:`float$(); profit:`float$(); gainPct:`float$(); durationSec:`long$(); swap:`float$(); commission:`float$(); collectedAt:`timestamp$())

.load.args:.Q.opt .z.x
.load.hdb:$[count .load.args`hdb; first .load.args`hdb; "C:/data/retail_myfxbook"]
.load.csv:$[count .load.args`csv; first .load.args`csv; "data/csv"]
.load.root:hsym `$.load.hdb
/ -only phase: run one step per process (each process is short-lived, so a
/ transient host hiccup during ~2500-partition backfill only loses that step)
.load.only:$[count .load.args`only; `$first .load.args`only; `all]

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

/ ensure every partition dir carries a COMPLETE splay for tname (empty one if
/ absent or - crucially - present-but-partial from an interrupted prior write:
/ check for the `.d` descriptor, the last thing a splay write creates, not just
/ whether the table's directory exists).
.load.backfill:{[tname;emptyT]
  root:.load.root;
  dates:{x where x like "[12][0-9][0-9][0-9].[0-9][0-9].[0-9][0-9]"} string key root;
  {[tname;emptyT;root;d]
    tdir:.Q.dd[root;`$d];
    complete:(tname in key tdir) and `.d in key .Q.dd[tdir;tname];
    if[not complete; .load.writePart[tname; "D"$d; emptyT] ] }[tname;emptyT;root;] each dates; }

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

.load.doLosingTrade:{
  t:.load.readSafe["losingAccounts.csv"; .load.cTrade; "SJSSSSS**",(8#"F"),"JFF*"];
  if[0=count t; -1 "[load] losingTrade: no rows"; :()];
  t:update openTime:.load.pTs openTime, closeTime:.load.pTs closeTime, collectedAt:.load.pTs collectedAt from t;
  t:update pd:`date$closeTime from t;
  t:update pd:`date$openTime from t where null pd;
  t:update date:pd from t;
  t:delete pd from t;
  .load.writePartitioned[`losingTrade; t; `date] }

/ ---- run -- each guard is one line on purpose (see kdb gotcha note top of file)

.load.wantAll:.load.only=`all;
if[.load.wantAll or .load.only=`sys; .load.doSys[]; -1 "[load] step sys done"];
if[.load.wantAll or .load.only=`snap; .load.doSnap[]; -1 "[load] step snap done"];
if[.load.wantAll or .load.only=`daily; .load.doDaily[]; -1 "[load] step daily done"];
if[.load.wantAll or .load.only=`trade; .load.doTrade[]; -1 "[load] step trade done"];
if[.load.wantAll or .load.only=`losingTrade; .load.doLosingTrade[]; -1 "[load] step losingTrade done"];
if[.load.wantAll or .load.only=`backfillSnap; .load.backfill[`snap; snap]; -1 "[load] step backfillSnap done"];
if[.load.wantAll or .load.only=`backfillDaily; .load.backfill[`daily; daily]; -1 "[load] step backfillDaily done"];
if[.load.wantAll or .load.only=`backfillTrade; .load.backfill[`trade; trade]; -1 "[load] step backfillTrade done"];
if[.load.wantAll or .load.only=`backfillLosingTrade; .load.backfill[`losingTrade; losingTrade]; -1 "[load] step backfillLosingTrade done"];
-1 "[load] finished.  Load with:  q -> \\l ",.load.hdb;
exit 0
