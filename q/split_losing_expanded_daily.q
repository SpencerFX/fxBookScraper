/ ============================================================
/ fxBookScraper - split losingAccountsExpanded*.csv shards into one plain CSV
/ per close-date (tradeKey-deduped across all source shards - and across all
/ source directories when -csvdirs names more than one, so re-crawled
/ generations collapse onto the same daily file), same column order/text as
/ the source files - a drop-in daily-split view, not a kdb+ writedown.
/ Useful for cheaply re-processing/backfilling a single day without scanning
/ every shard's full file.
/ -
/   q q/split_losing_expanded_daily.q -csvdir data/csv/losingAccountsExpanded_v7 -outdir data/csv/losingAccountsExpanded_v7/daily
/   q q/split_losing_expanded_daily.q -csvdirs data/csv/losingAccountsExpanded,data/csv/losingAccountsExpanded_v2,... -outdir data/csv/losingAccountsExpanded/daily
/ ============================================================

.sp.args:.Q.opt .z.x
.sp.csvdir:$[`csvdir in key .sp.args; first .sp.args`csvdir; "data/csv/losingAccountsExpanded_v7"]
.sp.csvdirs:$[`csvdirs in key .sp.args; "," vs first .sp.args`csvdirs; enlist .sp.csvdir]
.sp.outdir:$[`outdir in key .sp.args; first .sp.args`outdir; .sp.csvdir,"/daily"]

-1 ("[split] csvdirs=",(", " sv .sp.csvdirs)," outdir="),.sp.outdir;

.sp.cTrade:`tradeKey`systemId`username`systemName`ticket`symbol`action`openTime`closeTime`openPrice`closePrice`sl`tp`lots`pips`profit`gainPct`durationSec`swap`commission`collectedAt

/ load tradeKey as a symbol (fast de-dupe key), every other column as plain
/ unparsed text ("*") so the output CSV reproduces the source text exactly -
/ no numeric/timestamp reformatting risk.
.sp.ty:"S",20#"*"

.sp.readSafe:{[path]
  p:hsym `$path;
  if[()~key p; -1 "[split] missing ",path; :flip .sp.cTrade!(count .sp.cTrade)#()];
  lines:read0 p;
  if[2>count lines; -1 "[split] empty ",path; :flip .sp.cTrade!(count .sp.cTrade)#()];
  lines:1_lines;
  lines:lines where 0<count each lines;
  if[0=count lines; :flip .sp.cTrade!(count .sp.cTrade)#()];
  flip .sp.cTrade!(.sp.ty;",") 0: lines }

.sp.srcFiles:{[csvdir]
  d:hsym `$csvdir;
  if[()~key d; -1 "[split] csvdir not found: ",csvdir; :()];
  fs:key d;
  fs:fs where (fs like "losingAccountsExpanded*.csv");
  asc {[csvdir;f] csvdir,"/",string f}[csvdir;] each fs }

files:raze .sp.srcFiles each .sp.csvdirs;
if[0=count files; -1 "[split] no losingAccountsExpanded*.csv found under any of ",", " sv .sp.csvdirs; exit 0];
-1 "[split] found ",string[count files]," source file(s): ",", " sv files;

dat:raze .sp.readSafe each files;
-1 "[split] loaded ",string[count dat]," raw rows";

dat:0!(`tradeKey xkey dat);
-1 "[split] ",string[count dat]," unique rows after tradeKey de-dupe";

/ first 10 chars of closeTime (fallback openTime) = "YYYY-MM-DD"; blank/short
/ strings take-pad with spaces, so detect those by length instead of value.
.sp.first10:{[s] $[10>count s; ""; 10#s]}
cdate:.sp.first10 each dat`closeTime;
odate:.sp.first10 each dat`openTime;
dstr:?[0=count each cdate; odate; cdate];           / fallback to openTime's date when closeTime is blank
nBlank:sum 0=count each dstr;
if[nBlank>0; -1 "[split] WARNING: ",string[nBlank]," rows have neither a parseable closeTime nor openTime - skipped"];

g:group dstr;
if["" in key g; g:(key[g] where key[g]<>"") ! (value[g] where key[g]<>"")];   / drop the blank-date bucket, if any
-1 "[split] spans ",string[count g]," distinct date(s)";

if[()~key hsym `$.sp.outdir; system "mkdir \"",.sp.outdir,"\""];

hdr:"," sv string .sp.cTrade;
outCols:cols dat;

.sp.writeDay:{[dat;outCols;hdr;outdir;dt;idx]
  rows:{[dat;c;idx] $[c=`tradeKey; string dat[c] idx; dat[c] idx]}[dat;;idx] each outCols;
  lines:enlist[hdr],{","sv x} each flip rows;
  fn:ssr[dt;"-";"."];
  (hsym `$outdir,"/",fn,".csv") 0: lines; }

{[dat;outCols;hdr;outdir;kv] .sp.writeDay[dat;outCols;hdr;outdir;kv 0;kv 1]}
  [dat;outCols;hdr;.sp.outdir;] each flip (key g;value g);

-1 "[split] wrote ",string[count g]," daily file(s) to ",.sp.outdir;
exit 0
