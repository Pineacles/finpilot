"use client";

import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import { motion } from "motion/react";
import { api, PublicPortfolio, StockAnalysisEntry, Trade, PortfolioSnapshot, ValueTimelinePoint, PortfolioAnalysis } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell, ReferenceLine, ComposedChart, Line, Bar } from "recharts";
import { TrendingUp, BarChart3, Brain, Zap, AlertTriangle, ArrowUpRight, History, LineChart, X, ChevronDown, ChevronRight, Archive, Activity } from "lucide-react";

const COLORS = ["#3b82f6","#f97316","#ef4444","#a855f7","#14b8a6","#f59e0b","#ec4899","#22c55e","#06b6d4","#8b5cf6","#e11d48","#84cc16","#6366f1","#d946ef","#0ea5e9","#fb923c"];
const RANGES = [{value:"1d",label:"1D"},{value:"5d",label:"1W"},{value:"1mo",label:"1M"},{value:"3mo",label:"3M"},{value:"6mo",label:"6M"},{value:"1y",label:"1Y"},{value:"2y",label:"2Y"},{value:"5y",label:"5Y"}];

function GlassCard({children,className="",delay=0}:{children:React.ReactNode;className?:string;delay?:number}){
  return <motion.div initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{duration:0.45,delay,ease:[0.25,0.46,0.45,0.94]}} className={`glass bg-card rounded-3xl p-6 ${className}`}>{children}</motion.div>;
}
function Sparkline({data,positive}:{data:number[];positive:boolean}){
  if(!data||data.length<2)return null;
  const min=Math.min(...data),max=Math.max(...data),range=max-min||1,h=36,w=90;
  const points=data.map((v,i)=>`${(i/(data.length-1))*w},${h-((v-min)/range)*h}`).join(" ");
  return <svg width={w} height={h} className="shrink-0"><polyline fill="none" stroke={positive?"#3b82f6":"#ff3b30"} strokeWidth="2" points={points}/></svg>;
}
function PnlBadge({value,pct}:{value:number;pct?:number}){
  const pos=value>=0;
  return <span className={`text-[13px] px-2.5 py-1 rounded-xl font-medium inline-flex items-center gap-1 ${pos?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400"}`}>{pos?"+":""}{formatCurrency(value)}{pct!==undefined&&<span className="opacity-70">({pos?"+":""}{pct.toFixed(1)}%)</span>}</span>;
}
function ActionBadge({action,size="md"}:{action:string;size?:"sm"|"md"}){
  const cls=action==="ADD"?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":action==="SELL"?"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400":"bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400";
  const px=size==="sm"?"px-2 py-0.5 text-[11px]":"px-3 py-1 text-[13px]";
  return <span className={`${px} rounded-xl font-semibold ${cls}`}>{action}</span>;
}
function SentimentBadge({sentiment,size="md"}:{sentiment:string;size?:"sm"|"md"}){
  const cls=sentiment==="bullish"?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":sentiment==="bearish"?"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400":"bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400";
  const px=size==="sm"?"px-2 py-0.5 text-[11px]":"px-3 py-1.5 text-[13px]";
  return <span className={`${px} rounded-xl font-semibold capitalize ${cls}`}>{sentiment}</span>;
}
function StockAnalysisDetail({s}:{s:StockAnalysisEntry["stock"]}){
  return(
    <>
      <p className="text-[14px] sm:text-[15px] leading-[1.85] text-foreground/80">{s.rationale}</p>
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
        {s.key_risks.length>0&&<div className="space-y-2"><p className="text-[14px] font-semibold text-loss flex items-center gap-1.5"><AlertTriangle className="h-4 w-4"/>Risks</p><ul className="space-y-1.5">{s.key_risks.map((r,i)=><li key={i} className="text-[13px] sm:text-[14px] text-foreground/70 leading-[1.7] pl-4 relative before:content-[''] before:absolute before:left-0 before:top-2.5 before:w-1.5 before:h-1.5 before:rounded-full before:bg-loss/40">{r}</li>)}</ul></div>}
        {s.key_catalysts.length>0&&<div className="space-y-2"><p className="text-[14px] font-semibold text-gain flex items-center gap-1.5"><Zap className="h-4 w-4"/>Catalysts</p><ul className="space-y-1.5">{s.key_catalysts.map((c,i)=><li key={i} className="text-[13px] sm:text-[14px] text-foreground/70 leading-[1.7] pl-4 relative before:content-[''] before:absolute before:left-0 before:top-2.5 before:w-1.5 before:h-1.5 before:rounded-full before:bg-gain/40">{c}</li>)}</ul></div>}
      </div>
    </>
  );
}
function EconomyDetail({c}:{c:PortfolioAnalysis["content"]}){
  return(
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <SentimentBadge sentiment={c.market_sentiment}/>
      </div>
      <div className="p-5 rounded-2xl bg-accent/60">
        <p className="text-[15px] leading-[1.85] text-foreground/90">{c.market_summary}</p>
      </div>
      {c.key_indicators&&c.key_indicators.length>0&&(
        <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
          {c.key_indicators.map((ind,i)=>(
            <div key={i} className="p-4 rounded-2xl bg-accent/60 text-center">
              <p className="text-[13px] text-muted-foreground mb-1">{ind.name}</p>
              <p className="text-2xl font-bold">{ind.value}</p>
              <p className={`text-[12px] font-medium mt-1 ${ind.trend==="up"?"text-gain":ind.trend==="down"?"text-loss":"text-muted-foreground"}`}>
                {ind.trend==="up"?"Trending up":ind.trend==="down"?"Trending down":"Stable"}
              </p>
            </div>
          ))}
        </div>
      )}
      {c.outlook&&(
        <div className="p-5 rounded-2xl border border-border">
          <p className="text-[14px] font-semibold mb-2">Outlook</p>
          <p className="text-[15px] leading-[1.85] text-foreground/80">{c.outlook}</p>
        </div>
      )}
      {(c.risks?.length||c.opportunities?.length)&&(
        <div className="grid gap-5 md:grid-cols-2">
          {c.risks&&c.risks.length>0&&<div className="space-y-2"><p className="text-[14px] font-semibold text-loss flex items-center gap-1.5"><AlertTriangle className="h-4 w-4"/>Key Risks</p><ul className="space-y-1.5">{c.risks.map((r,i)=><li key={i} className="text-[14px] text-foreground/70 leading-[1.7] pl-4 relative before:content-[''] before:absolute before:left-0 before:top-2.5 before:w-1.5 before:h-1.5 before:rounded-full before:bg-loss/40">{r}</li>)}</ul></div>}
          {c.opportunities&&c.opportunities.length>0&&<div className="space-y-2"><p className="text-[14px] font-semibold text-gain flex items-center gap-1.5"><Zap className="h-4 w-4"/>Opportunities</p><ul className="space-y-1.5">{c.opportunities.map((o,i)=><li key={i} className="text-[14px] text-foreground/70 leading-[1.7] pl-4 relative before:content-[''] before:absolute before:left-0 before:top-2.5 before:w-1.5 before:h-1.5 before:rounded-full before:bg-gain/40">{o}</li>)}</ul></div>}
        </div>
      )}
    </div>
  );
}

