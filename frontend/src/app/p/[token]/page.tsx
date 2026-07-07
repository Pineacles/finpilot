"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { useParams } from "next/navigation";
import { motion } from "motion/react";
import { api, PublicPortfolio, Trade, PortfolioSnapshot, ValueTimelinePoint } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell, ReferenceLine, ComposedChart, Line, Bar } from "recharts";
import { BarChart3, LineChart, X, Sun, Moon } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { AnimatedNumber } from "@/components/animated-number";
import { Sparkline as SparklineChart } from "@/components/sparkline";
import { LivePill } from "@/components/live-pill";

const COLORS = ["#3b82f6","#f97316","#ef4444","#a855f7","#14b8a6","#f59e0b","#ec4899","#22c55e","#06b6d4","#8b5cf6","#e11d48","#84cc16","#6366f1","#d946ef","#0ea5e9","#fb923c"];
const RANGES = [{value:"1d",label:"1D"},{value:"5d",label:"1W"},{value:"1mo",label:"1M"},{value:"3mo",label:"3M"},{value:"6mo",label:"6M"},{value:"1y",label:"1Y"},{value:"2y",label:"2Y"},{value:"5y",label:"5Y"}];

function PnlBadge({value,pct}:{value:number;pct?:number}){
  const pos=value>=0;
  return <span className={`text-[13px] px-2.5 py-1 rounded-xl font-medium inline-flex items-center gap-1 ${pos?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400"}`}>{pos?"+":""}{formatCurrency(value)}{pct!==undefined&&<span className="opacity-70">({pos?"+":""}{pct.toFixed(1)}%)</span>}</span>;
}

