"use client";
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { motion } from "motion/react";
import { api, PortfolioSummary, PortfolioAnalysis, StockAnalysisEntry, Trade, ValueTimelinePoint, PostMortem, BuyAssessment, PostMortemInput, BuyAssessmentInput } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell, ReferenceLine, ComposedChart, Line, Bar } from "recharts";
import { Plus, Trash2, Pencil, X, Check, RefreshCw, BarChart3, Brain, Zap, AlertTriangle, ArrowUpRight, Globe, Link2, ClipboardCheck, History, LineChart, ChevronDown, ChevronRight, Archive, BookOpen, Target } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { AnimatedNumber } from "@/components/animated-number";
import { LivePill } from "@/components/live-pill";
import { Sparkline as SparklineChart } from "@/components/sparkline";
import { RangeSwitcher } from "@/components/range-switcher";
import { ActionBadge } from "@/components/action-badge";
import { ConvictionDots } from "@/components/conviction-dots";

const COLORS = ["#3b82f6","#f97316","#ef4444","#a855f7","#14b8a6","#f59e0b","#ec4899","#22c55e","#06b6d4","#8b5cf6","#e11d48","#84cc16","#6366f1","#d946ef","#0ea5e9","#fb923c"];
const RANGES = [{value:"1d",label:"1D"},{value:"5d",label:"1W"},{value:"1mo",label:"1M"},{value:"3mo",label:"3M"},{value:"6mo",label:"6M"},{value:"1y",label:"1Y"},{value:"2y",label:"2Y"},{value:"5y",label:"5Y"}];
const TIMELINE_RANGES = ["1W","1M","3M","6M","1Y","ALL"] as const;

