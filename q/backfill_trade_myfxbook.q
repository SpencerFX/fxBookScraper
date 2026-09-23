/ ============================================================
/ fxBookScraper - incremental, per-date backfill of trade_myfxbook
/ -
/ myfxbook_r.q's .mr.doTrade reads EVERY fxbook trade source (trades.csv +
/ accounts/losingAccounts.csv + all losingAccountsExpanded shards) into memory
/ and rewrites every date partition the union touches - correct, but wasteful
/ for topping up trade_myfxbook with just a new drop of CSVs (e.g. a shard's
/ "_v2" continuation file): re-reading and re-writing millions of already-
/ current rows just to add a comparatively small number of new ones.
/ -
/ This script instead:
/   1. reads ONLY the new source CSV(s) given via -csvdir (default
/      data/csv/losingAccountsExpanded_v2) into one in-memory table,
/   2. groups the new rows by date,
/   3. for EACH date touched, loads ONLY that one existing on-disk
/      trade_myfxbook partition (a handful of column-file reads, not a
/      whole-HDB \l), merges the new rows in (de-duped by tradeKey), and
/      writes JUST that partition back down.
/ Untouched dates are never read or rewritten at all.
/ -
/   q q/backfill_trade_myfxbook.q -hdb C:/data/retail -csvdir data/csv/losingAccountsExpanded_v2
/ -
/ -csvdir is scanned for every "losingAccountsExpanded*.csv" file it contains
/ (not a fixed list of 4), so this same script also works for the original
/ losingAccountsExpanded/ drop, a future _v3 drop, or any other directory of
/ same-schema fxbook trade CSVs.
/ ============================================================

.bf.args:.Q.opt .z.x
/ NB: `x in key .bf.args` (not `count .bf.args\`x`) - indexing a .Q.opt dict
/ with an absent key returns a 1-element list holding an empty string, so
/ `count` is always 1 and never picks the default branch (see myfxbook_r.q).
.bf.hdb:$[`hdb in key .bf.args; first .bf.args`hdb; "C:/data/retail"]
.bf.csvdir:$[`csvdir in key .bf.args; first .bf.args`csvdir; "data/csv/losingAccountsExpanded_v2"]
.bf.excludeFile:$[`exclude in key .bf.args; first .bf.args`exclude; "data/state/bad_action_systems.txt"]
.bf.root:hsym `$.bf.hdb
.bf.symDomain:`sym_myfxbook
.bf.tname:`trade_myfxbook

-1 "[backfill] hdb=",.bf.hdb," csvdir=",.bf.csvdir," sym=",string .bf.symDomain;

/ load the existing sym domain file (if any) so on-disk enum columns for
/ existing partitions can be read/de-enumerated correctly in this session -
/ normally a whole-root \l does this automatically; here we deliberately skip
/ that (the whole point is avoiding a full-HDB load) so it's done by hand.
.bf.symPath:hsym `$.bf.hdb,"/",string .bf.symDomain;
if[not ()~key .bf.symPath;
  @[{y set get x}[.bf.symPath]; .bf.symDomain; {[e] -1 "[backfill] WARNING: could not load ",string[.bf.symDomain],": ",e}] ];

