/ ============================================================
/ fxBookScraper - convenience queries over the HDB
/ -
/   q q/query.q -hdb data/hdb        / prints a few summaries
/   q -> \l data/hdb -> \l q/query.q / interactive: use .fx.* helpers
/ ============================================================

.fx.hdb:$[count a:.Q.opt[.z.x]`hdb; first a; "data/hdb"]
if[not `snap in tables[]; system "l ",.fx.hdb]

/ latest headline snapshot per system
.fx.latest:{[] `gain xdesc 0!select by systemId from `ts xasc select from snap }

/ leaderboard: latest gain / drawdown / profitFactor, joined to the registry
.fx.leaderboard:{[n]
  l:.fx.latest[];
  r:`systemId xkey select systemId,username,systemName,displayName from sys;
  n sublist `gain xdesc r lj `systemId xkey select systemId,ts,gain,drawdown,profitFactor,balance,trades from l }

/ equity / balance curve for one system
.fx.curve:{[sid] `date xasc select date,balance,equity,gain,profit,pips from daily where systemId=sid }

/ closed-trade blotter for one system
.fx.blotter:{[sid] `closeTime xasc select closeTime,symbol,action,lots,openPrice,closePrice,pips,profit,gainPct,durationSec from trade where systemId=sid }

/ per-symbol aggregates for one system (or all, sid::0N)
.fx.bySymbol:{[sid]
  t:$[null sid; trade; select from trade where systemId=sid];
  `netProfit xdesc select trades:count i, netProfit:sum profit, netPips:sum pips, winPct:100*avg profit>0, avgLots:avg lots by symbol from t }

/ per-broker aggregate of the latest snapshots
.fx.byBroker:{[] `systems xdesc select systems:count i, avgGain:avg gain, avgDrawdown:avg drawdown, medProfitFactor:med profitFactor by broker from .fx.latest[] }

.fx.summary:{
  -1 "tables: ",", " sv string tables[];
  -1 "\n== leaderboard (top 10 by latest gain) ==";
  show .fx.leaderboard 10;
  -1 "\n== by broker ==";
  show .fx.byBroker[];
  }

if[not count getenv `FX_QUIET; .fx.summary[]]
if[.z.f like "*query.q"; exit 0]