function AnimatedNumber({value,format}:{value:number;format:(n:number)=>string}){
  const [display,setDisplay]=useState(value);
  const startRef=useRef(value);
  const startTimeRef=useRef(0);
  const rafRef=useRef<number|undefined>(undefined);
  useEffect(()=>{
    if(value===display)return;
    startRef.current=display;
    startTimeRef.current=performance.now();
    const target=value;
    const start=display;
    const duration=600;
    const tick=(now:number)=>{
      const elapsed=now-startTimeRef.current;
      const t=Math.min(elapsed/duration,1);
      const eased=1-Math.pow(1-t,3);
      setDisplay(start+(target-start)*eased);
      if(t<1)rafRef.current=requestAnimationFrame(tick);
    };
    rafRef.current=requestAnimationFrame(tick);
    return()=>{if(rafRef.current)cancelAnimationFrame(rafRef.current);};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[value]);
  return <>{format(display)}</>;
}

function useScrollableDeck<T extends HTMLElement>(){
  const [el,setEl]=useState<T|null>(null);
  const refCb=useCallback((node:T|null)=>{setEl(node);},[]);
  const [atStart,setAtStart]=useState(true);
  const [atEnd,setAtEnd]=useState(true);
  const updateEdges=useCallback(()=>{
    if(!el)return;
    const start=el.scrollLeft<=1;
    const end=el.scrollLeft+el.clientWidth>=el.scrollWidth-1;
    // Direct DOM update for instant mask change (no React render lag)
    el.classList.toggle("deck-at-start",start);
    el.classList.toggle("deck-at-end",end);
    setAtStart(start);
    setAtEnd(end);
  },[el]);
  useEffect(()=>{
    if(!el)return;
    updateEdges();
    const onScroll=()=>updateEdges();
    el.addEventListener("scroll",onScroll,{passive:true});
    window.addEventListener("resize",updateEdges);
    // Wheel → horizontal scroll (release to page scroll at edges)
    const onWheel=(e:WheelEvent)=>{
      if(Math.abs(e.deltaY)>Math.abs(e.deltaX)&&Math.abs(e.deltaY)>0){
        const atStartNow=el.scrollLeft<=0;
        const atEndNow=el.scrollLeft+el.clientWidth>=el.scrollWidth-1;
        if((e.deltaY>0&&atEndNow)||(e.deltaY<0&&atStartNow))return;
        e.preventDefault();
        el.scrollLeft+=e.deltaY;
      }
    };
    el.addEventListener("wheel",onWheel,{passive:false});
    // Drag-to-scroll
    let isDragging=false;
    let startX=0;
    let startScroll=0;
    let moved=false;
    const onMouseDown=(e:MouseEvent)=>{
      const target=e.target as HTMLElement;
      if(target.closest("button")||target.closest("a")||target.closest("input"))return;
      isDragging=true;
      moved=false;
      startX=e.pageX;
      startScroll=el.scrollLeft;
      el.style.cursor="grabbing";
      e.preventDefault();
    };
    const onMouseMove=(e:MouseEvent)=>{
      if(!isDragging)return;
      const dx=e.pageX-startX;
      if(Math.abs(dx)>3)moved=true;
      el.scrollLeft=startScroll-dx;
    };
    const onMouseUp=()=>{
      if(!isDragging)return;
      isDragging=false;
      el.style.cursor="";
      if(moved){
        const stopClick=(ev:MouseEvent)=>{ev.stopPropagation();ev.preventDefault();window.removeEventListener("click",stopClick,true);};
        window.addEventListener("click",stopClick,true);
      }
    };
    el.addEventListener("mousedown",onMouseDown);
    window.addEventListener("mousemove",onMouseMove);
    window.addEventListener("mouseup",onMouseUp);
    return()=>{
      el.removeEventListener("scroll",onScroll);
      window.removeEventListener("resize",updateEdges);
      el.removeEventListener("wheel",onWheel);
      el.removeEventListener("mousedown",onMouseDown);
      window.removeEventListener("mousemove",onMouseMove);
      window.removeEventListener("mouseup",onMouseUp);
    };
  },[el,updateEdges]);
  const scrollByAmount=useCallback((amount:number)=>{
    el?.scrollBy({left:amount,behavior:"smooth"});
  },[el]);
  return{ref:refCb,atStart,atEnd,updateEdges,scrollByAmount,el};
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
  const [olderSymbol,setOlderSymbol]=useState<string|null>(null);
  const [olderAnalyses,setOlderAnalyses]=useState<StockAnalysisEntry[]>([]);
  const [olderLoading,setOlderLoading]=useState(false);
  const [expandedOlderId,setExpandedOlderId]=useState<string|null>(null);
  const [showPastStocks,setShowPastStocks]=useState(false);
  const [expandedStockCard,setExpandedStockCard]=useState<string|null>(null);
  const [economyHistory,setEconomyHistory]=useState<PortfolioAnalysis[]>([]);
  const [showOlderEconomy,setShowOlderEconomy]=useState(false);
  const [expandedEconomyId,setExpandedEconomyId]=useState<string|null>(null);
  const [trades,setTrades]=useState<Trade[]>([]);
  const [livePrices,setLivePrices]=useState<Record<string,{price:number;change:number;change_pct:number}>>({});
  const [flashes,setFlashes]=useState<Record<string,"up"|"down">>({});
  const prevPricesRef=useRef<Record<string,number>>({});
  const stockDeck=useScrollableDeck<HTMLDivElement>();
  const pastDeck=useScrollableDeck<HTMLDivElement>();
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
    api.publicEconomyHistory(token).then(setEconomyHistory).catch(()=>{});
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
    const i=setInterval(poll,5000);
    return()=>{cancelled=true;clearInterval(i);};
  },[token]);

  const openChart=async(ticker:string,range=chartRange)=>{
    setChartTicker(ticker);setChartRange(range);setChartLoading(true);
    try{const r=await api.publicChart(token,ticker,range);setChartData(r.data);}catch{setChartData([]);}
    finally{setChartLoading(false);}
  };
  useEffect(()=>{if(chartTicker)openChart(chartTicker,chartRange);},[chartRange]);

  useEffect(()=>{
    if(!p)return;
    const t=setTimeout(()=>{stockDeck.updateEdges();pastDeck.updateEdges();},50);
    return()=>clearTimeout(t);
  },[p,stockDeck,pastDeck]);

  const openTradeChart=async(sym:string,range=tradeChartRange)=>{
    setTradeChartSymbol(sym);setTradeChartRange(range);setTradeChartLoading(true);
    try{const r=await api.publicChart(token,sym,range);setTradeChartData(r.data);}catch{setTradeChartData([]);}
    finally{setTradeChartLoading(false);}
  };
  useEffect(()=>{if(tradeChartSymbol)openTradeChart(tradeChartSymbol,tradeChartRange);},[tradeChartRange]);

  const openOlderAnalyses=async(sym:string)=>{
    if(olderSymbol===sym){setOlderSymbol(null);setExpandedOlderId(null);return;}
    setOlderSymbol(sym);setOlderLoading(true);setExpandedOlderId(null);
    api.publicStockAnalyses(token,sym).then(setOlderAnalyses).finally(()=>setOlderLoading(false));
  };

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

  if(loading)return <div className="mx-auto max-w-[1600px] px-8 py-8 space-y-6">{[...Array(4)].map((_,i)=><div key={i} className="h-32 rounded-3xl bg-muted animate-pulse"/>)}</div>;

  if(error||!p)return(
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-2">Portfolio not found</h1>
        <p className="text-muted-foreground">This link may have expired or the portfolio is no longer public.</p>
      </div>
    </div>
  );

  return (
    <div className="mx-auto max-w-[1600px] px-8 py-8 space-y-8">
      <style>{`
  .recharts-brush text { fill: var(--foreground); font-weight: 500; font-size: 11px; }
  .recharts-brush-traveller { fill: var(--accent); }
  .stock-deck::-webkit-scrollbar { height: 8px; }
  .stock-deck::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
  .stock-deck::-webkit-scrollbar-track { background: transparent; }
  @keyframes flash-up { 0% { background-color: rgba(34,197,94,0.25); } 100% { background-color: transparent; } }
  @keyframes flash-down { 0% { background-color: rgba(239,68,68,0.25); } 100% { background-color: transparent; } }
  .flash-up { animation: flash-up 1.5s ease-out; }
  .flash-down { animation: flash-down 1.5s ease-out; }
  .stock-deck { -webkit-mask-image: linear-gradient(to right, transparent 0%, black 4%, black 92%, transparent 100%); mask-image: linear-gradient(to right, transparent 0%, black 4%, black 92%, transparent 100%); cursor: grab; user-select: none; }
  .stock-deck.deck-at-start { -webkit-mask-image: linear-gradient(to right, black 0%, black 92%, transparent 100%); mask-image: linear-gradient(to right, black 0%, black 92%, transparent 100%); }
  .stock-deck.deck-at-end { -webkit-mask-image: linear-gradient(to right, transparent 0%, black 8%, black 100%); mask-image: linear-gradient(to right, transparent 0%, black 8%, black 100%); }
  .stock-deck.deck-at-start.deck-at-end { -webkit-mask-image: none; mask-image: none; cursor: default; }
`}</style>
      {/* Header */}
      <motion.div initial={{opacity:0}} animate={{opacity:1}} className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center"><TrendingUp className="h-3.5 w-3.5 text-primary-foreground"/></div>
            <span className="text-sm font-semibold text-primary">FinPilot</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{p.display_name}&apos;s Portfolio</h1>
          <div className="flex items-center gap-2 mt-2">
            <p className="text-[13px] text-muted-foreground uppercase tracking-wider">Total Value</p>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold tracking-wider">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
              </span>
              LIVE
            </span>
          </div>
          <p className="text-3xl sm:text-4xl font-bold tracking-tight mt-1 tabular-nums"><AnimatedNumber value={liveTotals.value} format={formatCurrency}/></p>
          <div className="flex items-center gap-3 mt-2"><PnlBadge value={liveTotals.pnl} pct={liveTotals.pnlPct}/><span className="text-[13px] text-muted-foreground">all time</span></div>
        </div>
      </motion.div>

      {/* Summary */}
      <div className="grid gap-5 grid-cols-2 lg:grid-cols-4">
        {[
          {l:"Invested",v:formatCurrency(p.total_cost),live:false},
          {l:"Cash",v:formatCurrency(p.cash_balance),live:false},
          {l:"Positions",v:String(p.positions_count),live:false},
          {l:"Total",v:liveTotals.value+p.cash_balance,live:true},
        ].map((item,i)=>(
          <GlassCard key={item.l} delay={0.05+i*0.05}>
            <p className="text-[13px] text-muted-foreground mb-1">{item.l}</p>
            <p className="text-2xl font-semibold tabular-nums">{item.live?<AnimatedNumber value={item.v as number} format={formatCurrency}/>:(item.v as string)}</p>
          </GlassCard>
        ))}
      </div>

      {/* Holdings + Chart */}
      <div className="grid gap-5 grid-cols-1 md:grid-cols-2 lg:grid-cols-5">
        {/* Allocation */}
        <GlassCard delay={0.2} className="md:col-span-1 lg:col-span-1 !p-4">
          <p className="text-[13px] font-medium text-muted-foreground mb-3">Allocation</p>
          {p.positions.length===0?<p className="text-sm text-muted-foreground text-center py-8">No positions</p>:(
            <div className="h-48"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={p.positions} dataKey="market_value" nameKey="symbol" cx="50%" cy="50%" outerRadius={70} innerRadius={42}>{p.positions.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Pie><Tooltip formatter={(v:any)=>formatCurrency(Number(v))}/></PieChart></ResponsiveContainer></div>
          )}
        </GlassCard>

        {/* Holdings */}
        <GlassCard delay={0.25} className="md:col-span-1 lg:col-span-2 !p-4">
          <p className="text-[13px] font-medium text-muted-foreground mb-3">Holdings</p>
          <div className="space-y-1 max-h-[420px] overflow-y-auto pr-1" style={{scrollbarGutter:"stable"}}>
            {p.positions.map(pos=>{
              const live=livePrices[pos.symbol];
              const livePrice=live?.price??pos.last_price??0;
              const livePnlPct=pos.avg_cost_price?((livePrice/pos.avg_cost_price-1)*100):pos.pnl_pct;
              const flash=flashes[pos.symbol];
              return(
              <div key={pos.id} className={`flex items-center justify-between px-3 py-3 pr-4 rounded-2xl cursor-pointer transition-all duration-200 hover:bg-accent ${chartTicker===pos.symbol?"bg-accent":""} ${flash==="up"?"flash-up":flash==="down"?"flash-down":""}`} onClick={()=>openChart(pos.symbol)}>
                <div className="min-w-[70px] shrink-0">
                  <p className="font-semibold text-[15px]">{pos.symbol}</p>
                  <p className="text-[11px] text-muted-foreground truncate max-w-[80px]">{pos.name}</p>
                </div>
                <div className="hidden lg:block shrink-0"><Sparkline data={pos.sparkline} positive={livePnlPct>=0}/></div>
                <div className="text-right shrink-0">
                  <p className="text-[14px] font-medium tabular-nums">{livePrice.toFixed(2)}<span className="text-[10px] text-muted-foreground ml-1">{pos.currency}</span></p>
                  <p className="text-[11px] text-muted-foreground tabular-nums">cost {pos.avg_cost_price.toFixed(2)}</p>
                </div>
                <div className="text-right hidden sm:block shrink-0">
                  <p className="text-[15px] font-semibold tabular-nums">{formatCurrency(pos.market_value)}</p>
                  <p className={`text-[13px] font-semibold tabular-nums ${livePnlPct>=0?"text-gain":"text-loss"}`}>{livePnlPct>=0?"+":""}{livePnlPct.toFixed(1)}%</p>
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
                return <div className="flex items-center justify-center gap-3 mb-3"><span className="text-2xl font-bold tabular-nums">{lp.toFixed(2)}</span><span className={`text-sm font-medium ${lc>=0?"text-gain":"text-loss"}`}>{lc>=0?"+":""}{lc.toFixed(2)} ({lcp>=0?"+":""}{lcp.toFixed(1)}%)</span></div>;
              })()}
              <div className="flex justify-center gap-1 mb-2">{RANGES.map(r=><button key={r.value} onClick={()=>setChartRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${chartRange===r.value?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{r.label}</button>)}</div>
              <div className="h-52">{chartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:chartData.length===0?<p className="text-sm text-muted-foreground">No data</p>:(
                <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{top:5,right:10,left:10,bottom:5}}><defs><linearGradient id="sg-pub" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2}/><stop offset="100%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={(d:string)=>d.slice(5)} stroke="var(--muted-foreground)"/><YAxis hide domain={["auto","auto"]}/><Tooltip formatter={(v:any)=>Number(v).toFixed(2)}/><Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#sg-pub)"/></AreaChart></ResponsiveContainer>
              )}</div>
            </>
          )}
        </GlassCard>
      </div>

      {/* Per-Stock Analysis (currently held) */}
      <div>
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 rounded-2xl bg-orange-100 dark:bg-orange-500/15 flex items-center justify-center"><Brain className="h-5 w-5 text-orange-600 dark:text-orange-400" strokeWidth={1.8}/></div>
          <h2 className="text-lg font-semibold">Stock Analyses</h2>
          <span className="text-[13px] text-muted-foreground">{Object.keys(p.stock_analyses).length} held</span>
        </div>
        {Object.keys(p.stock_analyses).length===0?<GlassCard delay={0.35}><p className="text-muted-foreground py-6 text-center">No stock analyses yet.</p></GlassCard>:(
          <div className="relative">
            <div ref={stockDeck.ref} className={`flex gap-5 overflow-x-auto pb-3 -mx-4 px-4 stock-deck ${stockDeck.atStart?"deck-at-start":""} ${stockDeck.atEnd?"deck-at-end":""}`}>
              {Object.values(p.stock_analyses).map(entry=>{const s=entry.stock;return(
              <GlassCard key={entry.analysis_id} delay={0.35} className="space-y-3 min-w-[400px] max-w-[440px] shrink-0">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-bold">{s.symbol}</span>
                    <ActionBadge action={s.action}/>
                  </div>
                  <div className="text-left sm:text-right">
                    <span className="text-[13px] sm:text-[14px] text-muted-foreground">Entry {s.entry_price.toFixed(2)} / Now {s.current_price.toFixed(2)}</span>
                    <span className={`ml-2 sm:ml-3 text-[14px] sm:text-[15px] font-bold ${s.unrealized_pnl_pct>=0?"text-gain":"text-loss"}`}>{s.unrealized_pnl_pct>=0?"+":""}{s.unrealized_pnl_pct.toFixed(1)}%</span>
                  </div>
                </div>
                <StockAnalysisDetail s={s}/>
                <div className="flex items-center justify-between pt-2 border-t border-border">
                  <span className="text-[12px] text-muted-foreground">{new Date(entry.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"numeric"})}</span>
                  <button onClick={()=>openOlderAnalyses(s.symbol)} className="text-[13px] font-medium text-primary hover:underline cursor-pointer flex items-center gap-1"><History className="h-3.5 w-3.5"/>{olderSymbol===s.symbol?"Hide":"View"} older</button>
                </div>
                {/* Older analyses inline — collapsible */}
                {olderSymbol===s.symbol&&(
                  <div className="pt-3 border-t border-border space-y-2">
                    {olderLoading?<p className="text-[13px] text-muted-foreground">Loading...</p>:olderAnalyses.length<=1?<p className="text-[13px] text-muted-foreground">No older analyses.</p>:olderAnalyses.slice(1).map(older=>{
                      const os=older.stock;
                      const isOpen=expandedOlderId===older.analysis_id;
                      return(
                        <div key={older.analysis_id} className="rounded-2xl border border-border/50 overflow-hidden">
                          <button onClick={()=>setExpandedOlderId(isOpen?null:older.analysis_id)} className="w-full flex items-center justify-between gap-3 p-3 hover:bg-accent/50 cursor-pointer text-left">
                            <div className="flex items-center gap-2 min-w-0 flex-1">
                              {isOpen?<ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0"/>:<ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0"/>}
                              <ActionBadge action={os.action} size="sm"/>
                              <span className={`text-[12px] font-semibold tabular-nums ${os.unrealized_pnl_pct>=0?"text-gain":"text-loss"}`}>{os.unrealized_pnl_pct>=0?"+":""}{os.unrealized_pnl_pct.toFixed(1)}%</span>
                              <span className="text-[11px] text-muted-foreground truncate">{os.rationale.split(".")[0]}</span>
                            </div>
                            <span className="text-[11px] text-muted-foreground shrink-0">{new Date(older.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"2-digit"})}</span>
                          </button>
                          {isOpen&&<div className="p-4 pt-3 border-t border-border/50 bg-accent/20 space-y-3"><p className="text-[12px] text-muted-foreground">Entry {os.entry_price.toFixed(2)} / Now {os.current_price.toFixed(2)}</p><StockAnalysisDetail s={os}/></div>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </GlassCard>
            );})}
            </div>
            {!stockDeck.atEnd&&Object.values(p.stock_analyses).length>2&&<button onClick={()=>stockDeck.scrollByAmount(440)} className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-muted/80 text-muted-foreground border border-border hidden md:flex items-center justify-center cursor-pointer z-10 backdrop-blur-sm" aria-label="Scroll right"><ChevronRight className="h-4 w-4"/></button>}
          </div>
        )}
      </div>

      {/* Past Stocks (sold positions) */}
      {p.past_stock_analyses&&Object.keys(p.past_stock_analyses).length>0&&(
        <div>
          <button onClick={()=>setShowPastStocks(!showPastStocks)} className="flex items-center gap-3 mb-5 cursor-pointer group">
            <div className="h-10 w-10 rounded-2xl bg-slate-100 dark:bg-slate-500/15 flex items-center justify-center"><Archive className="h-5 w-5 text-slate-600 dark:text-slate-400" strokeWidth={1.8}/></div>
            <h2 className="text-lg font-semibold group-hover:text-primary transition-colors">Past Stocks</h2>
            <span className="text-[13px] text-muted-foreground">{Object.keys(p.past_stock_analyses).length} sold</span>
            {showPastStocks?<ChevronDown className="h-5 w-5 text-muted-foreground"/>:<ChevronRight className="h-5 w-5 text-muted-foreground"/>}
          </button>
          {showPastStocks&&(
            <div className="relative">
              <div ref={pastDeck.ref} className={`flex gap-3 overflow-x-auto pb-3 -mx-4 px-4 stock-deck ${pastDeck.atStart?"deck-at-start":""} ${pastDeck.atEnd?"deck-at-end":""}`}>
                {Object.values(p.past_stock_analyses).map(entry=>{
                const s=entry.stock;
                const isOpen=expandedStockCard===entry.analysis_id;
                return(
                  <div key={entry.analysis_id} className="glass bg-card rounded-2xl p-4 space-y-2 min-w-[340px] max-w-[380px] shrink-0">
                    <button onClick={()=>setExpandedStockCard(isOpen?null:entry.analysis_id)} className="w-full flex items-center justify-between gap-3 cursor-pointer text-left">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        {isOpen?<ChevronDown className="h-4 w-4 text-muted-foreground shrink-0"/>:<ChevronRight className="h-4 w-4 text-muted-foreground shrink-0"/>}
                        <span className="text-[15px] font-bold">{s.symbol}</span>
                        <ActionBadge action={s.action} size="sm"/>
                        <span className={`text-[12px] font-semibold tabular-nums ${s.unrealized_pnl_pct>=0?"text-gain":"text-loss"}`}>{s.unrealized_pnl_pct>=0?"+":""}{s.unrealized_pnl_pct.toFixed(1)}%</span>
                      </div>
                      <span className="text-[11px] text-muted-foreground shrink-0">{new Date(entry.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"2-digit"})}</span>
                    </button>
                    {!isOpen&&<p className="text-[12px] text-muted-foreground line-clamp-2 pl-6">{s.rationale}</p>}
                    {isOpen&&(
                      <div className="space-y-3 pt-2 border-t border-border">
                        <p className="text-[12px] text-muted-foreground">Entry {s.entry_price.toFixed(2)} / Last {s.current_price.toFixed(2)}</p>
                        <StockAnalysisDetail s={s}/>
                        <button onClick={(e)=>{e.stopPropagation();openOlderAnalyses(s.symbol);}} className="text-[12px] font-medium text-primary hover:underline cursor-pointer flex items-center gap-1"><History className="h-3.5 w-3.5"/>View all analyses for {s.symbol}</button>
                      </div>
                    )}
                  </div>
                );
              })}
              </div>
              {!pastDeck.atEnd&&Object.values(p.past_stock_analyses).length>2&&<button onClick={()=>pastDeck.scrollByAmount(380)} className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-muted/80 text-muted-foreground border border-border hidden md:flex items-center justify-center cursor-pointer z-10 backdrop-blur-sm" aria-label="Scroll right"><ChevronRight className="h-4 w-4"/></button>}
            </div>
          )}
        </div>
      )}

      {/* Economy Analysis */}
      {p.economy_analysis&&(
        <GlassCard delay={0.4}>
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-2xl bg-blue-100 dark:bg-blue-500/15 flex items-center justify-center"><BarChart3 className="h-5 w-5 text-blue-600 dark:text-blue-400" strokeWidth={1.8}/></div>
              <h2 className="text-lg font-semibold">Economy & Market</h2>
            </div>
            <span className="text-[13px] text-muted-foreground">{new Date(p.economy_analysis.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"numeric"})}</span>
          </div>
          <EconomyDetail c={p.economy_analysis.content}/>
          {/* Older economy analyses */}
          {economyHistory.length>1&&(
            <div className="mt-6 pt-5 border-t border-border">
              <button onClick={()=>setShowOlderEconomy(!showOlderEconomy)} className="flex items-center gap-2 text-[13px] font-medium text-primary hover:underline cursor-pointer">
                {showOlderEconomy?<ChevronDown className="h-4 w-4"/>:<ChevronRight className="h-4 w-4"/>}
                <History className="h-4 w-4"/>
                {showOlderEconomy?"Hide":"View"} {economyHistory.length-1} older analyses
              </button>
              {showOlderEconomy&&(
                <div className="mt-3 space-y-2">
                  {economyHistory.slice(1).map(entry=>{
                    const isOpen=expandedEconomyId===entry.id;
                    return(
                      <div key={entry.id} className="rounded-2xl border border-border overflow-hidden">
                        <button onClick={()=>setExpandedEconomyId(isOpen?null:entry.id)} className="w-full flex items-center justify-between gap-3 p-3 hover:bg-accent/50 cursor-pointer text-left">
                          <div className="flex items-center gap-3 min-w-0 flex-1">
                            {isOpen?<ChevronDown className="h-4 w-4 text-muted-foreground shrink-0"/>:<ChevronRight className="h-4 w-4 text-muted-foreground shrink-0"/>}
                            <SentimentBadge sentiment={entry.content.market_sentiment} size="sm"/>
                            <span className="text-[12px] text-muted-foreground truncate">{entry.content.market_summary?.split(".")[0]}</span>
                          </div>
                          <span className="text-[11px] text-muted-foreground shrink-0">{new Date(entry.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"2-digit"})}</span>
                        </button>
                        {isOpen&&<div className="p-4 pt-3 border-t border-border bg-accent/20"><EconomyDetail c={entry.content}/></div>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </GlassCard>
      )}

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
              <h2 className="text-lg font-semibold">Portfolio Timeline</h2>
            </div>
            <div className="sm:ml-auto flex items-center gap-3">
              <span className="text-[13px] text-muted-foreground">Current</span>
              <span className="text-lg font-bold tabular-nums">{formatCurrency(lastPt.value)}</span>
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
            <div className="h-10 w-10 rounded-2xl bg-violet-100 dark:bg-violet-500/15 flex items-center justify-center"><History className="h-5 w-5 text-violet-600 dark:text-violet-400" strokeWidth={1.8}/></div>
            <h2 className="text-lg font-semibold">Transaction History</h2>
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
              <h3 className="text-lg font-bold flex items-center gap-2"><LineChart className="h-5 w-5 text-primary"/>{tradeChartSymbol} — Price Chart</h3>
              <button onClick={()=>setTradeChartSymbol(null)} className="p-1.5 rounded-lg hover:bg-accent transition-colors cursor-pointer"><X className="h-5 w-5 text-muted-foreground"/></button>
            </div>
            <div className="flex gap-1 mb-3">{RANGES.map(r=><button key={r.value} onClick={()=>setTradeChartRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${tradeChartRange===r.value?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{r.label}</button>)}</div>
            <div className="h-64">
              {tradeChartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:tradeChartData.length===0?<p className="text-sm text-muted-foreground text-center py-8">No data available</p>:(
                <ResponsiveContainer width="100%" height="100%"><AreaChart data={tradeChartData}><defs><linearGradient id="sg-tc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2}/><stop offset="100%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={(d:string)=>d.slice(5)} stroke="var(--muted-foreground)"/><YAxis tick={{fontSize:10}} domain={["auto","auto"]} stroke="var(--muted-foreground)"/><Tooltip formatter={(v:any)=>Number(v).toFixed(2)}/><Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#sg-tc)"/></AreaChart></ResponsiveContainer>
              )}
            </div>
          </motion.div>
        </div>
      )}

      <p className="text-center text-[12px] text-muted-foreground pt-4">Shared via FinPilot</p>
    </div>
  );
}
