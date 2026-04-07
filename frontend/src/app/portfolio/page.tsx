"use client";
import { useEffect, useState, useCallback } from "react";
import { motion } from "motion/react";
import { api, PortfolioSummary, Position, PortfolioAnalysis, AnalysisListItem } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell } from "recharts";
import { Plus, Trash2, Pencil, X, Check, RefreshCw, BarChart3, Brain, Zap, AlertTriangle, ArrowUpRight, ArrowDownRight } from "lucide-react";

const COLORS = ["#34c759","#007aff","#ff9500","#ff3b30","#af52de","#ff2d55","#5ac8fa","#4cd964"];
const RANGES = [{value:"1mo",label:"1M"},{value:"3mo",label:"3M"},{value:"6mo",label:"6M"},{value:"1y",label:"1Y"},{value:"2y",label:"2Y"},{value:"5y",label:"5Y"}];

function GlassCard({children,className="",delay=0}:{children:React.ReactNode;className?:string;delay?:number}){
  return <motion.div initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{duration:0.45,delay,ease:[0.25,0.46,0.45,0.94]}} className={`glass bg-card rounded-3xl p-6 ${className}`}>{children}</motion.div>;
}
function Sparkline({data,positive}:{data:number[];positive:boolean}){
  if(!data||data.length<2)return null;
  const min=Math.min(...data),max=Math.max(...data),range=max-min||1,h=36,w=90;
  const points=data.map((v,i)=>`${(i/(data.length-1))*w},${h-((v-min)/range)*h}`).join(" ");
  return <svg width={w} height={h} className="shrink-0"><polyline fill="none" stroke={positive?"#34c759":"#ff3b30"} strokeWidth="2" points={points}/></svg>;
}
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
  const [latestPortfolio,setLP]=useState<PortfolioAnalysis|null>(null);
  const [latestEconomy,setLE]=useState<PortfolioAnalysis|null>(null);
  const [activeAnalysis,setAA]=useState<PortfolioAnalysis|null>(null);
  const [olderList,setOL]=useState<AnalysisListItem[]>([]);
  const [showOlder,setShowOlder]=useState(false);
  const [analysisType,setAnalysisType]=useState<"portfolio"|"economy">("portfolio");

  const load=useCallback(()=>{
    setLoading(true);
    Promise.all([api.portfolio(),api.portfolioHistory(90),api.analysisLatest("portfolio"),api.analysisLatest("economy")]).then(([port,h,ap,ae])=>{
      setP(port);setHistoryData(h);
      if(ap&&!("status" in ap&&(ap as any).status==="none")){setLP(ap);setAA(ap);}
      if(ae&&!("status" in ae&&(ae as any).status==="none"))setLE(ae);
    }).finally(()=>setLoading(false));
  },[]);
  useEffect(()=>{load();},[load]);
  useEffect(()=>{const i=setInterval(load,120000);return()=>clearInterval(i);},[load]);

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
  const viewAnalysis=async(id:string)=>{try{const a=await api.analysisDetail(id);setAA(a);setShowOlder(false);}catch{}};
  const loadOlder=async()=>{const l=await api.analysisList(analysisType,20);setOL(l);setShowOlder(true);};

  useEffect(()=>{
    if(analysisType==="portfolio"&&latestPortfolio)setAA(latestPortfolio);
    else if(analysisType==="economy"&&latestEconomy)setAA(latestEconomy);
    else setAA(null);setShowOlder(false);
  },[analysisType,latestPortfolio,latestEconomy]);

  const pnlUp=(p?.total_pnl??0)>=0;

  if(loading&&!p)return <div className="space-y-6">{[...Array(4)].map((_,i)=><div key={i} className="h-32 rounded-3xl bg-muted animate-pulse"/>)}</div>;

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div initial={{opacity:0}} animate={{opacity:1}} className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Portfolio</h1>
          <p className="text-[13px] text-muted-foreground mt-1 uppercase tracking-wider">Total Value</p>
          <p className="text-4xl font-bold tracking-tight mt-1">{formatCurrency(p?.total_value??0)}</p>
          <div className="flex items-center gap-3 mt-2"><PnlBadge value={p?.total_pnl??0} pct={p?.total_pnl_pct??0}/><span className="text-[13px] text-muted-foreground">all time</span></div>
        </div>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading} className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center hover:bg-muted transition-colors cursor-pointer"><RefreshCw className={`h-4 w-4 ${loading?"animate-spin":""}`}/></button>
          <Button onClick={()=>setShowTrade(true)} className="rounded-xl h-10 px-5"><Plus className="h-4 w-4 mr-1.5"/>Trade</Button>
        </div>
      </motion.div>

      {/* Summary */}
      <div className="grid gap-5 grid-cols-2 lg:grid-cols-4">
        {[{l:"Invested",v:formatCurrency(p?.total_cost??0)},{l:"Cash",v:formatCurrency(p?.cash_balance??0)},{l:"Positions",v:String(p?.positions_count??0)},{l:"Total",v:formatCurrency((p?.total_value??0)+(p?.cash_balance??0))}].map((item,i)=>(
          <GlassCard key={item.l} delay={0.05+i*0.05}><p className="text-[13px] text-muted-foreground mb-1">{item.l}</p><p className="text-2xl font-semibold">{item.v}</p></GlassCard>
        ))}
      </div>

      {/* Holdings + Chart */}
      <div className="grid gap-5 lg:grid-cols-5">
        {/* Allocation */}
        <GlassCard delay={0.2} className="lg:col-span-1 !p-4">
          <p className="text-[13px] font-medium text-muted-foreground mb-3">Allocation</p>
          {(p?.positions.length??0)===0?<p className="text-sm text-muted-foreground text-center py-8">No positions</p>:(
            <div className="h-48"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={p!.positions} dataKey="market_value" nameKey="symbol" cx="50%" cy="50%" outerRadius={70} innerRadius={42}>{p!.positions.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Pie><Tooltip formatter={(v:any)=>formatCurrency(Number(v))}/></PieChart></ResponsiveContainer></div>
          )}
        </GlassCard>

        {/* Holdings */}
        <GlassCard delay={0.25} className="lg:col-span-2 !p-4">
          <p className="text-[13px] font-medium text-muted-foreground mb-3">Holdings</p>
          <div className="space-y-1 max-h-[360px] overflow-y-auto">
            {(p?.positions??[]).map(pos=>(
              editingId===pos.id?(
                <div key={pos.id} className="flex items-center gap-2 p-3 rounded-2xl bg-accent"><span className="font-bold text-sm w-14">{pos.symbol}</span><Input value={editForm.quantity} onChange={e=>setEditForm({...editForm,quantity:e.target.value})} className="h-8 w-16 text-sm rounded-xl" placeholder="Qty"/><Input value={editForm.avg_cost_price} onChange={e=>setEditForm({...editForm,avg_cost_price:e.target.value})} className="h-8 w-20 text-sm rounded-xl" placeholder="Price"/><button onClick={()=>handleUpdate(pos.id)} className="cursor-pointer"><Check className="h-4 w-4 text-gain"/></button><button onClick={()=>setEditingId(null)} className="cursor-pointer"><X className="h-4 w-4 text-muted-foreground"/></button></div>
              ):(
                <div key={pos.id} className={`flex items-center gap-3 p-3 rounded-2xl cursor-pointer transition-all duration-200 group hover:bg-accent ${chartTicker===pos.symbol?"bg-accent":""}`} onClick={()=>openChart(pos.symbol)}>
                  <div className="min-w-[80px]"><p className="font-semibold text-[15px]">{pos.symbol}</p><p className="text-[12px] text-muted-foreground truncate max-w-[80px]">{pos.name}</p></div>
                  <Sparkline data={pos.sparkline} positive={pos.change>=0}/>
                  <div className="text-right flex-1"><p className="text-[14px] font-medium tabular-nums">{pos.last_price?.toFixed(2)}</p><p className={`text-[12px] ${pos.change>=0?"text-gain":"text-loss"}`}>{pos.change>=0?"+":""}{pos.change_pct.toFixed(1)}%</p></div>
                  <div className="text-right hidden sm:block min-w-[80px]"><p className="text-[14px] font-medium tabular-nums">{formatCurrency(pos.market_value)}</p><PnlBadge value={pos.unrealized_pnl}/></div>
                  <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e=>e.stopPropagation()}><button className="cursor-pointer p-1" onClick={()=>{setEditingId(pos.id);setEditForm({quantity:String(pos.quantity),avg_cost_price:String(pos.avg_cost_price)});}}><Pencil className="h-3.5 w-3.5 text-muted-foreground"/></button><button className="cursor-pointer p-1" onClick={()=>handleDelete(pos.id)}><Trash2 className="h-3.5 w-3.5 text-muted-foreground"/></button></div>
                </div>
              )
            ))}
          </div>
        </GlassCard>

        {/* Chart */}
        <GlassCard delay={0.3} className="lg:col-span-2 !p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[13px] font-medium text-muted-foreground flex items-center gap-1.5"><BarChart3 className="h-4 w-4"/>{chartTicker||"Select stock"}</p>
          </div>
          {!chartTicker?<div className="h-60 flex items-center justify-center text-muted-foreground">Click a holding</div>:(
            <>
              {(()=>{const pos=p?.positions.find(pp=>pp.symbol===chartTicker);return pos?<div className="flex items-center gap-3 mb-3"><span className="text-2xl font-bold tabular-nums">{pos.last_price?.toFixed(2)}</span><span className={`text-sm font-medium ${pos.change>=0?"text-gain":"text-loss"}`}>{pos.change>=0?"+":""}{pos.change.toFixed(2)} ({pos.change_pct>=0?"+":""}{pos.change_pct.toFixed(1)}%)</span></div>:null;})()}
              <div className="flex gap-1 mb-2">{RANGES.map(r=><button key={r.value} onClick={()=>setChartRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${chartRange===r.value?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{r.label}</button>)}</div>
              <div className="h-52">{chartLoading?<div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>:chartData.length===0?<p className="text-sm text-muted-foreground">No data</p>:(
                <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData}><defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#34c759" stopOpacity={0.2}/><stop offset="100%" stopColor="#34c759" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:10}} tickFormatter={d=>d.slice(5)} stroke="var(--muted-foreground)"/><YAxis tick={{fontSize:10}} domain={["auto","auto"]} stroke="var(--muted-foreground)"/><Tooltip formatter={(v:any)=>Number(v).toFixed(2)}/><Area type="monotone" dataKey="close" stroke="#34c759" strokeWidth={2} fill="url(#sg)"/></AreaChart></ResponsiveContainer>
              )}</div>
            </>
          )}
        </GlassCard>
      </div>

      {/* Analysis */}
      <GlassCard delay={0.35}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Brain className="h-5 w-5 text-muted-foreground"/>
            <div className="flex gap-1">{(["portfolio","economy"] as const).map(t=><button key={t} onClick={()=>setAnalysisType(t)} className={`px-4 py-1.5 rounded-xl text-[13px] font-medium transition-all cursor-pointer capitalize ${analysisType===t?"bg-primary text-primary-foreground":"text-muted-foreground hover:bg-accent"}`}>{t}</button>)}</div>
          </div>
          <button onClick={loadOlder} className="text-[13px] text-muted-foreground hover:text-foreground cursor-pointer">View older</button>
        </div>
        {showOlder&&<div className="mb-4 p-3 rounded-2xl bg-accent space-y-1">{olderList.map(a=><div key={a.id} onClick={()=>viewAnalysis(a.id)} className="flex items-center justify-between p-2 rounded-xl cursor-pointer hover:bg-muted text-[13px]"><span className="capitalize">{a.market_sentiment||"neutral"}</span><span className="text-muted-foreground">{new Date(a.created_at).toLocaleDateString()}</span></div>)}</div>}
        {!activeAnalysis?<p className="text-muted-foreground py-8 text-center">No analysis yet. Your agent will store reports here.</p>:(
          <div className="space-y-4">
            <div className="flex items-center gap-3"><span className={`text-[13px] px-3 py-1 rounded-xl font-medium capitalize ${activeAnalysis.content.market_sentiment==="bullish"?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":activeAnalysis.content.market_sentiment==="bearish"?"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400":"bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"}`}>{activeAnalysis.content.market_sentiment}</span><span className="text-[13px] text-muted-foreground">{new Date(activeAnalysis.created_at).toLocaleString()}</span></div>
            <div className="p-4 rounded-2xl bg-accent"><p className="text-[15px] leading-relaxed">{activeAnalysis.content.market_summary}</p></div>
            {activeAnalysis.content.stocks?.map(s=><div key={s.symbol} className="p-4 rounded-2xl border border-border"><div className="flex items-center justify-between mb-2"><div className="flex items-center gap-2"><span className="font-bold text-[15px]">{s.symbol}</span><span className={`text-[12px] px-2 py-0.5 rounded-lg font-medium ${s.action==="ADD"?"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400":s.action==="SELL"?"bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400":"bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400"}`}>{s.action}</span></div><div className="text-right text-[13px]"><span className="text-muted-foreground">Entry: {s.entry_price.toFixed(2)} / Now: {s.current_price.toFixed(2)}</span><span className={`ml-2 font-medium ${s.unrealized_pnl_pct>=0?"text-gain":"text-loss"}`}>{s.unrealized_pnl_pct>=0?"+":""}{s.unrealized_pnl_pct.toFixed(1)}%</span></div></div><p className="text-[14px] text-muted-foreground mb-2">{s.rationale}</p><div className="flex gap-4 text-[13px]">{s.key_risks.length>0&&<div className="flex-1"><p className="font-medium text-loss flex items-center gap-1 mb-1"><AlertTriangle className="h-3 w-3"/>Risks</p>{s.key_risks.map((r,i)=><p key={i} className="text-muted-foreground">- {r}</p>)}</div>}{s.key_catalysts.length>0&&<div className="flex-1"><p className="font-medium text-gain flex items-center gap-1 mb-1"><Zap className="h-3 w-3"/>Catalysts</p>{s.key_catalysts.map((c,i)=><p key={i} className="text-muted-foreground">- {c}</p>)}</div>}</div></div>)}
            {activeAnalysis.content.key_indicators&&activeAnalysis.content.key_indicators.length>0&&<div className="grid gap-3 grid-cols-2 md:grid-cols-4">{activeAnalysis.content.key_indicators.map((ind,i)=><div key={i} className="p-3 rounded-2xl bg-accent text-center"><p className="text-[12px] text-muted-foreground">{ind.name}</p><p className="text-xl font-bold">{ind.value}</p><p className={`text-[11px] ${ind.trend==="up"?"text-gain":ind.trend==="down"?"text-loss":"text-muted-foreground"}`}>{ind.trend==="up"?"Trending up":ind.trend==="down"?"Trending down":"Stable"}</p></div>)}</div>}
            {activeAnalysis.content.outlook&&<div className="p-4 rounded-2xl border border-border"><p className="text-[13px] font-medium mb-1">Outlook</p><p className="text-[14px] text-muted-foreground">{activeAnalysis.content.outlook}</p></div>}
          </div>
        )}
      </GlassCard>

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
