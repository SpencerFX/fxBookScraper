/ ============================================================
/ fxBookScraper - "myfxbook-suffixed" HDB at C:/data/r
/ Pure myfxbook data (no mql mixed in), named to line up with mqlScraper's
/ table names so this root can later sit alongside "*_mql" tables:
/   sig_myfxbook          - system registry            (root splay)
/   snap_myfxbook         - headline snapshots          (partition: date)
/   equity_myfxbook       - balance/equity daily curve  (partition: date)
/   withingrowth_myfxbook - daily gain% curve           (partition: date)
/   trade_myfxbook        - closed trades, trades.csv + losingAccounts.csv +
/                           losingAccounts_reverse.csv (losing_accounts.py's
/                           --reverse worker output, disjoint systemIds)
/                           unioned, same 222-system bad-parse exclusion as
/                           q/composite.q                (partition: date)
/ Uses a CUSTOM sym file (sym_myfxbook, not the default sym) via .Q.ens, so
/ this root can hold other sources under their own sym domain without
/ collision.
/ -
/   q q/myfxbook_r.q -hdb C:/data/r -csv data/csv
/ ============================================================

@[system;"l q/schema.q";{[e]@[system;"l schema.q";{[e]'"myfxbook_r.q: cannot locate schema.q"}]}]
/ snap_myfxbook empty template reuses schema.q's `snap` literal verbatim (same columns/types)
.mr.emptySnap:0#snap;

.mr.args:.Q.opt .z.x
.mr.hdb:$[count .mr.args`hdb; first .mr.args`hdb; "C:/data/r"]
.mr.csv:$[count .mr.args`csv; first .mr.args`csv; "data/csv"]
.mr.excludeFile:$[count .mr.args`exclude; first .mr.args`exclude; "data/state/bad_action_systems.txt"]
.mr.root:hsym `$.mr.hdb
.mr.symDomain:`sym_myfxbook

-1 "[myfxbook_r] hdb=",.mr.hdb," csv=",.mr.csv," sym=",string .mr.symDomain;

/ ---- csv reading ----------------------------------------------------------

.mr.readSafe:{[path;colz;ty]
  p:hsym `$path;
  if[()~key p; -1 "[myfxbook_r] missing ",path; :flip colz!(count colz)#()];
  lines:read0 p;
  if[2>count lines; -1 "[myfxbook_r] empty ",path; :flip colz!(count colz)#()];
  lines:1_lines;
  lines:lines where 0<count each lines;
  if[0=count lines; :flip colz!(count colz)#()];
  flip colz!(ty;",") 0: lines }

.mr.cSys:`systemId`username`systemName`displayName`url`firstSeen`lastSeen
.mr.cSnap:`ts`systemId`username`systemName`gain`absGain`daily`monthly`drawdown`balance`equity`equityPeak`profit`pips`deposits`withdrawals`interest`commissions`profitFactor`expectancyPips`trades`lots`winRatePct`avgWin`avgLoss`trackingSince`firstTradeAt`lastUpdate`broker`leverage`currency`accountType`strategyName
.mr.cDaily:`systemId`date`balance`equity`gain`profit`pips`lots`floatingPL
.mr.cTrade:`tradeKey`systemId`username`systemName`ticket`symbol`action`openTime`closeTime`openPrice`closePrice`sl`tp`lots`pips`profit`gainPct`durationSec`swap`commission`collectedAt

.mr.pTs:{
  s:23$'x;
  s:@[;4 7;:;"."] each s;
  s:@[;10;:;"D"] each s;
  "P"$ s }
.mr.pDate:{ "D"$ @[;4 7;:;"."] each 10$'x }

/ ---- exclude list (same 222 known-bad-parse fxbook systemIds as composite.q) --

.mr.excluded:$[
  ()~key hsym `$.mr.excludeFile;
    0#0Nj;
    ("J"$) each read0 hsym `$.mr.excludeFile ];
-1 "[myfxbook_r] excluding ",string[count .mr.excluded]," known-bad-parse fxbook systemIds";

/ ---- writedown (hand-rolled: .Q.ens against the custom sym domain, per-column set, .d) --

.mr.writeSplay:{[tname;t]
  d:.Q.dd[.mr.root;tname];
  t:.Q.ens[.mr.root;t;.mr.symDomain];
  {[d;t;c] (.Q.dd[d;c]) set t c}[d;t;] each cols t;
  (.Q.dd[d;`.d]) set cols t;
  -1 "[myfxbook_r] ",string[tname]," splay: ",string[count t]," rows"; }

.mr.writePart:{[tname;dt;t]
  if[`date in cols t; t:delete date from t];
  t:`systemId xasc t;
  if[`systemId in cols t; t:update `p#systemId from t];
  tdir:.Q.dd[.Q.dd[.mr.root; `$string dt]; tname];
  t:.Q.ens[.mr.root;t;.mr.symDomain];
  {[tdir;t;c] (.Q.dd[tdir;c]) set t c}[tdir;t;] each cols t;
  (.Q.dd[tdir;`.d]) set cols t; }

.mr.writePartitioned:{[tname;t;partCol]
  if[0=count t; -1 "[myfxbook_r] ",string[tname],": no rows"; :()];
  pv:t partCol;
  parts:asc distinct pv where not null pv;
  {[tname;t;pv;dt] .mr.writePart[tname;dt; t where pv=dt] }[tname;t;pv;] each parts;
  -1 "[myfxbook_r] ",string[tname],": ",string[count t]," rows over ",string[count parts]," partitions"; }

/ ensure every partition dir carries a COMPLETE splay for tname (empty one if
/ absent or partial-from-a-crash: check the `.d` descriptor, not just whether
/ the table's directory exists - see q/kdb_gotchas memory).
.mr.backfill:{[tname;emptyT]
  root:.mr.root;
  dates:{x where x like "[12][0-9][0-9][0-9].[0-9][0-9].[0-9][0-9]"} string key root;
  {[tname;emptyT;root;d]
    tdir:.Q.dd[root;`$d];
    complete:(tname in key tdir) and `.d in key .Q.dd[tdir;tname];
    if[not complete; .mr.writePart[tname; "D"$d; emptyT] ] }[tname;emptyT;root;] each dates; }

/ ---- per-table processing --------------------------------------------------

.mr.doSig:{
  t:.mr.readSafe[.mr.csv,"/systems.csv"; .mr.cSys; "JSSSS**"];
  if[0=count t; :()];
  t:update firstSeen:.mr.pTs firstSeen, lastSeen:.mr.pTs lastSeen from t;
  .mr.writeSplay[`sig_myfxbook; t] }

.mr.doSnap:{
  t:.mr.readSafe[.mr.csv,"/snapshots.csv"; .mr.cSnap; "*JSS",(16#"F"),"JFFFF","***","SJSSS"];
  if[0=count t; -1 "[myfxbook_r] snap: no rows"; :()];
  t:update ts:.mr.pTs ts, trackingSince:.mr.pTs trackingSince, firstTradeAt:.mr.pTs firstTradeAt, lastUpdate:.mr.pTs lastUpdate from t;
  t:update date:`date$ts from t;
  .mr.writePartitioned[`snap_myfxbook; t; `date] }

.mr.loadDaily:{
  t:.mr.readSafe[.mr.csv,"/daily.csv"; .mr.cDaily; "J*FFFFFFF"];
  if[0=count t; -1 "[myfxbook_r] daily: no rows"; :()];
  update date:.mr.pDate date from t }

.mr.doEquity:{[dt]
  if[0=count dt; :()];
  t:select systemId, date, balance, equity from dt;
  .mr.writePartitioned[`equity_myfxbook; t; `date] }

.mr.doWithinGrowth:{[dt]
  if[0=count dt; :()];
  t:select systemId, date, growthPct:gain from dt;
  .mr.writePartitioned[`withingrowth_myfxbook; t; `date] }

.mr.loadTradeSrc:{[path]
  t:.mr.readSafe[path; .mr.cTrade; "SJSSSSS**",(8#"F"),"JFF*"];
  if[0=count t; :0#t];
  delete from t where systemId in .mr.excluded }

.mr.doTrade:{
  t1:.mr.loadTradeSrc[.mr.csv,"/trades.csv"];
  t2:.mr.loadTradeSrc[.mr.csv,"/losingAccounts.csv"];
  t3:.mr.loadTradeSrc[.mr.csv,"/losingAccounts_reverse.csv"]; / losing_accounts.py --reverse worker's own output file - fully distinct systemIds from losingAccounts.csv, not a duplicate
  t:t1,t2,t3;
  if[0=count t; -1 "[myfxbook_r] trade: no rows"; :()];
  t:0!(`tradeKey xkey t);          / de-dupe overlap between the source CSVs
  t:update openTime:.mr.pTs openTime, closeTime:.mr.pTs closeTime, collectedAt:.mr.pTs collectedAt from t;
  t:update pd:`date$closeTime from t;
  t:update pd:`date$openTime from t where null pd;
  t:update date:pd from t;
  t:delete pd from t;
  .mr.writePartitioned[`trade_myfxbook; t; `date] }

/ ---- run --------------------------------------------------------------

.mr.doSig[];
.mr.doSnap[];
dailyT:.mr.loadDaily[];
.mr.doEquity[dailyT];
.mr.doWithinGrowth[dailyT];
.mr.doTrade[];

.mr.backfill[`snap_myfxbook; .mr.emptySnap];
.mr.backfill[`equity_myfxbook; ([] systemId:`long$(); date:`date$(); balance:`float$(); equity:`float$())];
.mr.backfill[`withingrowth_myfxbook; ([] systemId:`long$(); date:`date$(); growthPct:`float$())];
.mr.backfill[`trade_myfxbook; ([] tradeKey:`$(); systemId:`long$(); username:`$(); systemName:`$(); ticket:`$(); symbol:`$(); action:`$(); openTime:`timestamp$(); closeTime:`timestamp$(); openPrice:`float$(); closePrice:`float$(); sl:`float$(); tp:`float$(); lots:`float$(); pips:`float$(); profit:`float$(); gainPct:`float$(); durationSec:`long$(); swap:`float$(); commission:`float$(); collectedAt:`timestamp$())];

-1 "[myfxbook_r] done. Load with:  q -> \\l ",.mr.hdb;
exit 0
