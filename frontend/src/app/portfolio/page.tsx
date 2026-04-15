"use client";
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { motion } from "motion/react";
import { api, PortfolioSummary, PortfolioAnalysis, StockAnalysisEntry, Trade, ValueTimelinePoint, CVaRResult, KellyResult, PCAResult, CointegrationResult, CointPair, SpreadPoint } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell, ReferenceLine, ComposedChart, Line, Bar, LineChart as ReLineChart } from "recharts";
import { Plus, Trash2, Pencil, X, Check, RefreshCw, BarChart3, Brain, Zap, AlertTriangle, ArrowUpRight, ArrowDownRight, Globe, Link2, ClipboardCheck, History, LineChart, ChevronDown, ChevronRight, Archive, Activity } from "lucide-react";

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
  const [cvarData,setCvarData]=useState<CVaRResult|null>(null);
  const [cvarLoading,setCvarLoading]=useState(false);
  const [kellyData,setKellyData]=useState<KellyResult|null>(null);
  const [kellyLoading,setKellyLoading]=useState(false);
  const [kellyForm,setKellyForm]=useState({symbol:"",expectedReturn:"15",conviction:"0.7"});
  const [kellyError,setKellyError]=useState("");

  // PCA state
  const [pcaData,setPcaData]=useState<PCAResult|null>(null);
  const [pcaLoading,setPcaLoading]=useState(false);
  const [pcaExpanded,setPcaExpanded]=useState<number|null>(null);

  // Cointegration state
  const [pairsData,setPairsData]=useState<CointegrationResult|null>(null);
  const [pairsLoading,setPairsLoading]=useState(false);
  const [pairsSymbols,setPairsSymbols]=useState("");
  const [expandedPair,setExpandedPair]=useState<string|null>(null);
  const [spreadHistory,setSpreadHistory]=useState<Record<string,SpreadPoint[]>>({});
  const [spreadLoading,setSpreadLoading]=useState<string|null>(null);

  const fetchCvar=useCallback(()=>{
    setCvarLoading(true);
    api.cvar().then(setCvarData).catch(()=>{}).finally(()=>setCvarLoading(false));
  },[]);

  const handleKelly=useCallback(async()=>{
    if(!kellyForm.symbol)return;
    setKellyLoading(true);setKellyError("");setKellyData(null);
    try{
      const r=await api.kelly(kellyForm.symbol,parseFloat(kellyForm.expectedReturn)||15,parseFloat(kellyForm.conviction)||0.7);
      setKellyData(r);
    }catch(e){setKellyError(e instanceof Error?e.message:"Failed");}
    finally{setKellyLoading(false);}
  },[kellyForm]);

  const fetchPca=useCallback(()=>{
    setPcaLoading(true);
    api.pca().then(setPcaData).catch(()=>{}).finally(()=>setPcaLoading(false));
  },[]);

  const fetchPairs=useCallback(()=>{
    setPairsLoading(true);
    api.cointegrationPairs(pairsSymbols||undefined).then(setPairsData).catch(()=>{}).finally(()=>setPairsLoading(false));
  },[pairsSymbols]);

  const togglePairExpand=useCallback(async(pair:CointPair)=>{
    const key=`${pair.a}/${pair.b}`;
    if(expandedPair===key){setExpandedPair(null);return;}
    setExpandedPair(key);
    if(!spreadHistory[key]){
      setSpreadLoading(key);
      try{
        const hist=await api.spreadHistory(pair.a,pair.b,pair.hedge_ratio,90);
        setSpreadHistory(prev=>({...prev,[key]:hist}));
      }catch{} finally{setSpreadLoading(null);}
    }
  },[expandedPair,spreadHistory]);

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
  useEffect(()=>{load();api.publicPortfolioStatus().then(s=>{setPublicEnabled(s.enabled);setPublicToken(s.token);}).catch(()=>{});},[load]);
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
          <p className="text-sm font-medium text-primary mb-1">Portfolio</p>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Investments & Holdings</h1>
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
                className="h-8 px-3 rounded-xl bg-accent text-[13px] font-medium flex items-center gap-1.5 hover:bg-muted transition-colors cursor-pointer"
              >
                {copied?<><ClipboardCheck className="h-3.5 w-3.5 text-gain"/>Copied</>:<><Link2 className="h-3.5 w-3.5"/>Copy link</>}
              </button>
            )}
          </div>
          <button onClick={load} disabled={loading} className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center hover:bg-muted transition-colors cursor-pointer"><RefreshCw className={`h-4 w-4 ${loading?"animate-spin":""}`}/></button>
          <Button onClick={()=>setShowTrade(true)} className="rounded-xl h-10 px-5"><Plus className="h-4 w-4 mr-1.5"/>Trade</Button>
        </div>
      </motion.div>

      {/* Summary */}
      <div className="grid gap-5 grid-cols-2 lg:grid-cols-4">
        {[
          {l:"Invested",v:formatCurrency(p?.total_cost??0),live:false},
          {l:"Cash",v:formatCurrency(p?.cash_balance??0),live:false},
          {l:"Positions",v:String(p?.positions_count??0),live:false},
          {l:"Total",v:liveTotals.value+(p?.cash_balance??0),live:true},
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
          {(p?.positions.length??0)===0?<p className="text-sm text-muted-foreground text-center py-8">No positions</p>:(
            <div className="h-48"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={p!.positions} dataKey="market_value" nameKey="symbol" cx="50%" cy="50%" outerRadius={70} innerRadius={42}>{p!.positions.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Pie><Tooltip formatter={(v:any)=>formatCurrency(Number(v))}/></PieChart></ResponsiveContainer></div>
          )}
        </GlassCard>

        {/* Holdings */}
        <GlassCard delay={0.25} className="md:col-span-1 lg:col-span-2 !p-4">
          <p className="text-[13px] font-medium text-muted-foreground mb-3">Holdings</p>
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
                <div key={pos.id} className="flex items-center gap-2 p-3 rounded-2xl bg-accent flex-wrap"><span className="font-bold text-sm w-14">{pos.symbol}</span><Input value={editForm.quantity} onChange={e=>setEditForm({...editForm,quantity:e.target.value})} className="h-8 w-16 text-sm rounded-xl" placeholder="Qty"/><Input value={editForm.avg_cost_price} onChange={e=>setEditForm({...editForm,avg_cost_price:e.target.value})} className="h-8 w-20 text-sm rounded-xl" placeholder="Price"/><button onClick={()=>handleUpdate(pos.id)} className="cursor-pointer"><Check className="h-4 w-4 text-gain"/></button><button onClick={()=>setEditingId(null)} className="cursor-pointer"><X className="h-4 w-4 text-muted-foreground"/></button></div>
              ):(
                <div key={pos.id} className={`flex items-center justify-between px-3 py-3 pr-4 rounded-2xl cursor-pointer transition-all duration-200 group hover:bg-accent ${chartTicker===pos.symbol?"bg-accent":""} ${flash==="up"?"flash-up":flash==="down"?"flash-down":""}`} onClick={()=>openChart(pos.symbol)}>
                  <div className="min-w-[70px] shrink-0">
                    <p className="font-semibold text-[15px]">{pos.symbol}</p>
                    <p className="text-[11px] text-muted-foreground truncate max-w-[80px]">{pos.name}</p>
                  </div>
                  <div className="hidden lg:block shrink-0"><Sparkline data={pos.sparkline} positive={livePnlPct>=0}/></div>
                  <div className="text-right shrink-0">
                    <p className="text-[14px] font-medium tabular-nums">{livePrice.toFixed(2)}<span className="text-[10px] text-muted-foreground ml-1">{pos.currency}</span></p>
                    <p className="text-[11px] text-muted-foreground tabular-nums">cost {pos.avg_cost_price.toFixed(2)}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <div className="text-right hidden sm:block">
                      <p className="text-[15px] font-semibold tabular-nums">{formatCurrency(pos.market_value)}</p>
                      <p className={`text-[13px] font-semibold tabular-nums ${livePnlPct>=0?"text-gain":"text-loss"}`}>{livePnlPct>=0?"+":""}{livePnlPct.toFixed(1)}%</p>
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
                return <div className="flex items-center justify-center gap-3 mb-3"><span className="text-2xl font-bold tabular-nums">{lp.toFixed(2)}</span><span className={`text-sm font-medium ${lc>=0?"text-gain":"text-loss"}`}>{lc>=0?"+":""}{lc.toFixed(2)} ({lcp>=0?"+":""}{lcp.toFixed(1)}%)</span></div>;
              })()}
              <div className="flex justify-center gap-1 mb-2">{RANGES.map(r=><button key={r.value} onClick={()=>setChartRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${chartRange===r.value?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{r.label}</button>)}</div>
              <div className="h-52">{chartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:chartData.length===0?<p className="text-sm text-muted-foreground">No data</p>:(
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
          <h2 className="text-lg font-semibold">Stock Analyses</h2>
          <span className="text-[13px] text-muted-foreground">{Object.keys(stockAnalyses).length} held</span>
        </div>
        {Object.keys(stockAnalyses).length===0?<GlassCard delay={0.35}><p className="text-muted-foreground py-6 text-center">No stock analyses yet. Your agent will store reports here.</p></GlassCard>:(
          <div className="relative">
            <div ref={stockDeck.ref} className={`flex gap-5 overflow-x-auto pb-3 -mx-4 px-4 stock-deck ${stockDeck.atStart?"deck-at-start":""} ${stockDeck.atEnd?"deck-at-end":""}`}>
              {Object.values(stockAnalyses).map(entry=>{const s=entry.stock;return(
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
            <h2 className="text-lg font-semibold group-hover:text-primary transition-colors">Past Stocks</h2>
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
                          <ActionBadge action={s.action} size="sm"/>
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
            <h2 className="text-lg font-semibold">Economy & Market</h2>
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
              <h2 className="text-lg font-semibold">Portfolio Timeline</h2>
            </div>
            <div className="sm:ml-auto flex items-center gap-3">
              <span className="text-[13px] text-muted-foreground">Current</span>
              <span className="text-lg font-bold tabular-nums">{formatCurrency(lastPt.value)}</span>
              <span className={`text-[13px] font-semibold ${totalReturn>=0?"text-gain":"text-loss"}`}>{totalReturn>=0?"+":""}{formatCurrency(totalReturn)} ({totalReturnPct>=0?"+":""}{totalReturnPct.toFixed(1)}%)</span>
            </div>
          </div>
          <GlassCard delay={0.42} className="!p-4">
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

      {/* Transaction History */}
      <div>
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 rounded-2xl bg-violet-100 dark:bg-violet-500/15 flex items-center justify-center"><History className="h-5 w-5 text-violet-600 dark:text-violet-400" strokeWidth={1.8}/></div>
          <h2 className="text-lg font-semibold">Transaction History</h2>
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

      {/* Risk Metrics: CVaR + Kelly */}
      <div className="grid gap-5 md:grid-cols-2">
        {/* CVaR Card */}
        <GlassCard delay={0.5}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-2xl bg-rose-100 dark:bg-rose-500/15 flex items-center justify-center"><Activity className="h-5 w-5 text-rose-600 dark:text-rose-400" strokeWidth={1.8}/></div>
              <div><p className="text-[13px] font-medium text-muted-foreground">CVaR / Expected Shortfall</p><p className="text-[11px] text-muted-foreground">1-year lookback · historical simulation</p></div>
            </div>
            <button onClick={fetchCvar} disabled={cvarLoading} className="h-8 w-8 rounded-xl bg-accent flex items-center justify-center hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${cvarLoading?"animate-spin":""}`}/></button>
          </div>
          {cvarData===null&&!cvarLoading&&(
            <div className="text-center py-6"><p className="text-[13px] text-muted-foreground mb-3">Compute tail-risk metrics for your portfolio</p><button onClick={fetchCvar} className="h-9 px-5 rounded-xl bg-primary text-primary-foreground text-[13px] font-medium hover:brightness-110 transition-all cursor-pointer">Compute CVaR</button></div>
          )}
          {cvarLoading&&<div className="flex items-center justify-center py-8 text-muted-foreground text-[13px]">Computing...</div>}
          {cvarData&&!cvarLoading&&(
            cvarData.error?<p className="text-[13px] text-loss py-4">{cvarData.error==="no_positions"?"No positions to analyze.":"Insufficient price history."}</p>:(
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-2xl bg-rose-50 dark:bg-rose-500/10">
                  <p className="text-[11px] text-muted-foreground uppercase tracking-wider mb-1">CVaR 95%</p>
                  <p className="text-lg font-bold tabular-nums text-loss">{formatCurrency(cvarData.cvar_95)}</p>
                  <p className="text-[11px] text-muted-foreground">{cvarData.cvar_95_pct.toFixed(2)}% of portfolio</p>
                </div>
                <div className="p-3 rounded-2xl bg-rose-50 dark:bg-rose-500/10">
                  <p className="text-[11px] text-muted-foreground uppercase tracking-wider mb-1">CVaR 99%</p>
                  <p className="text-lg font-bold tabular-nums text-loss">{formatCurrency(cvarData.cvar_99)}</p>
                  <p className="text-[11px] text-muted-foreground">{cvarData.cvar_99_pct.toFixed(2)}% of portfolio</p>
                </div>
                <div className="p-3 rounded-2xl bg-accent">
                  <p className="text-[11px] text-muted-foreground uppercase tracking-wider mb-1">VaR 95%</p>
                  <p className="text-base font-semibold tabular-nums text-loss">{formatCurrency(cvarData.var_95)}</p>
                </div>
                <div className="p-3 rounded-2xl bg-accent">
                  <p className="text-[11px] text-muted-foreground uppercase tracking-wider mb-1">VaR 99%</p>
                  <p className="text-base font-semibold tabular-nums text-loss">{formatCurrency(cvarData.var_99)}</p>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">{cvarData.sample_size} trading days · portfolio {formatCurrency(cvarData.total_portfolio_chf)}</p>
            </div>)
          )}
        </GlassCard>

        {/* Half-Kelly Card */}
        <GlassCard delay={0.55}>
          <div className="flex items-center gap-3 mb-4">
            <div className="h-10 w-10 rounded-2xl bg-violet-100 dark:bg-violet-500/15 flex items-center justify-center"><Zap className="h-5 w-5 text-violet-600 dark:text-violet-400" strokeWidth={1.8}/></div>
            <div><p className="text-[13px] font-medium text-muted-foreground">Half-Kelly Position Sizer</p><p className="text-[11px] text-muted-foreground">optimal bet fraction · max 20% of portfolio</p></div>
          </div>
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <div><label className="text-[11px] text-muted-foreground block mb-1">Ticker</label><input value={kellyForm.symbol} onChange={e=>setKellyForm({...kellyForm,symbol:e.target.value.toUpperCase()})} placeholder="NVDA" className="w-full h-9 rounded-xl bg-accent px-3 text-[13px] outline-none focus:ring-2 focus:ring-primary/40 uppercase"/></div>
              <div><label className="text-[11px] text-muted-foreground block mb-1">Exp. Return %</label><input type="number" value={kellyForm.expectedReturn} onChange={e=>setKellyForm({...kellyForm,expectedReturn:e.target.value})} className="w-full h-9 rounded-xl bg-accent px-3 text-[13px] outline-none focus:ring-2 focus:ring-primary/40"/></div>
              <div><label className="text-[11px] text-muted-foreground block mb-1">Conviction 0–1</label><input type="number" step="0.1" min="0" max="1" value={kellyForm.conviction} onChange={e=>setKellyForm({...kellyForm,conviction:e.target.value})} className="w-full h-9 rounded-xl bg-accent px-3 text-[13px] outline-none focus:ring-2 focus:ring-primary/40"/></div>
            </div>
            <button onClick={handleKelly} disabled={kellyLoading||!kellyForm.symbol} className="w-full h-9 rounded-xl bg-primary text-primary-foreground text-[13px] font-medium hover:brightness-110 transition-all cursor-pointer disabled:opacity-50">{kellyLoading?"Computing...":"Calculate"}</button>
            {kellyError&&<p className="text-[12px] text-loss">{kellyError}</p>}
            {kellyData&&!kellyLoading&&(
              kellyData.error?<p className="text-[13px] text-loss">{kellyData.error==="insufficient_history"?`Insufficient history (${kellyData.available_days} days available)`:`Error: ${kellyData.error}`}</p>:(
              <div className="grid grid-cols-2 gap-2 pt-1">
                <div className="p-3 rounded-2xl bg-violet-50 dark:bg-violet-500/10">
                  <p className="text-[11px] text-muted-foreground mb-1">Half-Kelly fraction</p>
                  <p className="text-lg font-bold tabular-nums">{(kellyData.half_kelly_fraction*100).toFixed(2)}%</p>
                </div>
                <div className="p-3 rounded-2xl bg-violet-50 dark:bg-violet-500/10">
                  <p className="text-[11px] text-muted-foreground mb-1">Suggested size</p>
                  <p className="text-lg font-bold tabular-nums">{formatCurrency(kellyData.suggested_chf)}</p>
                </div>
                <div className="p-3 rounded-2xl bg-accent">
                  <p className="text-[11px] text-muted-foreground mb-1">Est. shares</p>
                  <p className="text-base font-semibold tabular-nums">{kellyData.suggested_shares}</p>
                </div>
                <div className="p-3 rounded-2xl bg-accent">
                  <p className="text-[11px] text-muted-foreground mb-1">60d vol (ann.)</p>
                  <p className="text-base font-semibold tabular-nums">{kellyData.volatility_60d.toFixed(1)}%</p>
                </div>
              </div>)
            )}
          </div>
        </GlassCard>
      </div>

      {/* PCA Factor Model */}
      <GlassCard delay={0.6}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-2xl bg-sky-100 dark:bg-sky-500/15 flex items-center justify-center"><BarChart3 className="h-5 w-5 text-sky-600 dark:text-sky-400" strokeWidth={1.8}/></div>
            <div><p className="text-[13px] font-medium text-muted-foreground">PCA Factor Exposure</p><p className="text-[11px] text-muted-foreground">252d returns · top 5 principal components</p></div>
          </div>
          <button onClick={fetchPca} disabled={pcaLoading} className="h-8 w-8 rounded-xl bg-accent flex items-center justify-center hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${pcaLoading?"animate-spin":""}`}/></button>
        </div>
        {pcaData===null&&!pcaLoading&&(
          <div className="text-center py-6"><p className="text-[13px] text-muted-foreground mb-3">Decompose portfolio into principal risk factors</p><button onClick={fetchPca} className="h-9 px-5 rounded-xl bg-primary text-primary-foreground text-[13px] font-medium hover:brightness-110 transition-all cursor-pointer">Run PCA</button></div>
        )}
        {pcaLoading&&<div className="flex items-center justify-center py-8 text-muted-foreground text-[13px]">Computing PCA...</div>}
        {pcaData&&!pcaLoading&&(
          pcaData.error?<p className="text-[13px] text-loss py-4">{pcaData.error==="insufficient_holdings"?"Need at least 2 holdings with sufficient history.":pcaData.error==="no_positions"?"No positions found.":pcaData.error}</p>:(
          <div className="space-y-3">
            {pcaData.concentration_risk&&(
              <div className="grid grid-cols-2 gap-3 mb-2">
                <div className="p-3 rounded-2xl bg-sky-50 dark:bg-sky-500/10">
                  <p className="text-[11px] text-muted-foreground uppercase tracking-wider mb-1">Top Factor</p>
                  <p className="text-lg font-bold tabular-nums">{pcaData.concentration_risk.top_factor_pct.toFixed(1)}%</p>
                  <p className="text-[11px] text-muted-foreground">of variance</p>
                </div>
                <div className="p-3 rounded-2xl bg-sky-50 dark:bg-sky-500/10">
                  <p className="text-[11px] text-muted-foreground uppercase tracking-wider mb-1">Total ({pcaData.factors?.length} PCs)</p>
                  <p className="text-lg font-bold tabular-nums">{pcaData.total_variance_explained_pct?.toFixed(1)}%</p>
                  <p className="text-[11px] text-muted-foreground">HHI {pcaData.concentration_risk.herfindahl_index.toFixed(3)}</p>
                </div>
              </div>
            )}
            <div className="space-y-2">
              {pcaData.factors?.slice(0,3).map(f=>(
                <div key={f.idx} className="rounded-2xl bg-accent/60 overflow-hidden">
                  <button onClick={()=>setPcaExpanded(pcaExpanded===f.idx?null:f.idx)} className="w-full flex items-center gap-3 p-3 hover:bg-accent transition-colors cursor-pointer">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[12px] font-medium">PC{f.idx+1}{f.interpretation?` — ${f.interpretation}`:""}</span>
                        <span className="text-[12px] font-bold tabular-nums">{f.variance_explained_pct.toFixed(1)}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-border overflow-hidden">
                        <div className="h-full rounded-full bg-sky-500 transition-all" style={{width:`${Math.min(f.variance_explained_pct,100)}%`}}/>
                      </div>
                    </div>
                    {pcaExpanded===f.idx?<ChevronDown className="h-4 w-4 text-muted-foreground shrink-0"/>:<ChevronRight className="h-4 w-4 text-muted-foreground shrink-0"/>}
                  </button>
                  {pcaExpanded===f.idx&&(
                    <div className="px-3 pb-3 space-y-1">
                      {f.loadings.slice(0,5).map(l=>(
                        <div key={l.symbol} className="flex items-center gap-2">
                          <span className="text-[11px] font-mono w-20 shrink-0">{l.symbol}</span>
                          <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
                            <div className="h-full rounded-full transition-all" style={{width:`${Math.min(Math.abs(l.loading)*100,100)}%`,background:l.loading>=0?"#3b82f6":"#ef4444",marginLeft:l.loading<0?`${(1-Math.abs(l.loading))*100}%`:undefined}}/>
                          </div>
                          <span className={`text-[11px] tabular-nums w-12 text-right ${l.loading>=0?"text-blue-600":"text-rose-500"}`}>{l.loading>=0?"+":""}{l.loading.toFixed(3)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">{pcaData.sample_size} trading days · {pcaData.holdings_used?.length} holdings</p>
          </div>)
        )}
      </GlassCard>

      {/* Cointegration Pairs */}
      <GlassCard delay={0.65}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-2xl bg-teal-100 dark:bg-teal-500/15 flex items-center justify-center"><Link2 className="h-5 w-5 text-teal-600 dark:text-teal-400" strokeWidth={1.8}/></div>
            <div><p className="text-[13px] font-medium text-muted-foreground">Cointegration Pairs</p><p className="text-[11px] text-muted-foreground">Engle-Granger · SMI universe · p &lt; 0.05</p></div>
          </div>
          <button onClick={fetchPairs} disabled={pairsLoading} className="h-8 w-8 rounded-xl bg-accent flex items-center justify-center hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${pairsLoading?"animate-spin":""}`}/></button>
        </div>
        <div className="flex gap-2 mb-3">
          <input value={pairsSymbols} onChange={e=>setPairsSymbols(e.target.value)} placeholder="Custom symbols: NESN.SW,ROG.SW,... (leave blank for SMI top 10)" className="flex-1 h-8 rounded-xl bg-accent px-3 text-[12px] outline-none focus:ring-2 focus:ring-primary/40"/>
          <button onClick={fetchPairs} disabled={pairsLoading} className="h-8 px-4 rounded-xl bg-primary text-primary-foreground text-[12px] font-medium hover:brightness-110 transition-all cursor-pointer disabled:opacity-50">{pairsLoading?"Running...":"Scan"}</button>
        </div>
        {pairsData===null&&!pairsLoading&&(
          <div className="text-center py-4"><p className="text-[13px] text-muted-foreground">Click Scan to find cointegrated pairs in the SMI universe</p></div>
        )}
        {pairsLoading&&<div className="flex items-center justify-center py-8 text-muted-foreground text-[13px]">Running Engle-Granger tests...</div>}
        {pairsData&&!pairsLoading&&(
          pairsData.pairs.length===0?(
            <p className="text-[13px] text-muted-foreground py-4 text-center">No cointegrated pairs found (p &lt; 0.05) in this universe.</p>
          ):(
          <div className="space-y-2">
            <div className="grid grid-cols-[1fr_80px_100px_80px_90px] gap-2 px-2 text-[11px] text-muted-foreground font-medium uppercase tracking-wider">
              <span>Pair</span><span className="text-right">p-value</span><span className="text-right">Z-score</span><span className="text-right">Half-life</span><span className="text-right">Signal</span>
            </div>
            {pairsData.pairs.map(pair=>{
              const key=`${pair.a}/${pair.b}`;
              const isExpanded=expandedPair===key;
              const absZ=Math.abs(pair.spread_zscore);
              const zColor=absZ>2?"text-rose-500 font-bold":absZ>1?"text-amber-500 font-semibold":"text-foreground";
              const sigColor=pair.signal==="neutral"?"text-muted-foreground":pair.signal==="long_a_short_b"?"text-emerald-600 dark:text-emerald-400":"text-rose-500";
              const sigLabel=pair.signal==="neutral"?"—":pair.signal==="long_a_short_b"?`L ${pair.a}`:`L ${pair.b}`;
              return(
                <div key={key} className="rounded-2xl bg-accent/50 overflow-hidden">
                  <button onClick={()=>togglePairExpand(pair)} className="w-full grid grid-cols-[1fr_80px_100px_80px_90px] gap-2 px-2 py-2.5 hover:bg-accent transition-colors cursor-pointer items-center">
                    <span className="text-[12px] font-medium text-left">{pair.a} / {pair.b}</span>
                    <span className="text-[12px] tabular-nums text-right text-muted-foreground">{pair.p_value.toFixed(4)}</span>
                    <div className="flex items-center justify-end gap-1">
                      <div className="h-1.5 w-12 rounded-full bg-border overflow-hidden">
                        <div className="h-full rounded-full transition-all" style={{width:`${Math.min(absZ/3*100,100)}%`,background:absZ>2?"#ef4444":absZ>1?"#f59e0b":"#3b82f6"}}/>
                      </div>
                      <span className={`text-[12px] tabular-nums w-10 text-right ${zColor}`}>{pair.spread_zscore.toFixed(2)}</span>
                    </div>
                    <span className="text-[12px] tabular-nums text-right text-muted-foreground">{pair.half_life_days!=null?`${pair.half_life_days}d`:"—"}</span>
                    <span className={`text-[11px] font-medium text-right truncate ${sigColor}`}>{sigLabel}</span>
                  </button>
                  {isExpanded&&(
                    <div className="px-3 pb-3 space-y-2">
                      <div className="flex gap-4 text-[11px] text-muted-foreground">
                        <span>Hedge ratio: <b className="text-foreground">{pair.hedge_ratio.toFixed(4)}</b></span>
                        <span>252d corr: <b className="text-foreground">{pair.last_252d_corr.toFixed(3)}</b></span>
                        <span>Spread: <b className="text-foreground">{pair.current_spread.toFixed(4)}</b></span>
                      </div>
                      {spreadLoading===key&&<div className="text-[12px] text-muted-foreground py-2">Loading spread chart...</div>}
                      {spreadHistory[key]&&spreadHistory[key].length>0&&(
                        <div className="h-40">
                          <ResponsiveContainer width="100%" height="100%">
                            <ReLineChart data={spreadHistory[key]}>
                              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/>
                              <XAxis dataKey="date" tick={{fontSize:9}} tickFormatter={d=>d.slice(5)} stroke="var(--muted-foreground)"/>
                              <YAxis tick={{fontSize:9}} domain={["auto","auto"]} stroke="var(--muted-foreground)"/>
                              <Tooltip formatter={(v:unknown)=>typeof v==="number"?v.toFixed(5):String(v)} labelFormatter={(d:unknown)=>String(d)}/>
                              <ReferenceLine y={spreadHistory[key][0]?.upper} stroke="#ef4444" strokeDasharray="4 2" label={{value:"+2σ",fill:"#ef4444",fontSize:9}}/>
                              <ReferenceLine y={spreadHistory[key][0]?.lower} stroke="#ef4444" strokeDasharray="4 2" label={{value:"-2σ",fill:"#ef4444",fontSize:9}}/>
                              <Line type="monotone" dataKey="spread" stroke="#14b8a6" strokeWidth={1.5} dot={false}/>
                            </ReLineChart>
                          </ResponsiveContainer>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            <p className="text-[11px] text-muted-foreground pt-1">{pairsData.pairs.length} cointegrated pairs · universe: {pairsData.universe.length} symbols · {pairsData.sample_size}d lookback</p>
          </div>)
        )}
      </GlassCard>

      {/* Trade Chart Dialog */}
      <Dialog open={tradeChartSymbol!==null} onOpenChange={open=>{if(!open)setTradeChartSymbol(null);}}>
        <DialogContent className="rounded-3xl max-w-2xl">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><LineChart className="h-5 w-5 text-primary"/>{tradeChartSymbol} — Price Chart</DialogTitle></DialogHeader>
          <div className="flex gap-1 mb-3">{RANGES.map(r=><button key={r.value} onClick={()=>setTradeChartRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${tradeChartRange===r.value?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{r.label}</button>)}</div>
          <div className="h-64">
            {tradeChartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:tradeChartData.length===0?<p className="text-sm text-muted-foreground text-center py-8">No data available</p>:(
              <ResponsiveContainer width="100%" height="100%"><AreaChart data={tradeChartData}><defs><linearGradient id="sg-trade" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2}/><stop offset="100%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={d=>d.slice(5)} stroke="var(--muted-foreground)"/><YAxis tick={{fontSize:10}} domain={["auto","auto"]} stroke="var(--muted-foreground)"/><Tooltip formatter={(v:any)=>Number(v).toFixed(2)}/><Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#sg-trade)"/></AreaChart></ResponsiveContainer>
            )}
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
