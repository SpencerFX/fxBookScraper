/ ============================================================
/ fxBookScraper - merge EVERY myfxbook trade source we have:
/   - data/csv/trades.csv              (single flat file)
/   - data/csv/trades/*.csv            (433 per-systemId files)
/   - data/csv/trades_bkp/*.csv        (historical backup snapshots)
/   - data/csv/losingAccountsExpanded/daily/*.csv  (the v1-v7 merged crawl)
/ dedupe by tradeKey, and write one plain CSV per close-date (fallback
/ open-date) into data/csv/trades/daily/ - same shape/approach as
/ split_losing_expanded_daily.q, just pointed at every trade source at once.
/ -
/   q q/consolidate_trades_daily.q -outdir data/csv/trades/daily
/ ============================================================

.tc.args:.Q.opt .z.x
.tc.outdir:$[`outdir in key .tc.args; first .tc.args`outdir; "data/csv/trades/daily"]

.tc.cTrade:`tradeKey`systemId`username`systemName`ticket`symbol`action`openTime`closeTime`openPrice`closePrice`sl`tp`lots`pips`profit`gainPct`durationSec`swap`commission`collectedAt
.tc.ty:"S",20#"*"

.tc.readSafe:{[path]
  p:hsym `$path;
  if[()~key p; -1 "[merge] missing ",path; :flip .tc.cTrade!(count .tc.cTrade)#()];
  lines:read0 p;
  if[2>count lines; -1 "[merge] empty ",path; :flip .tc.cTrade!(count .tc.cTrade)#()];
  lines:1_lines;
  lines:lines where 0<count each lines;
  if[0=count lines; :flip .tc.cTrade!(count .tc.cTrade)#()];
  flip .tc.cTrade!(.tc.ty;",") 0: lines }

.tc.globDir:{[dir;pat]
  d:hsym `$dir;
  if[()~key d; -1 "[merge] dir not found: ",dir; :()];
  fs:key d;
  fs:fs where (fs like pat) and not fs like "_index.csv";
  asc {[dir;f] dir,"/",string f}[dir;] each fs }

files:raze (
  enlist "data/csv/trades.csv";
  .tc.globDir["data/csv/trades";"*.csv"];
  .tc.globDir["data/csv/trades_bkp";"*.csv"];
  .tc.globDir["data/csv/losingAccountsExpanded/daily";"*.csv"] );
files:files where files like "*.csv";
-1 "[merge] found ",string[count files]," source file(s) across trades.csv, trades/, trades_bkp/, losingAccountsExpanded/daily/";

dat:raze .tc.readSafe each files;
-1 "[merge] loaded ",string[count dat]," raw rows";

/ real de-dupe (NOT a bare xkey round-trip, which only tags a key column
/ without collapsing duplicates) - keep the row with the latest collectedAt
/ per tradeKey, same proven pattern as consolidate_broker_info.q.
dat:`collectedAt xasc dat;
dat:0! select last systemId, last username, last systemName, last ticket,
  last symbol, last action, last openTime, last closeTime, last openPrice,
  last closePrice, last sl, last tp, last lots, last pips, last profit,
  last gainPct, last durationSec, last swap, last commission, last collectedAt
  by tradeKey from dat;
-1 "[merge] ",string[count dat]," unique rows after tradeKey de-dupe";

.tc.first10:{[s] $[10>count s; ""; 10#s]}
cdate:.tc.first10 each dat`closeTime;
odate:.tc.first10 each dat`openTime;
dstr:?[0=count each cdate; odate; cdate];
nBlank:sum 0=count each dstr;
if[nBlank>0; -1 "[merge] WARNING: ",string[nBlank]," rows have neither a parseable closeTime nor openTime - skipped"];

g:group dstr;
if["" in key g; g:(key[g] where key[g]<>"") ! (value[g] where key[g]<>"")];
-1 "[merge] spans ",string[count g]," distinct date(s)";

if[()~key hsym `$.tc.outdir; system "mkdir \"",.tc.outdir,"\""];

hdr:"," sv string .tc.cTrade;
outCols:cols dat;

.tc.writeDay:{[dat;outCols;hdr;outdir;dt;idx]
  rows:{[dat;c;idx] $[c=`tradeKey; string dat[c] idx; dat[c] idx]}[dat;;idx] each outCols;
  lines:enlist[hdr],{","sv x} each flip rows;
  fn:ssr[dt;"-";"."];
  (hsym `$outdir,"/",fn,".csv") 0: lines; }

{[dat;outCols;hdr;outdir;kv] .tc.writeDay[dat;outCols;hdr;outdir;kv 0;kv 1]}
  [dat;outCols;hdr;.tc.outdir;] each flip (key g;value g);

-1 "[merge] wrote ",string[count g]," daily file(s) to ",.tc.outdir;
exit 0
