"use client";
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { motion } from "motion/react";
import { api, PortfolioSummary, Trade, ValueTimelinePoint } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell, ReferenceLine, ComposedChart, Line, Bar } from "recharts";
import { Plus, Trash2, Pencil, X, Check, RefreshCw, BarChart3, Globe, Link2, ClipboardCheck, History, LineChart } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { AnimatedNumber } from "@/components/animated-number";
import { LivePill } from "@/components/live-pill";
import { Sparkline as SparklineChart } from "@/components/sparkline";
import { RangeSwitcher } from "@/components/range-switcher";
import { SaxoSection } from "@/components/saxo-section";
import { SaxoReconnectBanner } from "@/components/saxo-reconnect-banner";

const COLORS = ["#3b82f6","#f97316","#ef4444","#a855f7","#14b8a6","#f59e0b","#ec4899","#22c55e","#06b6d4","#8b5cf6","#e11d48","#84cc16","#6366f1","#d946ef","#0ea5e9","#fb923c"];
const RANGES = [{value:"1d",label:"1D"},{value:"5d",label:"1W"},{value:"1mo",label:"1M"},{value:"3mo",label:"3M"},{value:"6mo",label:"6M"},{value:"1y",label:"1Y"},{value:"2y",label:"2Y"},{value:"5y",label:"5Y"}];
const TIMELINE_RANGES = ["1W","1M","3M","6M","1Y","ALL"] as const;

