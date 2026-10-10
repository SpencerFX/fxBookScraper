/ ============================================================
/ Rebuild ONLY sig_myfxbook (systems.csv + brokerage join) and
/ brokerage_myfxbook (the full broker/leverage/platform registry, keyed by
/ systemId, for every system either brokerages.csv or the 4 brokerInfo_N.csv
/ shards has seen - ~27k systems, far more than sig_myfxbook's ~663-system
/ main directory) against an existing myfxbook_r.q-built root, without
/ re-touching snap/equity/growth/trade_myfxbook (unrelated to this change
/ and expensive to rewrite). Reuses myfxbook_r.q's exact .mr.*
/ csv-reading/writeSplay/doBrokerage/doSig logic verbatim (same sym domain,
/ same root layout) - just skips the rest of its "run" section.
/ -
/   q q/backfill_sig_brokerage.q -hdb C:/data/retail -csv data/csv
/ ============================================================

.mr.args:.Q.opt .z.x
/ NB: `x in key .mr.args` (not `count .mr.args\`x`) - see myfxbook_r.q.
.mr.hdb:$[`hdb in key .mr.args; first .mr.args`hdb; "C:/data/retail"]
.mr.csv:$[`csv in key .mr.args; first .mr.args`csv; "data/csv"]
.mr.root:hsym `$.mr.hdb
.mr.symDomain:`sym_myfxbook

-1 "[backfill_sig_brokerage] hdb=",.mr.hdb," csv=",.mr.csv;

.mr.readSafe:{[path;colz;ty]
  p:hsym `$path;
  if[()~key p; -1 "[backfill_sig_brokerage] missing ",path; :flip colz!(count colz)#()];
  lines:read0 p;
  if[2>count lines; -1 "[backfill_sig_brokerage] empty ",path; :flip colz!(count colz)#()];
  lines:1_lines;
  lines:lines where 0<count each lines;
  if[0=count lines; :flip colz!(count colz)#()];
  flip colz!(ty;",") 0: lines }

.mr.cSys:`systemId`username`systemName`displayName`url`firstSeen`lastSeen
.mr.cBrokerage:`systemId`username`systemName`url`accountType`currency`broker`brokerSlug`brokerId`leverage`platform`tags`collectedAt
.mr.cBrokerInfo:`systemId`username`systemName`accountType`currency`broker`brokerSlug`brokerId`leverage`platform`tags`collectedAt

.mr.pTs:{
  s:23$'x;
  s:@[;4 7;:;"."] each s;
  s:@[;10;:;"D"] each s;
  "P"$ s }

.mr.writeSplay:{[tname;t]
  d:.Q.dd[.mr.root;tname];
  t:.Q.ens[.mr.root;t;.mr.symDomain];
  {[d;t;c] (.Q.dd[d;c]) set t c}[d;t;] each cols t;
  (.Q.dd[d;`.d]) set cols t;
  -1 "[backfill_sig_brokerage] ",string[tname]," splay: ",string[count t]," rows"; }

.mr.doBrokerage:{
  b:.mr.readSafe[.mr.csv,"/brokerages/brokerages.csv"; .mr.cBrokerage; "JSSSSSSSJSSSS"];
  bi:raze {[d;f] .mr.readSafe[d,"/",f; .mr.cBrokerInfo; "JSSSSSSJSSSS"]}[.mr.csv;] each ("brokerInfo_1.csv";"brokerInfo_2.csv";"brokerInfo_3.csv";"brokerInfo_4.csv";"brokerInfo_v2/brokerInfo_v2_1.csv";"brokerInfo_v2/brokerInfo_v2_2.csv";"brokerInfo_v2/brokerInfo_v2_3.csv";"brokerInfo_v2/brokerInfo_v2_4.csv";"brokerInfo_v3/brokerInfo_v3_1.csv";"brokerInfo_v3/brokerInfo_v3_2.csv";"brokerInfo_v3/brokerInfo_v3_3.csv";"brokerInfo_v3/brokerInfo_v3_4.csv";"brokerInfo_v3/brokerInfo_v3_5.csv";"brokerInfo_v3/brokerInfo_v3_6.csv");
  mrg:uj[b;bi];             / uj nulls the `url` col bi lacks; bi listed second so it wins the xkey de-dupe below on systemId overlap
  if[0=count mrg; :0#mrg];
  mrg:0!(`systemId xkey mrg);   / de-dupe: last source wins - brokerInfo (newer, broader expanded-discovery sweep) over brokerages.csv
  .mr.writeSplay[`brokerage_myfxbook; mrg];   / full ~27k-system registry - sig_myfxbook's lj below only covers the ~663-system main directory
  1!select systemId,broker,brokerSlug,brokerId,leverage,platform,tags from mrg }

.mr.doSig:{
  t:.mr.readSafe[.mr.csv,"/systems.csv"; .mr.cSys; "JSSSS**"];
  if[0=count t; :()];
  t:update firstSeen:.mr.pTs firstSeen, lastSeen:.mr.pTs lastSeen from t;
  bk:.mr.doBrokerage[];
  if[count bk; t:t lj bk];
  .mr.writeSplay[`sig_myfxbook; t] }

.mr.doSig[];

-1 "[backfill_sig_brokerage] done.";
exit 0