function PnlBadge({value,pct}:{value:number;pct?:number}){
  const pos=value>=0;
  return <span className={`text-[13px] px-2.5 py-1 rounded-xl font-medium inline-flex items-center gap-1 ${pos?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400"}`}>{pos?"+":""}{formatCurrency(value)}{pct!==undefined&&<span className="opacity-70">({pos?"+":""}{pct.toFixed(1)}%)</span>}</span>;
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
      <div className="p-5 rounded-2xl bg-muted/60">
        <p className="text-[15px] leading-[1.85] text-foreground/90">{c.market_summary}</p>
      </div>
      {c.key_indicators&&c.key_indicators.length>0&&(
        <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
          {c.key_indicators.map((ind,i)=>(
            <div key={i} className="p-4 rounded-2xl bg-muted/60 text-center">
              <p className="text-[13px] text-muted-foreground mb-1">{ind.name}</p>
              <p className="font-mono tabular-nums text-[20px] font-bold">{ind.value}</p>
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

export default function PortfolioPage(){
  const [p,setP]=useState<PortfolioSummary|null>(null);
  const [loading,setLoading]=useState(true);
  const [showTrade,setShowTrade]=useState(false);
  const [tradeForm,setTradeForm]=useState({symbol:"",type:"buy",quantity:"",price:"",currency:"USD",date:new Date().toISOString().split("T")[0],fees:"",deduct_from_cash:true});
  const [tradeError,setTradeError]=useState("");
  const [trading,setTrading]=useState(false);
  const [editingId,setEditingId]=useState<string|null>(null);
  const [editForm,setEditForm]=useState({quantity:"",avg_cost_price:""});
  const [chartTicker,setChartTicker]=useState<string|null>(null);
  const [chartRange,setChartRange]=useState("1y");
  const [chartData,setChartData]=useState<{date:string;close:number}[]>([]);
  const [chartLoading,setChartLoading]=useState(false);
  const [historyData,setHistoryData]=useState<{date:string;value:number}[]>([]);
  const [stockAnalyses,setStockAnalyses]=useState<Record<string,StockAnalysisEntry>>({});
  const [pastStockAnalyses,setPastStockAnalyses]=useState<Record<string,StockAnalysisEntry>>({});
  const [showPastStocks,setShowPastStocks]=useState(false);
  const [expandedStockCard,setExpandedStockCard]=useState<string|null>(null);
  const [latestEconomy,setLE]=useState<PortfolioAnalysis|null>(null);
  const [economyHistory,setEconomyHistory]=useState<PortfolioAnalysis[]>([]);
  const [showOlderEconomy,setShowOlderEconomy]=useState(false);
  const [expandedEconomyId,setExpandedEconomyId]=useState<string|null>(null);
  const [olderSymbol,setOlderSymbol]=useState<string|null>(null);
  const [olderAnalyses,setOlderAnalyses]=useState<StockAnalysisEntry[]>([]);
  const [olderLoading,setOlderLoading]=useState(false);
  const [expandedOlderId,setExpandedOlderId]=useState<string|null>(null);
  const [publicEnabled,setPublicEnabled]=useState(false);
  const [publicToken,setPublicToken]=useState<string|null>(null);
  const [publicToggling,setPublicToggling]=useState(false);
  const [copied,setCopied]=useState(false);
  const [trades,setTrades]=useState<Trade[]>([]);
  const [tradesLoading,setTradesLoading]=useState(false);
  const [livePrices,setLivePrices]=useState<Record<string,{price:number;change:number;change_pct:number}>>({});
  const [flashes,setFlashes]=useState<Record<string,"up"|"down">>({});
  const prevPricesRef=useRef<Record<string,number>>({});
  const stockDeck=useScrollableDeck<HTMLDivElement>();
  const pastDeck=useScrollableDeck<HTMLDivElement>();
  const [timeline,setTimeline]=useState<ValueTimelinePoint[]>([]);
  const [tradeChartSymbol,setTradeChartSymbol]=useState<string|null>(null);
  const [tradeChartData,setTradeChartData]=useState<{date:string;close:number}[]>([]);
  const [tradeChartRange,setTradeChartRange]=useState("1y");
  const [tradeChartLoading,setTradeChartLoading]=useState(false);
  const [timelineRange,setTimelineRange]=useState<"1W"|"1M"|"3M"|"6M"|"1Y"|"ALL">("3M");

  // Journal state
  const [postMortems,setPostMortems]=useState<PostMortem[]>([]);
  const [buyAssessments,setBuyAssessments]=useState<BuyAssessment[]>([]);
  const [showPMModal,setShowPMModal]=useState(false);
  const [showBAModal,setShowBAModal]=useState(false);
  const [editingPM,setEditingPM]=useState<PostMortem|null>(null);
  const [editingBA,setEditingBA]=useState<BuyAssessment|null>(null);
  const [pmForm,setPMForm]=useState({symbol:"",entry_price:"",exit_price:"",notes:""});
  const [baForm,setBAForm]=useState({symbol:"",recommendation:"buy" as BuyAssessmentInput["recommendation"],target_price:"",stop_loss:"",thesis:"",risk_factors:"",conviction:"3",time_horizon:"" as BuyAssessmentInput["time_horizon"]|""});
  const [pmSubmitting,setPMSubmitting]=useState(false);
  const [baSubmitting,setBASubmitting]=useState(false);
  const [pmError,setPMError]=useState("");
  const [baError,setBAError]=useState("");
  const [expandedPMId,setExpandedPMId]=useState<string|null>(null);
  const [expandedBAId,setExpandedBAId]=useState<string|null>(null);
  const [deletingPMId,setDeletingPMId]=useState<string|null>(null);
  const [deletingBAId,setDeletingBAId]=useState<string|null>(null);

  const load=useCallback(()=>{
    setLoading(true);
    Promise.all([api.portfolio(),api.portfolioHistory(365),api.analysesByStock(),api.analysisLatest("economy"),api.trades(),api.portfolioValueTimeline(),api.economyHistory(20)]).then(([port,h,sa,ae,tr,tl,eh])=>{
      setP(port);setHistoryData(h);
      if(sa&&typeof sa==="object"){
        setStockAnalyses(sa.current||{});
        setPastStockAnalyses(sa.past||{});
      }
      if(ae&&!("status" in ae&&(ae as any).status==="none"))setLE(ae);
      setTrades(tr);
      setTimeline(tl);
      if(Array.isArray(eh))setEconomyHistory(eh);
    }).finally(()=>setLoading(false));
  },[]);
  useEffect(()=>{
    load();
    api.publicPortfolioStatus().then(s=>{setPublicEnabled(s.enabled);setPublicToken(s.token);}).catch(()=>{});
    api.postMortems().then(setPostMortems).catch(()=>{});
    api.buyAssessments().then(setBuyAssessments).catch(()=>{});
  },[load]);
  useEffect(()=>{const i=setInterval(load,120000);return()=>clearInterval(i);},[load]);
  useEffect(()=>{
    // Recompute edge states when content changes
    const t=setTimeout(()=>{stockDeck.updateEdges();pastDeck.updateEdges();},50);
    return()=>clearTimeout(t);
  },[stockAnalyses,pastStockAnalyses,stockDeck,pastDeck]);

  // Live ticker polling — fetch fresh prices every 5 seconds and animate changes
  useEffect(()=>{
    let cancelled=false;
    const poll=async()=>{
      try{
        const data=await api.livePrices();
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
  },[]);

  const openChart=async(ticker:string,range=chartRange)=>{
    setChartTicker(ticker);setChartRange(range);setChartLoading(true);
    try{const r=await api.priceChart(ticker,range);setChartData(r.data);}catch{setChartData([]);}
    finally{setChartLoading(false);}
  };
  useEffect(()=>{if(chartTicker)openChart(chartTicker,chartRange);},[chartRange]);
  useEffect(()=>{if(!chartTicker&&p?.positions.length)openChart(p.positions[0].symbol);},[p?.positions.length]);

  const handleTrade=async()=>{
    const f=tradeForm;if(!f.quantity||(f.type!=="deposit"&&f.type!=="withdraw"&&!f.symbol))return;
    setTrading(true);setTradeError("");
    try{await api.trade({symbol:f.type==="deposit"||f.type==="withdraw"?"CASH":f.symbol.toUpperCase().trim(),type:f.type,quantity:parseFloat(f.quantity),price:f.price?parseFloat(f.price):undefined,currency:f.currency,date:f.date||undefined,fees:f.fees?parseFloat(f.fees):0,deduct_from_cash:f.deduct_from_cash});
    setTradeForm({symbol:"",type:"buy",quantity:"",price:"",currency:"USD",date:new Date().toISOString().split("T")[0],fees:"",deduct_from_cash:true});setShowTrade(false);load();}
    catch(e){setTradeError(e instanceof Error?e.message:"Trade failed");}finally{setTrading(false);}
  };
  const handleUpdate=async(id:string)=>{await api.updatePosition(id,{quantity:editForm.quantity?parseFloat(editForm.quantity):undefined,avg_cost_price:editForm.avg_cost_price?parseFloat(editForm.avg_cost_price):undefined});setEditingId(null);load();};
  const handleDelete=async(id:string)=>{await api.deletePosition(id);load();};
  const openOlderAnalyses=async(sym:string)=>{setOlderSymbol(sym);setOlderLoading(true);setExpandedOlderId(null);api.stockAnalyses(sym).then(setOlderAnalyses).finally(()=>setOlderLoading(false));};
  const openTradeChart=async(sym:string,range=tradeChartRange)=>{
    setTradeChartSymbol(sym);setTradeChartRange(range);setTradeChartLoading(true);
    try{const r=await api.priceChart(sym,range);setTradeChartData(r.data);}catch{setTradeChartData([]);}
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

  const pnlUp=(p?.total_pnl??0)>=0;

  if(loading&&!p)return <div className="space-y-6">{[...Array(4)].map((_,i)=><div key={i} className="h-32 rounded-3xl bg-muted animate-pulse"/>)}</div>;

  return (
    <div className="space-y-8">
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
          <div className="flex items-center gap-2">
            <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-[0.5px]">Total Value</p>
            <LivePill/>
          </div>
          <p className="font-mono tabular-nums text-[42px] font-extrabold" style={{letterSpacing: '-1.2px'}}><AnimatedNumber value={liveTotals.value} format={formatCurrency}/></p>
          <div className="flex items-center gap-3 mt-2"><PnlBadge value={liveTotals.pnl} pct={liveTotals.pnlPct}/><span className="text-[13px] text-muted-foreground">all-time P&L</span></div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Public toggle */}
          <div className="flex items-center gap-2 mr-2">
            <button
              disabled={publicToggling}
              onClick={async()=>{setPublicToggling(true);try{const r=await api.publicPortfolioToggle();setPublicEnabled(r.enabled);setPublicToken(r.token);setCopied(false);}finally{setPublicToggling(false);}}}
              className={`relative h-7 w-12 rounded-full transition-colors cursor-pointer ${publicEnabled?"bg-primary":"bg-muted"}`}
            >
              <span className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${publicEnabled?"translate-x-5":"translate-x-0"}`}/>
            </button>
            <Globe className={`h-4 w-4 ${publicEnabled?"text-primary":"text-muted-foreground"}`}/>
            {publicEnabled&&publicToken&&(
              <button
                onClick={()=>{navigator.clipboard.writeText(`${window.location.origin}/p/${publicToken}`);setCopied(true);setTimeout(()=>setCopied(false),2000);}}
                className="h-8 px-3 rounded-xl bg-accent text-[13px] font-medium flex items-center gap-1.5 hover:bg-muted transition-colors cursor-pointer font-sans"
              >
                {copied?<><ClipboardCheck className="h-3.5 w-3.5 text-gain"/>Copied</>:<><Link2 className="h-3.5 w-3.5"/>Copy link</>}
              </button>
            )}
          </div>
          <button onClick={load} disabled={loading} className="h-10 w-10 rounded-xl bg-muted flex items-center justify-center hover:bg-muted/80 transition-colors cursor-pointer"><RefreshCw className={`h-4 w-4 ${loading?"animate-spin":""}`}/></button>
          <Button onClick={()=>setShowTrade(true)} className="rounded-[14px] h-auto px-5 py-3 text-[14px] font-semibold" style={{boxShadow:'0 10px 24px -10px rgba(59,130,246,0.4)'}}><Plus className="h-4 w-4 mr-1.5"/>New Trade</Button>
        </div>
      </motion.div>

      {/* KPI Row */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        {[
          {l:"Invested",v:p?.total_cost??0,fmt:formatCurrency,pct:undefined as number|undefined},
          {l:"Cash",v:p?.cash_balance??0,fmt:formatCurrency,pct:undefined},
          {l:"Positions",v:p?.positions_count??0,fmt:(n:number)=>String(Math.round(n)),pct:undefined},
          {l:"Day P&L",v:liveTotals.pnl,fmt:formatCurrency,pct:liveTotals.pnlPct},
        ].map((item,i)=>(
          <GlassCard key={item.l} delay={0.05+i*0.05} className="!rounded-[20px] !p-[18px]">
            <p className="text-[12px] text-muted-foreground mb-1.5 uppercase tracking-wider font-medium">{item.l}</p>
            <p className={`font-mono tabular-nums text-[20px] font-bold ${item.l==="Day P&L"?(item.v>=0?"text-gain":"text-loss"):""}`}>
              <AnimatedNumber value={item.v} format={item.fmt}/>
            </p>
            {item.pct!==undefined&&<p className={`text-[12px] tabular-nums mt-0.5 ${item.pct>=0?"text-gain":"text-loss"}`}>{item.pct>=0?"+":""}{item.pct.toFixed(2)}%</p>}
          </GlassCard>
        ))}
      </div>

      {/* Holdings + Chart */}
      <div className="grid gap-5 grid-cols-1 md:grid-cols-2 lg:grid-cols-5">
        {/* Allocation */}
        <GlassCard delay={0.2} className="md:col-span-1 lg:col-span-1 !p-4">
          <p className="text-[13px] font-medium text-muted-foreground mb-3">Allocation</p>
          {(p?.positions.length??0)===0?<p className="text-[13px] text-muted-foreground text-center py-8">No positions</p>:(
            <div className="h-48"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={p!.positions} dataKey="market_value" nameKey="symbol" cx="50%" cy="50%" outerRadius={70} innerRadius={42}>{p!.positions.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Pie><Tooltip formatter={(v:any)=>formatCurrency(Number(v))}/></PieChart></ResponsiveContainer></div>
          )}
        </GlassCard>

        {/* Holdings */}
        <GlassCard delay={0.25} className="md:col-span-1 lg:col-span-2 !p-4">
          <p className="text-[14px] font-semibold text-muted-foreground mb-3">Holdings</p>
          <div className="space-y-1 max-h-[420px] overflow-y-auto pr-1" style={{scrollbarGutter:"stable"}}>
            {(p?.positions??[]).map(pos=>{
              const live=livePrices[pos.symbol];
              const livePrice=live?.price??pos.last_price??0;
              const liveChange=live?.change??pos.change;
              const liveChangePct=live?.change_pct??pos.change_pct;
              const livePnlPct=pos.avg_cost_price?((livePrice/pos.avg_cost_price-1)*100):pos.pnl_pct;
              const flash=flashes[pos.symbol];
              return(
              editingId===pos.id?(
                <div key={pos.id} className="flex items-center gap-2 p-3 rounded-[14px] bg-muted flex-wrap"><span className="font-bold text-[14px] w-14">{pos.symbol}</span><Input value={editForm.quantity} onChange={e=>setEditForm({...editForm,quantity:e.target.value})} className="h-8 w-16 text-[13px] rounded-[14px]" placeholder="Qty"/><Input value={editForm.avg_cost_price} onChange={e=>setEditForm({...editForm,avg_cost_price:e.target.value})} className="h-8 w-20 text-[13px] rounded-[14px]" placeholder="Price"/><button onClick={()=>handleUpdate(pos.id)} className="cursor-pointer"><Check className="h-4 w-4 text-gain"/></button><button onClick={()=>setEditingId(null)} className="cursor-pointer"><X className="h-4 w-4 text-muted-foreground"/></button></div>
              ):(
                <div key={pos.id} className={`flex items-center justify-between px-3.5 py-3 pr-4 rounded-[14px] cursor-pointer transition-all duration-200 group hover:bg-accent ${chartTicker===pos.symbol?"bg-accent":""} ${flash==="up"?"flash-up":flash==="down"?"flash-down":""}`} onClick={()=>openChart(pos.symbol)}>
                  <div className="min-w-[70px] shrink-0">
                    <p className="font-bold text-[14px]">{pos.symbol}</p>
                    <p className="text-[11px] text-muted-foreground truncate max-w-[80px]">{pos.name}</p>
                  </div>
                  <div className="hidden lg:block shrink-0"><SparklineChart data={pos.sparkline||[]} color={livePnlPct>=0?"#3b82f6":"#ff3b30"} width={90} height={36}/></div>
                  <div className="text-right shrink-0">
                    <p className="font-mono tabular-nums text-[13px] font-semibold">{livePrice.toFixed(2)}<span className="text-[11px] text-muted-foreground ml-1">{pos.currency}</span></p>
                    <p className="font-mono tabular-nums text-[11px] text-muted-foreground">{pos.quantity} shares · cost {pos.avg_cost_price.toFixed(2)}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <div className="text-right hidden sm:block">
                      <p className="font-mono tabular-nums text-[13px] font-semibold">{formatCurrency(pos.market_value)}</p>
                      <p className={`font-mono tabular-nums text-[11px] font-semibold ${livePnlPct>=0?"text-gain":"text-loss"}`}>{livePnlPct>=0?"+":""}{livePnlPct.toFixed(1)}%</p>
                      <p className={`text-[11px] tabular-nums ${pos.unrealized_pnl>=0?"text-gain":"text-loss"}`}>{pos.unrealized_pnl>=0?"+":""}{formatCurrency(pos.unrealized_pnl)}</p>
                      {pos.first_bought&&<p className="text-[10px] text-muted-foreground mt-0.5">since {new Date(pos.first_bought).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"2-digit"})}</p>}
                    </div>
                    <div className="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e=>e.stopPropagation()}>
                      <button className="cursor-pointer p-1 rounded-lg hover:bg-background" onClick={()=>{setEditingId(pos.id);setEditForm({quantity:String(pos.quantity),avg_cost_price:String(pos.avg_cost_price)});}}><Pencil className="h-3.5 w-3.5 text-muted-foreground"/></button>
                      <button className="cursor-pointer p-1 rounded-lg hover:bg-background" onClick={()=>handleDelete(pos.id)}><Trash2 className="h-3.5 w-3.5 text-muted-foreground"/></button>
                    </div>
                  </div>
                </div>
              ));
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
                const pos=p?.positions.find(pp=>pp.symbol===chartTicker);
                if(!pos)return null;
                const live=livePrices[pos.symbol];
                const lp=live?.price??pos.last_price??0;
                const lc=live?.change??pos.change;
                const lcp=live?.change_pct??pos.change_pct;
                return <div className="flex items-center justify-center gap-3 mb-3"><span className="font-mono tabular-nums text-[20px] font-bold">{lp.toFixed(2)}</span><span className={`text-[13px] font-semibold ${lc>=0?"text-gain":"text-loss"}`}>{lc>=0?"+":""}{lc.toFixed(2)} ({lcp>=0?"+":""}{lcp.toFixed(1)}%)</span></div>;
              })()}
              <div className="flex justify-center mb-2"><RangeSwitcher ranges={RANGES.map(r=>r.label)} active={RANGES.find(r=>r.value===chartRange)?.label||"1Y"} onChange={lbl=>{const r=RANGES.find(x=>x.label===lbl);if(r)setChartRange(r.value);}}/></div>
              <div className="h-52">{chartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:chartData.length===0?<p className="text-[13px] text-muted-foreground">No data</p>:(
                <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{top:5,right:10,left:10,bottom:5}}><defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2}/><stop offset="100%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={d=>d.slice(5)} stroke="var(--muted-foreground)"/><YAxis hide domain={["auto","auto"]}/><Tooltip formatter={(v:any)=>Number(v).toFixed(2)}/><Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#sg)"/></AreaChart></ResponsiveContainer>
              )}</div>
            </>
          )}
        </GlassCard>
      </div>

      {/* Per-Stock Analysis (currently held) */}
      <div>
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 rounded-2xl bg-orange-100 dark:bg-orange-500/15 flex items-center justify-center"><Brain className="h-5 w-5 text-orange-600 dark:text-orange-400" strokeWidth={1.8}/></div>
          <h2 className="text-[16px] font-semibold">Stock Analyses</h2>
          <span className="text-[13px] text-muted-foreground">{Object.keys(stockAnalyses).length} held</span>
        </div>
        {Object.keys(stockAnalyses).length===0?<GlassCard delay={0.35}><p className="text-muted-foreground py-6 text-center">No stock analyses yet. Your agent will store reports here.</p></GlassCard>:(
          <div className="relative">
            <div ref={stockDeck.ref} className={`flex gap-5 overflow-x-auto pb-3 -mx-4 px-4 stock-deck ${stockDeck.atStart?"deck-at-start":""} ${stockDeck.atEnd?"deck-at-end":""}`}>
              {Object.values(stockAnalyses).map(entry=>{const s=entry.stock;return(
              <GlassCard key={entry.analysis_id} delay={0.35} className="space-y-3 min-w-[400px] max-w-[440px] shrink-0">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <span className="text-[16px] font-bold">{s.symbol}</span>
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
                  <button onClick={()=>openOlderAnalyses(s.symbol)} className="text-[13px] font-medium text-primary hover:underline cursor-pointer flex items-center gap-1"><History className="h-3.5 w-3.5"/>View older</button>
                </div>
              </GlassCard>
            );})}
            </div>
            {!stockDeck.atEnd&&Object.values(stockAnalyses).length>2&&<button onClick={()=>stockDeck.scrollByAmount(440)} className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-muted/80 text-muted-foreground border border-border hidden md:flex items-center justify-center cursor-pointer z-10 backdrop-blur-sm" aria-label="Scroll right"><ChevronRight className="h-4 w-4"/></button>}
          </div>
        )}
      </div>

      {/* Past Stocks (sold positions) */}
      {Object.keys(pastStockAnalyses).length>0&&(
        <div>
          <button onClick={()=>setShowPastStocks(!showPastStocks)} className="flex items-center gap-3 mb-5 cursor-pointer group">
            <div className="h-10 w-10 rounded-2xl bg-slate-100 dark:bg-slate-500/15 flex items-center justify-center"><Archive className="h-5 w-5 text-slate-600 dark:text-slate-400" strokeWidth={1.8}/></div>
            <h2 className="text-[16px] font-semibold group-hover:text-primary transition-colors">Past Stocks</h2>
            <span className="text-[13px] text-muted-foreground">{Object.keys(pastStockAnalyses).length} sold</span>
            {showPastStocks?<ChevronDown className="h-5 w-5 text-muted-foreground"/>:<ChevronRight className="h-5 w-5 text-muted-foreground"/>}
          </button>
          {showPastStocks&&(
            <div className="relative">
              <div ref={pastDeck.ref} className={`flex gap-3 overflow-x-auto pb-3 -mx-4 px-4 stock-deck ${pastDeck.atStart?"deck-at-start":""} ${pastDeck.atEnd?"deck-at-end":""}`}>
                {Object.values(pastStockAnalyses).map(entry=>{
                const s=entry.stock;
                const isOpen=expandedStockCard===entry.analysis_id;
                return(
                  <div key={entry.analysis_id} className="glass bg-card rounded-2xl p-4 space-y-2 min-w-[340px] max-w-[380px] shrink-0">
                    <button onClick={()=>setExpandedStockCard(isOpen?null:entry.analysis_id)} className="w-full flex items-center justify-between gap-3 cursor-pointer text-left">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        {isOpen?<ChevronDown className="h-4 w-4 text-muted-foreground shrink-0"/>:<ChevronRight className="h-4 w-4 text-muted-foreground shrink-0"/>}
                        <span className="text-[15px] font-bold">{s.symbol}</span>
                        <ActionBadge action={s.action} className="text-[10px] px-2 py-0.5"/>
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
              {!pastDeck.atEnd&&Object.values(pastStockAnalyses).length>2&&<button onClick={()=>pastDeck.scrollByAmount(380)} className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-muted/80 text-muted-foreground border border-border hidden md:flex items-center justify-center cursor-pointer z-10 backdrop-blur-sm" aria-label="Scroll right"><ChevronRight className="h-4 w-4"/></button>}
            </div>
          )}
        </div>
      )}

      {/* Older Analyses Dialog — collapsed summaries that expand on click */}
      <Dialog open={olderSymbol!==null} onOpenChange={open=>{if(!open){setOlderSymbol(null);setExpandedOlderId(null);}}}>
        <DialogContent className="rounded-3xl max-w-4xl max-h-[85vh] overflow-hidden p-0 flex flex-col">
          <DialogHeader className="px-6 pt-6 pb-2 shrink-0"><DialogTitle>Analysis History — {olderSymbol}</DialogTitle></DialogHeader>
          <div className="overflow-y-auto px-6 pb-6 flex-1">
            {olderLoading?<div className="py-8 text-center text-muted-foreground">Loading...</div>:olderAnalyses.length===0?<p className="py-8 text-center text-muted-foreground">No analyses found.</p>:(
              <div className="space-y-2">
                {olderAnalyses.map(entry=>{
                  const s=entry.stock;
                  const isOpen=expandedOlderId===entry.analysis_id;
                  return(
                    <div key={entry.analysis_id} className="rounded-2xl border border-border overflow-hidden">
                      <button onClick={()=>setExpandedOlderId(isOpen?null:entry.analysis_id)} className="w-full flex items-center justify-between gap-3 p-3 hover:bg-accent/50 cursor-pointer text-left">
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          {isOpen?<ChevronDown className="h-4 w-4 text-muted-foreground shrink-0"/>:<ChevronRight className="h-4 w-4 text-muted-foreground shrink-0"/>}
                          <ActionBadge action={s.action} className="text-[10px] px-2 py-0.5"/>
                          <span className={`text-[13px] font-semibold tabular-nums ${s.unrealized_pnl_pct>=0?"text-gain":"text-loss"}`}>{s.unrealized_pnl_pct>=0?"+":""}{s.unrealized_pnl_pct.toFixed(1)}%</span>
                          <span className="text-[12px] text-muted-foreground truncate">{s.rationale.split(".")[0]}</span>
                        </div>
                        <span className="text-[11px] text-muted-foreground shrink-0">{new Date(entry.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"2-digit"})}</span>
                      </button>
                      {isOpen&&(
                        <div className="p-4 pt-3 border-t border-border bg-accent/20 space-y-3">
                          <p className="text-[12px] text-muted-foreground">Entry {s.entry_price.toFixed(2)} / Now {s.current_price.toFixed(2)}</p>
                          <StockAnalysisDetail s={s}/>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Economy Analysis */}
      <GlassCard delay={0.4}>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-2xl bg-blue-100 dark:bg-blue-500/15 flex items-center justify-center"><BarChart3 className="h-5 w-5 text-blue-600 dark:text-blue-400" strokeWidth={1.8}/></div>
            <h2 className="text-[16px] font-semibold">Economy & Market</h2>
          </div>
          {latestEconomy && <span className="text-[13px] text-muted-foreground">{new Date(latestEconomy.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"numeric"})}</span>}
        </div>
        {!latestEconomy?<p className="text-muted-foreground py-6 text-center">No economy analysis yet.</p>:<EconomyDetail c={latestEconomy.content}/>}
        {/* Older economy analyses — collapsed summaries */}
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

      {/* Portfolio Timeline — unified chart with range presets, P&L bars, and all transaction markers */}
      {timeline.length>0&&(()=>{
        const allChartData=timeline.map((pt,i)=>{
          const prev=i>0?timeline[i-1]:pt;
          const dailyChange=pt.value-prev.value;
          const tradeLabels=pt.trades?.map(t=>{
            if(t.symbol==="CASH")return `${t.type==="deposit"?"+ Deposit":"- Withdraw"} ${formatCurrency(t.quantity)}`;
            return `${t.type==="buy"?"+ Buy":"- Sell"} ${t.quantity} ${t.symbol} @ ${t.price.toFixed(2)}`;
          }).join("\n")||null;
          return {date:pt.date,value:pt.value,cost:pt.cost,pnl:pt.pnl,dailyChange,gain:dailyChange>=0?dailyChange:0,loss:dailyChange<0?dailyChange:0,tradeLabels,hasTrades:!!pt.trades?.length,trades:pt.trades};
        });
        // Filter by range preset — slice from the end to get the last N days
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
          <GlassCard delay={0.42} className="!p-4">
            <div className="flex justify-center mb-3">
              <RangeSwitcher ranges={[...TIMELINE_RANGES]} active={timelineRange} onChange={r=>setTimelineRange(r as typeof timelineRange)}/>
            </div>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{top:10,right:10,bottom:0,left:0}}>
                  <defs>
                    <linearGradient id="sg-tl-gain" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22c55e" stopOpacity={0.15}/><stop offset="100%" stopColor="#22c55e" stopOpacity={0}/></linearGradient>
                    <linearGradient id="sg-tl-loss" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ef4444" stopOpacity={0.15}/><stop offset="100%" stopColor="#ef4444" stopOpacity={0}/></linearGradient>
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
                  {/* Daily change bars */}
                  <Bar yAxisId="change" dataKey="gain" fill="#22c55e" opacity={0.5} radius={[2,2,0,0]} barSize={3}/>
                  <Bar yAxisId="change" dataKey="loss" fill="#ef4444" opacity={0.5} radius={[0,0,2,2]} barSize={3}/>
                  {/* Value area */}
                  <Area yAxisId="value" type="monotone" dataKey="value" stroke={lastPt.pnl>=0?"#22c55e":"#ef4444"} strokeWidth={2} fill={lastPt.pnl>=0?"url(#sg-tl-gain)":"url(#sg-tl-loss)"}/>
                  {/* Cost basis line */}
                  <Line yAxisId="value" type="monotone" dataKey="cost" stroke="var(--muted-foreground)" strokeWidth={1} strokeDasharray="4 3" dot={false}/>
                  {/* Transaction markers — only show if within filtered range */}
                  {timeline.filter(pt=>pt.trades&&pt.trades.length>0&&chartData.some(cd=>cd.date===pt.date)).map((pt,i)=>{
                    const t=pt.trades![0];
                    const color=t.symbol==="CASH"?(t.type==="deposit"?"#3b82f6":"#f59e0b"):t.type==="buy"?"#22c55e":"#ef4444";
                    return <ReferenceLine key={`tl-${i}`} yAxisId="value" x={pt.date} stroke={color} strokeDasharray="3 3" strokeWidth={1.5}/>;
                  })}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            {/* Legend */}
            <div className="flex flex-wrap items-center gap-4 mt-3 px-1">
              <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-[#22c55e]/70 inline-block"/><span className="text-[11px] text-muted-foreground">Profit</span></div>
              <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-[#ef4444]/70 inline-block"/><span className="text-[11px] text-muted-foreground">Loss</span></div>
              <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-muted-foreground"/><span className="text-[11px] text-muted-foreground">Cost basis</span></div>
              <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#22c55e]"/><span className="text-[11px] text-muted-foreground">Buy</span></div>
              <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#ef4444]"/><span className="text-[11px] text-muted-foreground">Sell</span></div>
              <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#3b82f6]"/><span className="text-[11px] text-muted-foreground">Deposit</span></div>
              <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#f59e0b]"/><span className="text-[11px] text-muted-foreground">Withdraw</span></div>
              <span className="text-[11px] text-muted-foreground ml-auto">Showing {timelineRange==="ALL"?"all history":`last ${timelineRange}`}</span>
            </div>
          </GlassCard>
        </div>);
      })()}

      {/* Buy Assessments */}
      <div>
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 rounded-2xl bg-emerald-100 dark:bg-emerald-500/15 flex items-center justify-center"><Target className="h-5 w-5 text-emerald-600 dark:text-emerald-400" strokeWidth={1.8}/></div>
          <h2 className="text-[16px] font-semibold">Buy Assessments</h2>
          <span className="text-[12px] px-2 py-0.5 rounded-full bg-accent text-muted-foreground font-medium">{buyAssessments.length}</span>
          <button onClick={()=>{setEditingBA(null);setBAForm({symbol:"",recommendation:"buy",target_price:"",stop_loss:"",thesis:"",risk_factors:"",conviction:"3",time_horizon:""});setBAError("");setShowBAModal(true);}} className="ml-auto p-2 rounded-xl bg-accent hover:bg-accent/80 transition-colors cursor-pointer"><Plus className="h-4 w-4"/></button>
        </div>
        {buyAssessments.length===0?(
          <GlassCard delay={0.43}><p className="text-muted-foreground py-6 text-center text-[14px]">No buy assessments yet — the agent will write these for you.</p></GlassCard>
        ):(
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {buyAssessments.map(ba=>{
              const recColor=ba.recommendation==="buy"?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":ba.recommendation==="hold"?"bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400":ba.recommendation==="watch"?"bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400":"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400";
              const isExpanded=expandedBAId===ba.id;
              return(
                <GlassCard key={ba.id} delay={0} className="relative group !p-4 flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[16px] font-bold">{ba.symbol}</span>
                      <span className={`text-[12px] px-2.5 py-0.5 rounded-full font-semibold capitalize ${recColor}`}>{ba.recommendation}</span>
                      {ba.time_horizon&&<span className="text-[11px] px-2 py-0.5 rounded-full bg-accent text-muted-foreground capitalize">{ba.time_horizon}</span>}
                    </div>
                    <div className="hidden group-hover:flex items-center gap-1 shrink-0">
                      <button onClick={()=>{setEditingBA(ba);setBAForm({symbol:ba.symbol,recommendation:ba.recommendation,target_price:ba.target_price?.toString()||"",stop_loss:ba.stop_loss?.toString()||"",thesis:ba.thesis,risk_factors:ba.risk_factors||"",conviction:String(ba.conviction),time_horizon:ba.time_horizon||""});setBAError("");setShowBAModal(true);}} className="p-1.5 rounded-lg hover:bg-accent transition-colors cursor-pointer"><Pencil className="h-3.5 w-3.5 text-muted-foreground"/></button>
                      {deletingBAId===ba.id?(
                        <button onClick={async()=>{await api.deleteBuyAssessment(ba.id);setBuyAssessments(p=>p.filter(x=>x.id!==ba.id));setDeletingBAId(null);}} className="px-2 py-1 text-[11px] rounded-lg bg-rose-500 text-white font-medium cursor-pointer">Confirm</button>
                      ):(
                        <button onClick={()=>setDeletingBAId(ba.id)} className="p-1.5 rounded-lg hover:bg-accent transition-colors cursor-pointer"><Trash2 className="h-3.5 w-3.5 text-muted-foreground"/></button>
                      )}
                    </div>
                  </div>
                  {(ba.target_price||ba.stop_loss)&&(
                    <div className="flex items-center gap-3 text-[12px] text-muted-foreground">
                      {ba.target_price&&<span>Target: <span className="text-foreground font-medium">{ba.target_price.toFixed(2)}</span></span>}
                      {ba.stop_loss&&<span>Stop: <span className="text-foreground font-medium">{ba.stop_loss.toFixed(2)}</span></span>}
                    </div>
                  )}
                  <div className="flex items-center gap-1.5">
                    <ConvictionDots level={ba.conviction}/>
                    <span className="text-[11px] text-muted-foreground">conviction</span>
                  </div>
                  <div>
                    <p className={`text-[13px] text-foreground/80 leading-[1.7] ${isExpanded?"":"line-clamp-3"}`}>{ba.thesis}</p>
                    {ba.thesis.length>120&&<button onClick={()=>setExpandedBAId(isExpanded?null:ba.id)} className="text-[12px] text-primary hover:underline cursor-pointer mt-0.5">{isExpanded?"Show less":"Show more"}</button>}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-auto">{new Date(ba.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"numeric"})}</p>
                </GlassCard>
              );
            })}
          </div>
        )}
      </div>

      {/* Post-Mortems */}
      <div>
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 rounded-2xl bg-rose-100 dark:bg-rose-500/15 flex items-center justify-center"><BookOpen className="h-5 w-5 text-rose-600 dark:text-rose-400" strokeWidth={1.8}/></div>
          <h2 className="text-[16px] font-semibold">Post-Mortems</h2>
          <span className="text-[12px] px-2 py-0.5 rounded-full bg-accent text-muted-foreground font-medium">{postMortems.length}</span>
          <button onClick={()=>{setEditingPM(null);setPMForm({symbol:"",entry_price:"",exit_price:"",notes:""});setPMError("");setShowPMModal(true);}} className="ml-auto p-2 rounded-xl bg-accent hover:bg-accent/80 transition-colors cursor-pointer"><Plus className="h-4 w-4"/></button>
        </div>
        {postMortems.length===0?(
          <GlassCard delay={0.44}><p className="text-muted-foreground py-6 text-center text-[14px]">No post-mortems yet — the agent writes these when a position is closed.</p></GlassCard>
        ):(
          <div className="space-y-3">
            {postMortems.map(pm=>{
              const isPos=pm.pnl_pct>=0;
              const isExpanded=expandedPMId===pm.id;
              return(
                <GlassCard key={pm.id} delay={0} className="relative group !p-4 flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[15px] font-bold">{pm.symbol}</span>
                      <span className={`text-[12px] px-2.5 py-0.5 rounded-full font-semibold ${isPos?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400"}`}>{isPos?"+":""}{pm.pnl_pct.toFixed(2)}%</span>
                    </div>
                    <div className="hidden group-hover:flex items-center gap-1 shrink-0">
                      <button onClick={()=>{setEditingPM(pm);setPMForm({symbol:pm.symbol,entry_price:String(pm.entry_price),exit_price:String(pm.exit_price),notes:pm.notes||""});setPMError("");setShowPMModal(true);}} className="p-1.5 rounded-lg hover:bg-accent transition-colors cursor-pointer"><Pencil className="h-3.5 w-3.5 text-muted-foreground"/></button>
                      {deletingPMId===pm.id?(
                        <button onClick={async()=>{await api.deletePostMortem(pm.id);setPostMortems(p=>p.filter(x=>x.id!==pm.id));setDeletingPMId(null);}} className="px-2 py-1 text-[11px] rounded-lg bg-rose-500 text-white font-medium cursor-pointer">Confirm</button>
                      ):(
                        <button onClick={()=>setDeletingPMId(pm.id)} className="p-1.5 rounded-lg hover:bg-accent transition-colors cursor-pointer"><Trash2 className="h-3.5 w-3.5 text-muted-foreground"/></button>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
                    <span>Entry: <span className="text-foreground font-medium">{pm.entry_price.toFixed(2)}</span></span>
                    <ArrowUpRight className="h-3.5 w-3.5"/>
                    <span>Exit: <span className="text-foreground font-medium">{pm.exit_price.toFixed(2)}</span></span>
                  </div>
                  {pm.notes&&(
                    <div>
                      <p className={`text-[13px] text-foreground/80 leading-[1.7] ${isExpanded?"":"line-clamp-4"}`}>{pm.notes}</p>
                      {pm.notes.length>160&&<button onClick={()=>setExpandedPMId(isExpanded?null:pm.id)} className="text-[12px] text-primary hover:underline cursor-pointer mt-0.5">{isExpanded?"Show less":"Show more"}</button>}
                    </div>
                  )}
                  <p className="text-[11px] text-muted-foreground">{new Date(pm.created_at).toLocaleDateString("en-CH",{day:"numeric",month:"short",year:"numeric"})}</p>
                </GlassCard>
              );
            })}
          </div>
        )}
      </div>

      {/* Transaction History */}
      <div>
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 rounded-2xl bg-violet-100 dark:bg-violet-500/15 flex items-center justify-center"><History className="h-5 w-5 text-violet-600 dark:text-violet-400" strokeWidth={1.8}/></div>
          <h2 className="text-[16px] font-semibold">Transaction History</h2>
          <span className="text-[13px] text-muted-foreground ml-auto">{trades.length} transactions</span>
        </div>
        {trades.length===0?<GlassCard delay={0.45}><p className="text-muted-foreground py-6 text-center">No transactions yet. Record trades above or let your AI agent log them.</p></GlassCard>:(
          <GlassCard delay={0.45} className="!p-0 overflow-hidden">
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
        )}
      </div>

      {/* Trade Chart Dialog */}
      <Dialog open={tradeChartSymbol!==null} onOpenChange={open=>{if(!open)setTradeChartSymbol(null);}}>
        <DialogContent className="rounded-3xl max-w-2xl">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><LineChart className="h-5 w-5 text-primary"/>{tradeChartSymbol} — Price Chart</DialogTitle></DialogHeader>
          <div className="flex gap-1 mb-3">{RANGES.map(r=><button key={r.value} onClick={()=>setTradeChartRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${tradeChartRange===r.value?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{r.label}</button>)}</div>
          <div className="h-64">
            {tradeChartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:tradeChartData.length===0?<p className="text-[13px] text-muted-foreground text-center py-8">No data available</p>:(
              <ResponsiveContainer width="100%" height="100%"><AreaChart data={tradeChartData}><defs><linearGradient id="sg-trade" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2}/><stop offset="100%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={d=>d.slice(5)} stroke="var(--muted-foreground)"/><YAxis tick={{fontSize:10}} domain={["auto","auto"]} stroke="var(--muted-foreground)"/><Tooltip formatter={(v:any)=>Number(v).toFixed(2)}/><Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#sg-trade)"/></AreaChart></ResponsiveContainer>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Buy Assessment Modal */}
      <Dialog open={showBAModal} onOpenChange={open=>{if(!open){setShowBAModal(false);setEditingBA(null);}}}>
        <DialogContent className="rounded-3xl max-w-lg">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Target className="h-5 w-5 text-emerald-500"/>{editingBA?"Edit Buy Assessment":"New Buy Assessment"}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><label className="text-[13px] text-muted-foreground block mb-1.5">Symbol *</label><Input placeholder="NVDA" value={baForm.symbol} onChange={e=>setBAForm({...baForm,symbol:e.target.value.toUpperCase()})} className="rounded-xl h-11"/></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-[13px] text-muted-foreground block mb-1.5">Recommendation *</label><select className="w-full h-11 rounded-xl bg-muted px-3 text-[14px] border-0" value={baForm.recommendation} onChange={e=>setBAForm({...baForm,recommendation:e.target.value as BuyAssessmentInput["recommendation"]})}>{["buy","hold","watch","avoid"].map(r=><option key={r} value={r} className="capitalize">{r}</option>)}</select></div>
              <div><label className="text-[13px] text-muted-foreground block mb-1.5">Time Horizon</label><select className="w-full h-11 rounded-xl bg-muted px-3 text-[14px] border-0" value={baForm.time_horizon} onChange={e=>setBAForm({...baForm,time_horizon:e.target.value as BuyAssessmentInput["time_horizon"]|""})}><option value="">—</option>{["short","medium","long"].map(h=><option key={h} value={h} className="capitalize">{h}</option>)}</select></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-[13px] text-muted-foreground block mb-1.5">Target Price</label><Input type="number" placeholder="0.00" value={baForm.target_price} onChange={e=>setBAForm({...baForm,target_price:e.target.value})} className="rounded-xl h-11"/></div>
              <div><label className="text-[13px] text-muted-foreground block mb-1.5">Stop Loss</label><Input type="number" placeholder="0.00" value={baForm.stop_loss} onChange={e=>setBAForm({...baForm,stop_loss:e.target.value})} className="rounded-xl h-11"/></div>
            </div>
            <div><label className="text-[13px] text-muted-foreground block mb-1.5">Conviction (1–5) *</label><div className="flex items-center gap-2">{[1,2,3,4,5].map(n=><button key={n} type="button" onClick={()=>setBAForm({...baForm,conviction:String(n)})} className={`h-9 w-9 rounded-xl text-[14px] font-semibold transition-all cursor-pointer ${Number(baForm.conviction)>=n?"bg-primary text-primary-foreground":"bg-accent text-muted-foreground"}`}>{n}</button>)}</div></div>
            <div><label className="text-[13px] text-muted-foreground block mb-1.5">Thesis *</label><textarea rows={4} placeholder="Why this asset is worth buying..." value={baForm.thesis} onChange={e=>setBAForm({...baForm,thesis:e.target.value})} className="w-full rounded-xl bg-accent px-3 py-2.5 text-[14px] resize-none border-0 outline-none focus:ring-2 focus:ring-primary/30"/></div>
            <div><label className="text-[13px] text-muted-foreground block mb-1.5">Risk Factors</label><textarea rows={2} placeholder="Key risks to the thesis..." value={baForm.risk_factors} onChange={e=>setBAForm({...baForm,risk_factors:e.target.value})} className="w-full rounded-xl bg-accent px-3 py-2.5 text-[14px] resize-none border-0 outline-none focus:ring-2 focus:ring-primary/30"/></div>
            {baError&&<p className="text-[13px] text-loss">{baError}</p>}
            <button disabled={baSubmitting} onClick={async()=>{
              if(!baForm.symbol.trim()){setBAError("Symbol is required");return;}
              if(!baForm.thesis.trim()){setBAError("Thesis is required");return;}
              setBAError("");setBASubmitting(true);
              try{
                const payload:BuyAssessmentInput={symbol:baForm.symbol,recommendation:baForm.recommendation,thesis:baForm.thesis,conviction:Number(baForm.conviction),...(baForm.target_price?{target_price:Number(baForm.target_price)}:{}),...(baForm.stop_loss?{stop_loss:Number(baForm.stop_loss)}:{}),...(baForm.risk_factors?{risk_factors:baForm.risk_factors}:{}),...(baForm.time_horizon?{time_horizon:baForm.time_horizon as BuyAssessmentInput["time_horizon"]}:{})};
                if(editingBA){const updated=await api.updateBuyAssessment(editingBA.id,payload);setBuyAssessments(p=>p.map(x=>x.id===editingBA.id?updated:x));}
                else{const created=await api.createBuyAssessment(payload);setBuyAssessments(p=>[created,...p]);}
                setShowBAModal(false);setEditingBA(null);
              }catch(e:any){setBAError(e.message||"Failed to save");}
              finally{setBASubmitting(false);}
            }} className="w-full h-11 rounded-xl bg-primary text-primary-foreground font-semibold text-[15px] hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50">{baSubmitting?"Saving...":(editingBA?"Update":"Create")}</button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Post-Mortem Modal */}
      <Dialog open={showPMModal} onOpenChange={open=>{if(!open){setShowPMModal(false);setEditingPM(null);}}}>
        <DialogContent className="rounded-3xl max-w-lg">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><BookOpen className="h-5 w-5 text-rose-500"/>{editingPM?"Edit Post-Mortem":"New Post-Mortem"}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><label className="text-[13px] text-muted-foreground block mb-1.5">Symbol *</label><Input placeholder="NVDA" value={pmForm.symbol} onChange={e=>setPMForm({...pmForm,symbol:e.target.value.toUpperCase()})} className="rounded-xl h-11" disabled={!!editingPM}/></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-[13px] text-muted-foreground block mb-1.5">Entry Price *</label><Input type="number" placeholder="0.00" value={pmForm.entry_price} onChange={e=>setPMForm({...pmForm,entry_price:e.target.value})} className="rounded-xl h-11"/></div>
              <div><label className="text-[13px] text-muted-foreground block mb-1.5">Exit Price *</label><Input type="number" placeholder="0.00" value={pmForm.exit_price} onChange={e=>setPMForm({...pmForm,exit_price:e.target.value})} className="rounded-xl h-11"/></div>
            </div>
            {pmForm.entry_price&&pmForm.exit_price&&Number(pmForm.entry_price)>0&&(
              <div className="p-3 rounded-xl bg-accent text-[13px]">P&L: <span className={`font-semibold ${((Number(pmForm.exit_price)-Number(pmForm.entry_price))/Number(pmForm.entry_price)*100)>=0?"text-gain":"text-loss"}`}>{((Number(pmForm.exit_price)-Number(pmForm.entry_price))/Number(pmForm.entry_price)*100).toFixed(2)}%</span></div>
            )}
            <div><label className="text-[13px] text-muted-foreground block mb-1.5">Notes (lessons learned)</label><textarea rows={4} placeholder="What went wrong, what you'd do differently..." value={pmForm.notes} onChange={e=>setPMForm({...pmForm,notes:e.target.value})} className="w-full rounded-xl bg-accent px-3 py-2.5 text-[14px] resize-none border-0 outline-none focus:ring-2 focus:ring-primary/30"/></div>
            {pmError&&<p className="text-[13px] text-loss">{pmError}</p>}
            <button disabled={pmSubmitting} onClick={async()=>{
              if(!pmForm.symbol.trim()){setPMError("Symbol is required");return;}
              if(!pmForm.entry_price||!pmForm.exit_price){setPMError("Entry and exit prices are required");return;}
              setPMError("");setPMSubmitting(true);
              try{
                const payload:PostMortemInput={symbol:pmForm.symbol,entry_price:Number(pmForm.entry_price),exit_price:Number(pmForm.exit_price),...(pmForm.notes?{notes:pmForm.notes}:{})};
                if(editingPM){const updated=await api.updatePostMortem(editingPM.id,payload);setPostMortems(p=>p.map(x=>x.id===editingPM.id?updated:x));}
                else{const created=await api.createPostMortem(payload);setPostMortems(p=>[created,...p]);}
                setShowPMModal(false);setEditingPM(null);
              }catch(e:any){setPMError(e.message||"Failed to save");}
              finally{setPMSubmitting(false);}
            }} className="w-full h-11 rounded-xl bg-primary text-primary-foreground font-semibold text-[15px] hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50">{pmSubmitting?"Saving...":(editingPM?"Update":"Create")}</button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Trade Dialog */}
      <Dialog open={showTrade} onOpenChange={setShowTrade}><DialogContent className="rounded-3xl"><DialogHeader><DialogTitle>Record Trade</DialogTitle></DialogHeader><div className="space-y-4">
        <div className="grid grid-cols-4 gap-1.5">{(["buy","sell","deposit","withdraw"] as const).map(t=><button key={t} onClick={()=>setTradeForm({...tradeForm,type:t})} className={`py-2.5 rounded-xl text-[14px] font-medium transition-all cursor-pointer capitalize ${tradeForm.type===t?"bg-primary text-primary-foreground":"bg-accent text-muted-foreground hover:text-foreground"}`}>{t}</button>)}</div>
        {tradeForm.type!=="deposit"&&tradeForm.type!=="withdraw"&&<div><label className="text-[13px] text-muted-foreground block mb-1.5">Ticker</label><Input placeholder="AAPL, NVDA..." value={tradeForm.symbol} onChange={e=>setTradeForm({...tradeForm,symbol:e.target.value})} className="rounded-xl h-11"/></div>}
        <div className="grid grid-cols-2 gap-3"><div><label className="text-[13px] text-muted-foreground block mb-1.5">{tradeForm.type==="deposit"||tradeForm.type==="withdraw"?"Amount":"Qty"}</label><Input type="number" value={tradeForm.quantity} onChange={e=>setTradeForm({...tradeForm,quantity:e.target.value})} className="rounded-xl h-11"/></div>{tradeForm.type!=="deposit"&&tradeForm.type!=="withdraw"&&<div><label className="text-[13px] text-muted-foreground block mb-1.5">Price</label><Input type="number" value={tradeForm.price} onChange={e=>setTradeForm({...tradeForm,price:e.target.value})} className="rounded-xl h-11" placeholder="Market"/></div>}</div>
        <div className="grid grid-cols-2 gap-3"><div><label className="text-[13px] text-muted-foreground block mb-1.5">Date</label><Input type="date" value={tradeForm.date} onChange={e=>setTradeForm({...tradeForm,date:e.target.value})} className="rounded-xl h-11"/></div><div><label className="text-[13px] text-muted-foreground block mb-1.5">Currency</label><select className="w-full h-11 rounded-xl bg-accent px-3 text-[14px] border-0" value={tradeForm.currency} onChange={e=>setTradeForm({...tradeForm,currency:e.target.value})}>{["USD","CHF","EUR","GBP","KRW"].map(c=><option key={c} value={c}>{c}</option>)}</select></div></div>
        {tradeError&&<p className="text-[13px] text-loss">{tradeError}</p>}
        <button onClick={handleTrade} disabled={trading} className="w-full h-11 rounded-xl bg-primary text-primary-foreground font-semibold text-[15px] hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer capitalize disabled:opacity-50">{trading?"Processing...":tradeForm.type}</button>
      </div></DialogContent></Dialog>
    </div>
  );
}