function PnlBadge({value,pct}:{value:number;pct?:number}){
  const pos=value>=0;
  return <span className={`text-[13px] px-2.5 py-1 rounded-xl font-medium inline-flex items-center gap-1 ${pos?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400"}`}>{pos?"+":""}{formatCurrency(value)}{pct!==undefined&&<span className="opacity-70">({pos?"+":""}{pct.toFixed(1)}%)</span>}</span>;
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
  const [publicEnabled,setPublicEnabled]=useState(false);
  const [publicToken,setPublicToken]=useState<string|null>(null);
  const [publicToggling,setPublicToggling]=useState(false);
  const [copied,setCopied]=useState(false);
  const [trades,setTrades]=useState<Trade[]>([]);
  const [tradesLoading,setTradesLoading]=useState(false);
  const [livePrices,setLivePrices]=useState<Record<string,{price:number;change:number;change_pct:number}>>({});
  const [flashes,setFlashes]=useState<Record<string,"up"|"down">>({});
  const prevPricesRef=useRef<Record<string,number>>({});
  const [timeline,setTimeline]=useState<ValueTimelinePoint[]>([]);
  const [tradeChartSymbol,setTradeChartSymbol]=useState<string|null>(null);
  const [tradeChartData,setTradeChartData]=useState<{date:string;close:number}[]>([]);
  const [tradeChartRange,setTradeChartRange]=useState("1y");
  const [tradeChartLoading,setTradeChartLoading]=useState(false);
  const [timelineRange,setTimelineRange]=useState<"1W"|"1M"|"3M"|"6M"|"1Y"|"ALL">("3M");

  const load=useCallback(()=>{
    setLoading(true);
    Promise.all([api.portfolio(),api.portfolioHistory(365),api.trades(),api.portfolioValueTimeline()]).then(([port,h,tr,tl])=>{
      setP(port);setHistoryData(h);
      setTrades(tr);
      setTimeline(tl);
    }).finally(()=>setLoading(false));
  },[]);
  useEffect(()=>{
    load();
    api.publicPortfolioStatus().then(s=>{setPublicEnabled(s.enabled);setPublicToken(s.token);}).catch(()=>{});
  },[load]);
  useEffect(()=>{const i=setInterval(load,120000);return()=>clearInterval(i);},[load]);

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
  const openTradeChart=async(sym:string,range=tradeChartRange)=>{
    setTradeChartSymbol(sym);setTradeChartRange(range);setTradeChartLoading(true);
    try{const r=await api.priceChart(sym,range);setTradeChartData(r.data);}catch{setTradeChartData([]);}
    finally{setTradeChartLoading(false);}
  };
  useEffect(()=>{if(tradeChartSymbol)openTradeChart(tradeChartSymbol,tradeChartRange);},[tradeChartRange]);

  // Total Value = live market value of stocks + cash. Always recomputed on
  // the client from live prices + cash_balance — never read from a cached
  // server-side total_value.
  //
  // All-time P&L is measured against NET DEPOSITS (what the user actually put
  // in, minus withdrawals), NOT cost basis. This is the true wealth delta and
  // correctly captures realised gains that have been booked to cash.
  //
  // Day P&L is separate: intraday change only (live price - previous close)
  // summed per position, with its own percentage against the stock value at
  // yesterday's close.
  const liveTotals=useMemo(()=>{
    if(!p)return{value:0,pnl:0,pnlPct:0,dayPnl:0,dayPnlPct:0};
    let liveMarketValue=0;
    let dayChangeChf=0;
    let stockValueAtOpen=0;
    for(const pos of p.positions){
      const live=livePrices[pos.symbol];
      const refPrice=pos.last_price||pos.avg_cost_price||0;
      const fx=refPrice&&pos.quantity?(pos.market_value/(refPrice*pos.quantity)):1;
      const livePrice=live?.price??pos.last_price??pos.avg_cost_price??0;
      liveMarketValue+=livePrice*pos.quantity*fx;
      const changePerShare=live?.change??0;
      dayChangeChf+=changePerShare*pos.quantity*fx;
      stockValueAtOpen+=(livePrice-changePerShare)*pos.quantity*fx;
    }
    const cash=p.cash_balance??0;
    const value=liveMarketValue+cash;
    const netDeposits=p.net_deposits??0;
    const pnl=value-netDeposits;
    const pnlPct=netDeposits>0?(pnl/netDeposits*100):0;
    const dayPnlPct=stockValueAtOpen>0?(dayChangeChf/stockValueAtOpen*100):0;
    return{value,pnl,pnlPct,dayPnl:dayChangeChf,dayPnlPct};
  },[p,livePrices]);

  const pnlUp=(p?.total_pnl??0)>=0;

  if(loading&&!p)return <div className="space-y-6">{[...Array(4)].map((_,i)=><div key={i} className="h-32 rounded-3xl bg-muted animate-pulse"/>)}</div>;

  return (
    <div className="space-y-8">
      <style>{`
  .recharts-brush text { fill: var(--foreground); font-weight: 500; font-size: 11px; }
  .recharts-brush-traveller { fill: var(--accent); }
  @keyframes flash-up { 0% { background-color: rgba(34,197,94,0.25); } 100% { background-color: transparent; } }
  @keyframes flash-down { 0% { background-color: rgba(239,68,68,0.25); } 100% { background-color: transparent; } }
  .flash-up { animation: flash-up 1.5s ease-out; }
  .flash-down { animation: flash-down 1.5s ease-out; }
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
          {l:"Day P&L",v:liveTotals.dayPnl,fmt:formatCurrency,pct:liveTotals.dayPnlPct},
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
                  <div className="text-center shrink-0 min-w-[50px]">
                    <p className="font-mono tabular-nums text-[13px] font-semibold">{pos.quantity}</p>
                    <p className="text-[10px] text-muted-foreground">shares</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-mono tabular-nums text-[13px] font-semibold">{livePrice.toFixed(2)}<span className="text-[11px] text-muted-foreground ml-1">{pos.currency}</span></p>
                    <p className="font-mono tabular-nums text-[11px] text-muted-foreground">cost {pos.avg_cost_price.toFixed(2)}</p>
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

        {/* Reconnect banner first — self-hides when not needed. */}
        <SaxoReconnectBanner />

        {/* Saxo brokerage — section header + card live inside SaxoSection, self-hides when not connected. */}
        <SaxoSection />
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
