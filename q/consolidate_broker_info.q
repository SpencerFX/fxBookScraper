/ ============================================================
/ fxBookScraper - consolidate brokerInfo_*.csv (base + _v2/_v3 generations)
/ AND brokerages*.csv (the earlier-generation scrape that also carries a
/ `url` column brokerInfo dropped) into one CSV per alphanumeric username
/ bucket (first char of username, case-folded: 0-9, a-z, "_other" for
/ anything else/blank), deduped by systemId (one broker-info record per
/ system; latest collectedAt wins when a system was re-scraped across
/ generations/sources). Rows from brokerInfo (no `url` column) get a blank
/ url rather than losing the column - nothing is dropped, same reasoning
/ as mqlScraper/union.q's uj-based column handling.
/ -
/   q q/consolidate_broker_info.q -csvdirs data/csv,data/csv/brokerInfo_v2,data/csv/brokerInfo_v3,data/csv/brokerages -outdir data/csv/brokerInfo/byUsername
/ ============================================================

.bi.args:.Q.opt .z.x
.bi.csvdirs:$[`csvdirs in key .bi.args; "," vs first .bi.args`csvdirs; enlist "data/csv"]
.bi.outdir:$[`outdir in key .bi.args; first .bi.args`outdir; "data/csv/brokerInfo/byUsername"]

-1 ("[consolidate] csvdirs=",(", " sv .bi.csvdirs)," outdir="),.bi.outdir;

.bi.cols:`systemId`username`systemName`url`accountType`currency`broker`brokerSlug`brokerId`leverage`platform`tags`collectedAt
.bi.colsNoUrl:`systemId`username`systemName`accountType`currency`broker`brokerSlug`brokerId`leverage`platform`tags`collectedAt
.bi.tyUrl:"S",12#"*"
.bi.tyNoUrl:"S",11#"*"

.bi.readSafe:{[path]
  p:hsym `$path;
  if[()~key p; -1 "[consolidate] missing ",path; :flip .bi.cols!(count .bi.cols)#()];
  lines:read0 p;
  if[2>count lines; -1 "[consolidate] empty ",path; :flip .bi.cols!(count .bi.cols)#()];
  hdrLine:first lines;
  hasUrl:hdrLine like "*,url,*";
  body:1_lines;
  body:body where 0<count each body;
  if[0=count body; :flip .bi.cols!(count .bi.cols)#()];
  $[hasUrl;
    flip .bi.cols!(.bi.tyUrl;",") 0: body;
    [ t0:flip .bi.colsNoUrl!(.bi.tyNoUrl;",") 0: body;
      flip .bi.cols!(t0`systemId;t0`username;t0`systemName;(count t0)#enlist "";
        t0`accountType;t0`currency;t0`broker;t0`brokerSlug;t0`brokerId;
        t0`leverage;t0`platform;t0`tags;t0`collectedAt) ] ] }

.bi.srcFiles:{[csvdir]
  d:hsym `$csvdir;
  if[()~key d; -1 "[consolidate] csvdir not found: ",csvdir; :()];
  fs:key d;
  fs:fs where (fs like "brokerInfo*.csv") or (fs like "brokerages*.csv") or (fs like "?.csv") or (fs like "_other.csv");
  asc {[csvdir;f] csvdir,"/",string f}[csvdir;] each fs }

files:raze .bi.srcFiles each .bi.csvdirs;
if[0=count files; -1 "[consolidate] no brokerInfo*.csv/brokerages*.csv found under any of ",", " sv .bi.csvdirs; exit 0];
-1 "[consolidate] found ",string[count files]," source file(s): ",", " sv files;

dat:raze .bi.readSafe each files;
-1 "[consolidate] loaded ",string[count dat]," raw rows";

/ keep the LATEST collectedAt per systemId when a system was re-scraped
/ across generations/sources (collectedAt is ISO-8601 text, so plain
/ string ordering is chronological - ascending sort means "last" per
/ group is the most recent, for every field including url).
dat:`collectedAt xasc dat;
dat:0! select last username, last systemName, last url,
  last accountType, last currency, last broker, last brokerSlug,
  last brokerId, last leverage, last platform, last tags, last collectedAt
  by systemId from dat;
-1 "[consolidate] ",string[count dat]," unique systemId(s) after de-dupe (latest collectedAt kept)";

/ bucket key = lowercased first char of username, folded to 0-9/a-z, else "_other"
.bi.bucketOf:{[u]
  if[0=count u; :"_other"];
  c:lower first u;
  if[c in "0123456789abcdefghijklmnopqrstuvwxyz"; :enlist c];
  :"_other" }

buckets:.bi.bucketOf each dat`username;
g:group buckets;
-1 "[consolidate] spans ",string[count g]," bucket(s)";

if[()~key hsym `$.bi.outdir; system "mkdir \"",.bi.outdir,"\""];

hdr:"," sv string .bi.cols;
outCols:cols dat;

.bi.writeBucket:{[dat;outCols;hdr;outdir;bk;idx]
  rows:{[dat;c;idx] $[c=`systemId; string dat[c] idx; dat[c] idx]}[dat;;idx] each outCols;
  lines:enlist[hdr],{","sv x} each flip rows;
  (hsym `$outdir,"/",bk,".csv") 0: lines; }

{[dat;outCols;hdr;outdir;kv] .bi.writeBucket[dat;outCols;hdr;outdir;kv 0;kv 1]}
  [dat;outCols;hdr;.bi.outdir;] each flip (key g;value g);

-1 "[consolidate] wrote ",string[count g]," bucket file(s) to ",.bi.outdir;
exit 0