/ ---- csv reading (same pattern/types as myfxbook_r.q's .mr.readSafe/.mr.cTrade) --

.bf.readSafe:{[path;colz;ty]
  p:hsym `$path;
  if[()~key p; -1 "[backfill] missing ",path; :flip colz!(count colz)#()];
  lines:read0 p;
  if[2>count lines; -1 "[backfill] empty ",path; :flip colz!(count colz)#()];
  lines:1_lines;
  lines:lines where 0<count each lines;
  if[0=count lines; :flip colz!(count colz)#()];
  flip colz!(ty;",") 0: lines }

.bf.cTrade:`tradeKey`systemId`username`systemName`ticket`symbol`action`openTime`closeTime`openPrice`closePrice`sl`tp`lots`pips`profit`gainPct`durationSec`swap`commission`collectedAt

.bf.pTs:{
  s:23$'x;
  s:@[;4 7;:;"."] each s;
  s:@[;10;:;"D"] each s;
  "P"$ s }

/ ---- exclude list (same 222 known-bad-parse fxbook systemIds as everywhere else) --

.bf.excluded:$[
  ()~key hsym `$.bf.excludeFile;
    0#0Nj;
    ("J"$) each read0 hsym `$.bf.excludeFile ];
-1 "[backfill] excluding ",string[count .bf.excluded]," known-bad-parse fxbook systemIds";

/ ---- de-enum helper (same pattern as union.q's .un.deenum) -------------------

.bf.deenum:{[t] {[t;c] $[20h=type t c; @[t;c;value]; t]}/[t;cols t] }

/ ---- discover + load every losingAccountsExpanded*.csv under -csvdir --------

.bf.srcFiles:{[csvdir]
  d:hsym `$csvdir;
  if[()~key d; -1 "[backfill] csvdir not found: ",csvdir; :()];
  fs:key d;
  fs:fs where fs like "losingAccountsExpanded*.csv";
  asc {[csvdir;f] csvdir,"/",string f}[csvdir;] each fs }

.bf.loadSrc:{[path]
  t:.bf.readSafe[path; .bf.cTrade; "SJSSSSS**",(8#"F"),"JFF*"];
  if[0=count t; :0#t];
  delete from t where systemId in .bf.excluded }

files:.bf.srcFiles[.bf.csvdir];
if[0=count files; -1 "[backfill] no losingAccountsExpanded*.csv found under ",.bf.csvdir,", nothing to do"; exit 0];
-1 "[backfill] found ",string[count files]," source file(s): ",", " sv files;

new:raze .bf.loadSrc each files;
-1 "[backfill] loaded ",string[count new]," rows (post-exclude) from source CSVs";
if[0=count new; -1 "[backfill] nothing to do"; exit 0];

new:0!(`tradeKey xkey new);   / de-dupe any overlap across the source files themselves
new:update openTime:.bf.pTs openTime, closeTime:.bf.pTs closeTime, collectedAt:.bf.pTs collectedAt from new;
new:update pd:`date$closeTime from new;
new:update pd:`date$openTime from new where null pd;
new:update date:pd from new;
new:delete pd from new;

dates:asc distinct new`date;
-1 "[backfill] ",string[count new]," new trade rows span ",string[count dates]," date(s): ",string[first dates]," -> ",string[last dates];

/ ---- empty templates for the 3 sibling _myfxbook tables (snap/equity/growth) -
/ only used to stub a BRAND NEW date-partition so `\l` can still discover
/ every _myfxbook table root-wide afterwards - see q_kdb_gotchas: a partitioned
/ root's table list is discovered from the OVERALL NEWEST partition only, so a
/ newly-appearing date that's missing a sibling table breaks that table's
/ discovery for the WHOLE root, not just that date (hit for real backfilling
/ trade_myfxbook past mql5's ingest coverage - see myfxbook_dashboard/
/ q_kdb_gotchas memory). This does NOT recompute real snap/equity/growth data
/ (that needs snapshots.csv/daily.csv, out of scope here) - just keeps a new
/ date structurally complete.
@[system;"l q/schema.q";{[e]@[system;"l schema.q";{[e]'"backfill_trade_myfxbook.q: cannot locate schema.q"}]}]
.bf.emptySnap:0#snap;
.bf.emptyEquity:([] systemId:`long$(); date:`date$(); balance:`float$(); equity:`float$());
.bf.emptyGrowth:([] systemId:`long$(); date:`date$(); growthPct:`float$());
.bf.siblings:`snap_myfxbook`equity_myfxbook`growth_myfxbook!(.bf.emptySnap;.bf.emptyEquity;.bf.emptyGrowth);

.bf.writeStub:{[root;dt;tname;emptyT]
  if[`date in cols emptyT; emptyT:delete date from emptyT];   / the partition value is implicit in the dir name, never a physical column - writing it as a real file makes the NEWEST partition's schema wrongly include `date`, which then breaks every OTHER (correctly-built) partition's virtual-column access
  tdir:.Q.dd[.Q.dd[root; `$string dt]; tname];
  {[tdir;t;c] (.Q.dd[tdir;c]) set t c}[tdir;emptyT;] each cols emptyT;
  (.Q.dd[tdir;`.d]) set cols emptyT; }

.bf.ensureSiblings:{[root;dt]
  tdir:.Q.dd[root;`$string dt];
  {[root;tdir;dt;tname]
    complete:(tname in key tdir) and `.d in key .Q.dd[tdir;tname];
    if[not complete; .bf.writeStub[root;dt;tname;.bf.siblings tname]];
    }[root;tdir;dt;] each key .bf.siblings; }

/ ---- load ONE existing date partition (not the whole root) ------------------

.bf.loadExistingDay:{[root;dt;tname]
  tdir:.Q.dd[.Q.dd[root;`$string dt];tname];
  if[not tname in key .Q.dd[root;`$string dt]; :()];   / caller checks isNewTable itself
  cs:get .Q.dd[tdir;`.d];
  .bf.deenum flip cs!{[tdir;c] get .Q.dd[tdir;c]}[tdir;] each cs }

/ ---- per-date merge + writedown ---------------------------------------------

.bf.doDate:{[root;symDomain;tname;dt;newT]
  tdir:.Q.dd[root;`$string dt];
  isNewTable:not tname in key tdir;
  newT:delete date from newT;   / the partition value is implicit in the dir name, never a stored column - existing never has it, so newT must drop it before concatenating or `,` throws 'mismatch
  existing:$[isNewTable; 0#newT; .bf.loadExistingDay[root;dt;tname]];
  before:count existing;
  merged:existing,newT;
  merged:0!(`tradeKey xkey merged);         / de-dupe existing vs new (identical rows collapse; new wins on true ties)
  merged:`systemId xasc merged;
  if[`systemId in cols merged; merged:update `p#systemId from merged];
  t:.Q.ens[root;merged;symDomain];
  tOutDir:.Q.dd[tdir;tname];
  {[tOutDir;t;c] (.Q.dd[tOutDir;c]) set t c}[tOutDir;t;] each cols t;
  (.Q.dd[tOutDir;`.d]) set cols t;
  if[isNewTable; .bf.ensureSiblings[root;dt]];
  added:count[merged]-before;
  -1 "[backfill] ",string[dt],": ",string[before]," -> ",string[count merged]," rows (+",string[added],")",
     $[isNewTable;"  (NEW partition - stubbed sibling tables)";""];
  }

{[root;symDomain;tname;new;dt] .bf.doDate[root;symDomain;tname;dt; select from new where date=dt] }
  [.bf.root;.bf.symDomain;.bf.tname;new;] each dates;

-1 "[backfill] done. ",string[count dates]," date-partition(s) touched, ",string[count new]," rows applied.";
-1 "[backfill] NOTE: this only updates trade_myfxbook. If any of the above dates were NEW to the root, ";
-1 "[backfill]       equity_mql/growth_mql/trade_mql/snap_mql (or the plain composite trade/equity/growth";
-1 "[backfill]       tables from q/../union.q) may need the equivalent stub fix before union.q or a fresh";
-1 "[backfill]       \\l of the root can see them again - same issue hit backfilling the v1 CSVs.";
exit 0