export default function PublicPortfolioPage(){
  const {token}=useParams<{token:string}>();
  const [p,setP]=useState<PublicPortfolio|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState(false);
  const [chartTicker,setChartTicker]=useState<string|null>(null);
  const [chartRange,setChartRange]=useState("1y");
  const [chartData,setChartData]=useState<{date:string;close:number}[]>([]);
  const [chartLoading,setChartLoading]=useState(false);
  const [trades,setTrades]=useState<Trade[]>([]);
  const [livePrices,setLivePrices]=useState<Record<string,{price:number;change:number;change_pct:number}>>({});
  const [flashes,setFlashes]=useState<Record<string,"up"|"down">>({});
  const prevPricesRef=useRef<Record<string,number>>({});
  const [historyData,setHistoryData]=useState<PortfolioSnapshot[]>([]);
  const [timeline,setTimeline]=useState<ValueTimelinePoint[]>([]);
  const [tradeChartSymbol,setTradeChartSymbol]=useState<string|null>(null);
  const [tradeChartData,setTradeChartData]=useState<{date:string;close:number}[]>([]);
  const [tradeChartRange,setTradeChartRange]=useState("1y");
  const [tradeChartLoading,setTradeChartLoading]=useState(false);
  const [timelineRange,setTimelineRange]=useState<"1W"|"1M"|"3M"|"6M"|"1Y"|"ALL">("3M");

  useEffect(()=>{
    if(!token)return;
    api.publicPortfolio(token).then(data=>{setP(data);if(data.positions.length)openChart(data.positions[0].symbol);}).catch(()=>setError(true)).finally(()=>setLoading(false));
    api.publicTrades(token).then(setTrades).catch(()=>{});
    api.publicPortfolioHistory(token).then(setHistoryData).catch(()=>{});
    api.publicValueTimeline(token).then(setTimeline).catch(()=>{});
  },[token]);

  // Live ticker polling — fetch fresh prices every 5 seconds and animate changes
  useEffect(()=>{
    if(!token)return;
    let cancelled=false;
    const poll=async()=>{
      try{
        const data=await api.publicLivePrices(token);
        if(cancelled)return;
        const newFlashes:Record<string,"up"|"down">={};
        Object.entries(data).forEach(([sym,p])=>{
          const old=prevPricesRef.current[sym];
          if(old!==undefined&&p.price!==old){
            newFlashes[sym]=p.price>old?"up":"down";
          }
          prevPricesRef.current[sym]=p.price;
        });
        setLivePrices(data);
        if(Object.keys(newFlashes).length){
          setFlashes(newFlashes);
          setTimeout(()=>setFlashes({}),1500);
        }
      }catch{}
    };
    poll();
    const i=setInterval(poll,15000);
    return()=>{cancelled=true;clearInterval(i);};
  },[token]);

  const openChart=async(ticker:string,range=chartRange)=>{
    setChartTicker(ticker);setChartRange(range);setChartLoading(true);
    try{const r=await api.publicChart(token,ticker,range);setChartData(r.data);}catch{setChartData([]);}
    finally{setChartLoading(false);}
  };
  useEffect(()=>{if(chartTicker)openChart(chartTicker,chartRange);},[chartRange]);

  const openTradeChart=async(sym:string,range=tradeChartRange)=>{
    setTradeChartSymbol(sym);setTradeChartRange(range);setTradeChartLoading(true);
    try{const r=await api.publicChart(token,sym,range);setTradeChartData(r.data);}catch{setTradeChartData([]);}
    finally{setTradeChartLoading(false);}
  };
  useEffect(()=>{if(tradeChartSymbol)openTradeChart(tradeChartSymbol,tradeChartRange);},[tradeChartRange]);

  const liveTotals=useMemo(()=>{
    if(!p)return{value:0,pnl:0,pnlPct:0};
    let liveValue=0;
    for(const pos of p.positions){
      const live=livePrices[pos.symbol];
      const refPrice=pos.last_price||pos.avg_cost_price||0;
      const fx=refPrice&&pos.quantity?(pos.market_value/(refPrice*pos.quantity)):1;
      const livePrice=live?.price??pos.last_price??pos.avg_cost_price??0;
      liveValue+=livePrice*pos.quantity*fx;
    }
    const pnl=liveValue-p.total_cost;
    const pnlPct=p.total_cost>0?(pnl/p.total_cost*100):0;
    return{value:liveValue,pnl,pnlPct};
  },[p,livePrices]);

  const [dark,setDark]=useState(false);
  useEffect(()=>{
    const stored=localStorage.getItem("theme");
    const isDark=stored==="dark"||(!stored&&window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDark(isDark);
    document.documentElement.classList.toggle("dark",isDark);
  },[]);
  const toggleTheme=()=>{
    const next=!dark;
    setDark(next);
    document.documentElement.classList.toggle("dark",next);
    localStorage.setItem("theme",next?"dark":"light");
  };

  if(loading)return(
    <div className="min-h-screen">
      <div className="mx-auto max-w-7xl px-6 py-10 space-y-6">
        {[...Array(4)].map((_,i)=><div key={i} className="h-32 rounded-[24px] bg-muted animate-pulse"/>)}
      </div>
    </div>
  );

  if(error||!p)return(
    <div className="min-h-screen flex items-center justify-center">
      <button onClick={toggleTheme} className="glass fixed top-6 right-6 w-[42px] h-[42px] rounded-[14px] flex items-center justify-center text-foreground hover:brightness-110 transition-all cursor-pointer" aria-label="Toggle theme">{dark?<Sun className="h-[18px] w-[18px]"/>:<Moon className="h-[18px] w-[18px]"/>}</button>
      <div className="text-center">
        <h1 className="text-[24px] font-bold mb-2">Portfolio not found</h1>
        <p className="text-muted-foreground">This link may have expired or the portfolio is no longer public.</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      {/* Floating theme toggle */}
      <button onClick={toggleTheme} className="glass fixed top-6 right-6 w-[42px] h-[42px] rounded-[14px] flex items-center justify-center text-foreground hover:brightness-110 transition-all cursor-pointer z-50" aria-label="Toggle theme">{dark?<Sun className="h-[18px] w-[18px]"/>:<Moon className="h-[18px] w-[18px]"/>}</button>

    <div className="mx-auto max-w-7xl px-6 py-10 space-y-8">
      <style>{`
  .recharts-brush text { fill: var(--foreground); font-weight: 500; font-size: 11px; }
  .recharts-brush-traveller { fill: var(--accent); }
  @keyframes flash-up { 0% { background-color: rgba(34,197,94,0.25); } 100% { background-color: transparent; } }
  @keyframes flash-down { 0% { background-color: rgba(239,68,68,0.25); } 100% { background-color: transparent; } }
  .flash-up { animation: flash-up 1.5s ease-out; }
  .flash-down { animation: flash-down 1.5s ease-out; }
`}</style>
      {/* Branded header */}
      <motion.div initial={{opacity:0,y:-8}} animate={{opacity:1,y:0}} transition={{duration:0.45,ease:[0.25,0.46,0.45,0.94]}} className="flex items-center justify-between gap-4 pb-2 border-b border-border/60">
        <div className="flex items-center gap-4">
          {/* Gradient logo square */}
          <div className="w-[52px] h-[52px] rounded-[14px] flex items-center justify-center shrink-0" style={{background:"linear-gradient(135deg,#3b82f6 0%,#8b5cf6 100%)"}} >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-[13px] font-bold tracking-tight" style={{background:"linear-gradient(135deg,#3b82f6,#8b5cf6)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>FinPilot</span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">Read-only view</span>
            </div>
            <p className="text-[15px] font-semibold text-foreground">Shared by {p.display_name}</p>
          </div>
        </div>
        <div className="text-right hidden sm:block">
          <div className="flex items-center gap-2 justify-end mb-1">
            <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-[0.5px]">Total Value</p>
            <LivePill/>
          </div>
          <p className="font-mono tabular-nums text-[42px] font-extrabold" style={{letterSpacing: '-1.2px'}}><AnimatedNumber value={liveTotals.value} format={formatCurrency}/></p>
          <div className="flex items-center gap-2 justify-end mt-1"><PnlBadge value={liveTotals.pnl} pct={liveTotals.pnlPct}/><span className="text-[12px] text-muted-foreground">all time</span></div>
        </div>
      </motion.div>

      {/* Mobile total value */}
      <div className="sm:hidden">
        <div className="flex items-center gap-2 mb-1">
          <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-[0.5px]">Total Value</p>
          <LivePill/>
        </div>
        <p className="font-mono tabular-nums text-[42px] font-extrabold" style={{letterSpacing: '-1.2px'}}><AnimatedNumber value={liveTotals.value} format={formatCurrency}/></p>
        <div className="flex items-center gap-3 mt-2"><PnlBadge value={liveTotals.pnl} pct={liveTotals.pnlPct}/><span className="text-[13px] text-muted-foreground">all time</span></div>
      </div>

      {/* Summary */}
      <div className="grid gap-5 grid-cols-2 lg:grid-cols-4">
        {[
          {l:"Invested",v:formatCurrency(p.total_cost),live:false},
          {l:"Cash",v:formatCurrency(p.cash_balance),live:false},
          {l:"Positions",v:String(p.positions_count),live:false},
          {l:"Total",v:liveTotals.value+p.cash_balance,live:true},
        ].map((item,i)=>(
          <GlassCard key={item.l} delay={0.05+i*0.05}>
            <p className="text-[12px] text-muted-foreground mb-1">{item.l}</p>
            <p className="font-mono tabular-nums text-[20px] font-bold">{item.live?<AnimatedNumber value={item.v as number} format={formatCurrency}/>:(item.v as string)}</p>
          </GlassCard>
        ))}
      </div>

      {/* Holdings + Chart */}
      <div className="grid gap-5 grid-cols-1 md:grid-cols-2 lg:grid-cols-5">
        {/* Allocation */}
        <GlassCard delay={0.2} className="md:col-span-1 lg:col-span-1 !p-4">
          <p className="text-[13px] font-medium text-muted-foreground mb-3">Allocation</p>
          {p.positions.length===0?<p className="text-[13px] text-muted-foreground text-center py-8">No positions</p>:(
            <div className="h-48"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={p.positions} dataKey="market_value" nameKey="symbol" cx="50%" cy="50%" outerRadius={70} innerRadius={42}>{p.positions.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Pie><Tooltip formatter={(v:any)=>formatCurrency(Number(v))}/></PieChart></ResponsiveContainer></div>
          )}
        </GlassCard>

        {/* Holdings */}
        <GlassCard delay={0.25} className="md:col-span-1 lg:col-span-2 !p-4">
          <p className="text-[14px] font-semibold text-muted-foreground mb-3">Holdings</p>
          <div className="space-y-1 max-h-[420px] overflow-y-auto pr-1" style={{scrollbarGutter:"stable"}}>
            {p.positions.map(pos=>{
              const live=livePrices[pos.symbol];
              const livePrice=live?.price??pos.last_price??0;
              const livePnlPct=pos.avg_cost_price?((livePrice/pos.avg_cost_price-1)*100):pos.pnl_pct;
              const flash=flashes[pos.symbol];
              return(
              <div key={pos.id} className={`flex items-center justify-between px-3.5 py-3 pr-4 rounded-[14px] cursor-pointer transition-all duration-200 hover:bg-accent ${chartTicker===pos.symbol?"bg-accent":""} ${flash==="up"?"flash-up":flash==="down"?"flash-down":""}`} onClick={()=>openChart(pos.symbol)}>
                <div className="min-w-[70px] shrink-0">
                  <p className="font-bold text-[14px]">{pos.symbol}</p>
                  <p className="text-[11px] text-muted-foreground truncate max-w-[80px]">{pos.name}</p>
                </div>
                <div className="hidden lg:block shrink-0"><SparklineChart data={pos.sparkline} width={90} height={36} color={livePnlPct>=0?"#3b82f6":"#ef4444"}/></div>
                <div className="text-right shrink-0">
                  <p className="font-mono tabular-nums text-[13px] font-semibold">{livePrice.toFixed(2)}<span className="text-[11px] text-muted-foreground ml-1">{pos.currency}</span></p>
                  <p className="font-mono tabular-nums text-[11px] text-muted-foreground">cost {pos.avg_cost_price.toFixed(2)}</p>
                </div>
                <div className="text-right hidden sm:block shrink-0">
                  <p className="font-mono tabular-nums text-[13px] font-semibold">{formatCurrency(pos.market_value)}</p>
                  <p className={`font-mono tabular-nums text-[11px] font-semibold ${livePnlPct>=0?"text-gain":"text-loss"}`}>{livePnlPct>=0?"+":""}{livePnlPct.toFixed(1)}%</p>
                  <p className={`text-[11px] tabular-nums ${pos.unrealized_pnl>=0?"text-gain":"text-loss"}`}>{pos.unrealized_pnl>=0?"+":""}{formatCurrency(pos.unrealized_pnl)}</p>
                  {pos.first_bought&&<p className="text-[10px] text-muted-foreground mt-0.5">since {new Date(pos.first_bought).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"2-digit"})}</p>}
                </div>
              </div>
              );
            })}
          </div>
        </GlassCard>

        {/* Chart */}
        <GlassCard delay={0.3} className="md:col-span-2 lg:col-span-2 !p-4">
          <div className="flex items-center justify-center mb-2">
            <p className="text-[13px] font-medium text-muted-foreground flex items-center gap-1.5"><BarChart3 className="h-4 w-4"/>{chartTicker||"Select stock"}</p>
          </div>
          {!chartTicker?<div className="h-60 flex items-center justify-center text-muted-foreground">Click a holding</div>:(
            <>
              {(()=>{
                const pos=p.positions.find(pp=>pp.symbol===chartTicker);
                if(!pos)return null;
                const live=livePrices[pos.symbol];
                const lp=live?.price??pos.last_price??0;
                const lc=live?.change??pos.change;
                const lcp=live?.change_pct??pos.change_pct;
                return <div className="flex items-center justify-center gap-3 mb-3"><span className="text-[20px] font-bold tabular-nums font-mono">{lp.toFixed(2)}</span><span className={`text-[13px] font-medium ${lc>=0?"text-gain":"text-loss"}`}>{lc>=0?"+":""}{lc.toFixed(2)} ({lcp>=0?"+":""}{lcp.toFixed(1)}%)</span></div>;
              })()}
              <div className="flex justify-center gap-1 mb-2">{RANGES.map(r=><button key={r.value} onClick={()=>setChartRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${chartRange===r.value?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{r.label}</button>)}</div>
              <div className="h-52">{chartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:chartData.length===0?<p className="text-[13px] text-muted-foreground">No data</p>:(
                <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{top:5,right:10,left:10,bottom:5}}><defs><linearGradient id="sg-pub" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2}/><stop offset="100%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={(d:string)=>d.slice(5)} stroke="var(--muted-foreground)"/><YAxis hide domain={["auto","auto"]}/><Tooltip formatter={(v:any)=>Number(v).toFixed(2)}/><Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#sg-pub)"/></AreaChart></ResponsiveContainer>
              )}</div>
            </>
          )}
        </GlassCard>
      </div>

      {/* Portfolio Timeline — unified chart with range presets */}
      {timeline.length>0&&(()=>{
        const allChartData=timeline.map((pt,i)=>{
          const prev=i>0?timeline[i-1]:pt;
          const dailyChange=pt.value-prev.value;
          const tradeLabels=pt.trades?.map(t=>{
            if(t.symbol==="CASH")return `${t.type==="deposit"?"+ Deposit":"- Withdraw"} ${formatCurrency(t.quantity)}`;
            return `${t.type==="buy"?"+ Buy":"- Sell"} ${t.quantity} ${t.symbol} @ ${t.price.toFixed(2)}`;
          }).join("\n")||null;
          return {date:pt.date,value:pt.value,cost:pt.cost,pnl:pt.pnl,dailyChange,gain:dailyChange>=0?dailyChange:0,loss:dailyChange<0?dailyChange:0,tradeLabels,trades:pt.trades};
        });
        const daysMap:Record<string,number>={"1W":7,"1M":30,"3M":90,"6M":180,"1Y":365,"ALL":10000};
        const days=daysMap[timelineRange];
        const chartData=allChartData.slice(Math.max(0,allChartData.length-days));
        const lastPt=timeline[timeline.length-1];
        const rangeFirst=chartData[0];
        const rangeLast=chartData[chartData.length-1];
        const totalReturn=rangeLast?rangeLast.value-rangeFirst.value:0;
        const totalReturnPct=rangeFirst&&rangeFirst.value>0?((rangeLast.value/rangeFirst.value-1)*100):0;
        return(
        <div>
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-2xl bg-indigo-100 dark:bg-indigo-500/15 flex items-center justify-center"><BarChart3 className="h-5 w-5 text-indigo-600 dark:text-indigo-400" strokeWidth={1.8}/></div>
              <h2 className="text-[16px] font-semibold">Portfolio Timeline</h2>
            </div>
            <div className="sm:ml-auto flex items-center gap-3">
              <span className="text-[13px] text-muted-foreground">Current</span>
              <span className="text-[20px] font-bold tabular-nums font-mono">{formatCurrency(lastPt.value)}</span>
              <span className={`text-[13px] font-semibold ${totalReturn>=0?"text-gain":"text-loss"}`}>{totalReturn>=0?"+":""}{formatCurrency(totalReturn)} ({totalReturnPct>=0?"+":""}{totalReturnPct.toFixed(1)}%)</span>
            </div>
          </div>
          <GlassCard delay={0.47} className="!p-4">
            <div className="flex items-center justify-center gap-1 mb-3">
              {(["1W","1M","3M","6M","1Y","ALL"] as const).map(r=>(
                <button
                  key={r}
                  onClick={()=>setTimelineRange(r)}
                  className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${timelineRange===r?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}
                >{r}</button>
              ))}
            </div>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{top:10,right:10,bottom:0,left:0}}>
                  <defs>
                    <linearGradient id="sg-tl-gain-pub" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22c55e" stopOpacity={0.15}/><stop offset="100%" stopColor="#22c55e" stopOpacity={0}/></linearGradient>
                    <linearGradient id="sg-tl-loss-pub" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ef4444" stopOpacity={0.15}/><stop offset="100%" stopColor="#ef4444" stopOpacity={0}/></linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/>
                  <XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={(d:string)=>d.slice(5)} stroke="var(--muted-foreground)"/>
                  <YAxis yAxisId="value" tick={{fontSize:10}} domain={["auto","auto"]} stroke="var(--muted-foreground)" tickFormatter={(v:number)=>v>=1000?`${(v/1000).toFixed(1)}k`:v.toFixed(0)}/>
                  <YAxis yAxisId="change" orientation="right" tick={{fontSize:9}} stroke="var(--muted-foreground)" tickFormatter={(v:number)=>v>=1000||v<=-1000?`${(v/1000).toFixed(1)}k`:v.toFixed(0)} width={45}/>
                  <Tooltip content={({active,payload,label}:any)=>{
                    if(!active||!payload?.length)return null;
                    const d=payload[0]?.payload;
                    const change=d?.dailyChange??0;
                    return(<div className="bg-popover border border-border rounded-xl p-3 shadow-lg text-[13px] space-y-1 max-w-[260px]">
                      <p className="font-medium">{new Date(String(label)).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"numeric"})}</p>
                      <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">Value</span><span className="font-semibold tabular-nums">{formatCurrency(d?.value??0)}</span></div>
                      <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">Cost</span><span className="tabular-nums">{formatCurrency(d?.cost??0)}</span></div>
                      <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">P&L</span><span className={`font-semibold tabular-nums ${(d?.pnl??0)>=0?"text-gain":"text-loss"}`}>{(d?.pnl??0)>=0?"+":""}{formatCurrency(d?.pnl??0)}</span></div>
                      <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">Day</span><span className={`font-medium tabular-nums ${change>=0?"text-gain":"text-loss"}`}>{change>=0?"+":""}{formatCurrency(change)}</span></div>
                      {d?.tradeLabels&&<div className="pt-1.5 mt-1.5 border-t border-border space-y-0.5">{d.tradeLabels.split("\n").map((line:string,i:number)=><p key={i} className={`text-[12px] font-medium ${line.startsWith("+")?line.includes("Deposit")?"text-blue-500":"text-gain":line.includes("Withdraw")?"text-amber-500":"text-loss"}`}>{line}</p>)}</div>}
                    </div>);
                  }}/>
                  <Bar yAxisId="change" dataKey="gain" fill="#22c55e" opacity={0.5} radius={[2,2,0,0]} barSize={3}/>
                  <Bar yAxisId="change" dataKey="loss" fill="#ef4444" opacity={0.5} radius={[0,0,2,2]} barSize={3}/>
                  <Area yAxisId="value" type="monotone" dataKey="value" stroke={lastPt.pnl>=0?"#22c55e":"#ef4444"} strokeWidth={2} fill={lastPt.pnl>=0?"url(#sg-tl-gain-pub)":"url(#sg-tl-loss-pub)"}/>
                  <Line yAxisId="value" type="monotone" dataKey="cost" stroke="var(--muted-foreground)" strokeWidth={1} strokeDasharray="4 3" dot={false}/>
                  {timeline.filter(pt=>pt.trades&&pt.trades.length>0&&chartData.some(cd=>cd.date===pt.date)).map((pt,i)=>{
                    const t=pt.trades![0];
                    const color=t.symbol==="CASH"?(t.type==="deposit"?"#3b82f6":"#f59e0b"):t.type==="buy"?"#22c55e":"#ef4444";
                    return <ReferenceLine key={`tl-${i}`} yAxisId="value" x={pt.date} stroke={color} strokeDasharray="3 3" strokeWidth={1.5}/>;
                  })}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-wrap items-center gap-4 mt-3 px-1">
              <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-[#22c55e]/70 inline-block"/><span className="text-[11px] text-muted-foreground">Profit</span></div>
              <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-[#ef4444]/70 inline-block"/><span className="text-[11px] text-muted-foreground">Loss</span></div>
              <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-muted-foreground"/><span className="text-[11px] text-muted-foreground">Cost basis</span></div>
              <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#3b82f6]"/><span className="text-[11px] text-muted-foreground">Deposit</span></div>
              <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#f59e0b]"/><span className="text-[11px] text-muted-foreground">Withdraw</span></div>
              <span className="text-[11px] text-muted-foreground ml-auto">Showing {timelineRange==="ALL"?"all history":`last ${timelineRange}`}</span>
            </div>
          </GlassCard>
        </div>);
      })()}

      {/* Transaction History */}
      {trades.length>0&&(
        <div>
          <div className="flex items-center gap-3 mb-5">
            <div className="h-10 w-10 rounded-2xl bg-violet-100 dark:bg-violet-500/15 flex items-center justify-center"><BarChart3 className="h-5 w-5 text-violet-600 dark:text-violet-400" strokeWidth={1.8}/></div>
            <h2 className="text-[16px] font-semibold">Transaction History</h2>
            <span className="text-[13px] text-muted-foreground ml-auto">{trades.length} transactions</span>
          </div>
          <GlassCard delay={0.5} className="!p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Date</th>
                    <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Symbol</th>
                    <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Type</th>
                    <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Qty</th>
                    <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Price</th>
                    <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Fees</th>
                    <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Total (CHF)</th>
                    <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-center">Chart</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map(t=>(
                    <tr key={t.id} className="border-b border-border/50 hover:bg-accent/50 transition-colors">
                      <td className="px-5 py-3 text-[13px] tabular-nums text-muted-foreground">{new Date(t.date).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"numeric"})}</td>
                      <td className="px-5 py-3 text-[14px] font-semibold">{t.symbol}</td>
                      <td className="px-5 py-3"><span className={`text-[12px] px-2.5 py-1 rounded-lg font-semibold uppercase ${t.type==="buy"?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":t.type==="sell"?"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400":t.type==="deposit"?"bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400":"bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"}`}>{t.type}</span></td>
                      <td className="px-5 py-3 text-[13px] tabular-nums text-right">{t.quantity}</td>
                      <td className="px-5 py-3 text-[13px] tabular-nums text-right"><span>{t.price.toFixed(2)}</span>{t.currency!=="CHF"&&<span className="text-[11px] text-muted-foreground ml-1">{t.currency}</span>}</td>
                      <td className="px-5 py-3 text-[13px] tabular-nums text-right text-muted-foreground">{t.fees>0?formatCurrency(t.fees_chf):"—"}</td>
                      <td className="px-5 py-3 text-[14px] font-medium tabular-nums text-right">{formatCurrency(t.total_chf)}</td>
                      <td className="px-5 py-3 text-center">{t.symbol!=="CASH"&&<button onClick={()=>openTradeChart(t.symbol)} className="p-1.5 rounded-lg hover:bg-accent transition-colors cursor-pointer" title={`Chart for ${t.symbol}`}><LineChart className="h-4 w-4 text-primary"/></button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </div>
      )}

      {/* Trade Chart Modal */}
      {tradeChartSymbol&&(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={()=>setTradeChartSymbol(null)}>
          <motion.div initial={{opacity:0,scale:0.95}} animate={{opacity:1,scale:1}} className="glass bg-card rounded-3xl p-6 w-full max-w-2xl mx-4 shadow-2xl" onClick={e=>e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[16px] font-bold flex items-center gap-2"><LineChart className="h-5 w-5 text-primary"/>{tradeChartSymbol} — Price Chart</h3>
              <button onClick={()=>setTradeChartSymbol(null)} className="p-1.5 rounded-lg hover:bg-accent transition-colors cursor-pointer"><X className="h-5 w-5 text-muted-foreground"/></button>
            </div>
            <div className="flex gap-1 mb-3">{RANGES.map(r=><button key={r.value} onClick={()=>setTradeChartRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${tradeChartRange===r.value?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{r.label}</button>)}</div>
            <div className="h-64">
              {tradeChartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:tradeChartData.length===0?<p className="text-[13px] text-muted-foreground text-center py-8">No data available</p>:(
                <ResponsiveContainer width="100%" height="100%"><AreaChart data={tradeChartData}><defs><linearGradient id="sg-tc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2}/><stop offset="100%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={(d:string)=>d.slice(5)} stroke="var(--muted-foreground)"/><YAxis tick={{fontSize:10}} domain={["auto","auto"]} stroke="var(--muted-foreground)"/><Tooltip formatter={(v:any)=>Number(v).toFixed(2)}/><Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#sg-tc)"/></AreaChart></ResponsiveContainer>
              )}
            </div>
          </motion.div>
        </div>
      )}

      <p className="text-center text-[12px] text-muted-foreground pt-4 pb-8">Shared via FinPilot</p>
    </div>
    </div>
  );
}
