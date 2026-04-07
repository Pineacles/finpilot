"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { api, MonthlyStats, YearlyStats, TransactionItem } from "@/lib/api";
import { formatCurrency, formatPct, formatDate } from "@/lib/format";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, PieChart, Pie, Cell, LineChart, Line, AreaChart, Area } from "recharts";
import { ChevronLeft, ChevronRight, Calendar, Wallet, PiggyBank, Receipt, Store, CreditCard, ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import { useRouter } from "next/navigation";

const COLORS = ["#34c759","#007aff","#ff9500","#ff3b30","#af52de","#ff2d55","#5ac8fa","#4cd964"];
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function GlassCard({children,className="",delay=0}:{children:React.ReactNode;className?:string;delay?:number}){
  return <motion.div initial={{opacity:0,y:16}} animate={{opacity:1,y:0}} transition={{duration:0.45,delay,ease:[0.25,0.46,0.45,0.94]}} className={`glass bg-card rounded-3xl p-6 ${className}`}>{children}</motion.div>;
}

function Change({value,pct,expense=false}:{value:number;pct:number;expense?:boolean}){
  if(Math.abs(pct)<0.5)return <span className="text-[13px] text-muted-foreground flex items-center gap-1"><Minus className="h-3 w-3"/>No change</span>;
  const up=value>0; const good=expense?!up:up;
  return <span className={`text-[13px] flex items-center gap-1 font-medium ${good?"text-gain":"text-loss"}`}>{up?<ArrowUpRight className="h-3 w-3"/>:<ArrowDownRight className="h-3 w-3"/>}{formatCurrency(Math.abs(value))} ({formatPct(pct)})</span>;
}

function CategoryDrillDown({open,onClose,categoryName,categoryId,fromDate,toDate}:{open:boolean;onClose:()=>void;categoryName:string;categoryId:string|null;fromDate:string;toDate:string}){
  const router=useRouter();
  const [txns,setTxns]=useState<TransactionItem[]>([]);const [ld,setLd]=useState(false);
  useEffect(()=>{if(!open||!categoryId)return;setLd(true);api.transactions({category_id:categoryId,from_date:fromDate,to_date:toDate,limit:500}).then(setTxns).finally(()=>setLd(false));},[open,categoryId,fromDate,toDate]);
  const total=txns.reduce((s,t)=>s+Math.abs(t.amount),0);
  return <Dialog open={open} onOpenChange={v=>{if(!v)onClose();}}><DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col rounded-3xl"><DialogHeader><DialogTitle>{categoryName} — {txns.length} transactions</DialogTitle><p className="text-[13px] text-muted-foreground">{fromDate} to {toDate} — Total: {formatCurrency(total)}</p></DialogHeader><div className="overflow-y-auto flex-1 -mx-6 px-6">{ld?<p className="text-muted-foreground py-4">Loading...</p>:txns.length===0?<p className="text-muted-foreground py-4">No transactions.</p>:<table className="w-full text-[14px]"><thead><tr className="border-b text-left text-muted-foreground text-[13px]"><th className="pb-2 font-medium">Date</th><th className="pb-2 font-medium">Merchant</th><th className="pb-2 font-medium text-right">Amount</th></tr></thead><tbody>{txns.map(t=><tr key={t.id} className="border-b border-border/50 cursor-pointer hover:bg-accent/30 transition-colors" onClick={()=>router.push(`/transactions?highlight=${t.id}`)}><td className="py-2 text-muted-foreground whitespace-nowrap">{formatDate(t.date)}</td><td className="py-2 font-medium">{t.merchant}</td><td className={`py-2 text-right font-medium tabular-nums ${t.amount<0?"text-loss":"text-gain"}`}>{formatCurrency(t.amount,t.currency)}</td></tr>)}</tbody></table>}</div></DialogContent></Dialog>;
}

export default function StatsPage(){
  const today=new Date();
  const [tab,setTab]=useState("monthly");
  const [year,setYear]=useState(today.getFullYear());
  const [month,setMonth]=useState(today.getMonth()+1);
  const [monthly,setMonthly]=useState<MonthlyStats|null>(null);
  const [yearly,setYearly]=useState<YearlyStats|null>(null);
  const [loading,setLoading]=useState(true);
  const [drillCat,setDrillCat]=useState<{id:string|null;name:string}|null>(null);

  useEffect(()=>{setLoading(true);if(tab==="monthly")api.monthlyStats(year,month).then(setMonthly).finally(()=>setLoading(false));else api.yearlyStats(year).then(setYearly).finally(()=>setLoading(false));},[tab,year,month]);
  const prevMonth=()=>{if(month===1){setMonth(12);setYear(year-1);}else setMonth(month-1);};
  const nextMonth=()=>{if(month===12){setMonth(1);setYear(year+1);}else setMonth(month+1);};

  return (
    <div className="space-y-8">
      <motion.div initial={{opacity:0}} animate={{opacity:1}} className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold tracking-tight">Statistics</h1>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">{["monthly","yearly"].map(t=><button key={t} onClick={()=>setTab(t)} className={`px-4 py-2 rounded-xl text-[14px] font-medium transition-all cursor-pointer capitalize ${tab===t?"bg-primary text-primary-foreground":"glass bg-card text-muted-foreground hover:text-foreground"}`}>{t}</button>)}</div>
          <div className="flex items-center gap-2">
            <button onClick={tab==="monthly"?prevMonth:()=>setYear(year-1)} className="h-9 w-9 rounded-xl glass bg-card flex items-center justify-center cursor-pointer hover:bg-accent"><ChevronLeft className="h-4 w-4"/></button>
            <span className="text-[14px] font-medium w-28 text-center">{tab==="monthly"?`${MONTHS[month-1]} ${year}`:String(year)}</span>
            <button onClick={tab==="monthly"?nextMonth:()=>setYear(year+1)} className="h-9 w-9 rounded-xl glass bg-card flex items-center justify-center cursor-pointer hover:bg-accent"><ChevronRight className="h-4 w-4"/></button>
          </div>
        </div>
      </motion.div>

      {loading?<div className="grid gap-5 md:grid-cols-4">{[...Array(4)].map((_,i)=><div key={i} className="h-28 rounded-3xl bg-muted animate-pulse"/>)}</div>:tab==="monthly"&&monthly?(()=>{
        const s=monthly.summary;const totalForPie=monthly.categories.reduce((sum,c)=>sum+c.total,0);
        return <>
          {/* KPIs */}
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            {[{l:"Income",v:formatCurrency(s.income),color:"text-gain",cmp:monthly.comparison.income,icon:Wallet},{l:"Expenses",v:formatCurrency(s.expenses),color:"text-loss",cmp:monthly.comparison.expenses,expense:true,icon:Receipt},{l:"Net / Saved",v:formatCurrency(s.net),color:s.net>=0?"text-gain":"text-loss",cmp:monthly.comparison.net,icon:PiggyBank},{l:"Daily Average",v:formatCurrency(s.avg_daily_spend),sub:`${s.txn_count} transactions`,icon:Calendar}].map((k,i)=>(
              <GlassCard key={k.l} delay={0.05+i*0.03}>
                <div className="flex items-center gap-2 mb-3"><k.icon className="h-4 w-4 text-muted-foreground"/><span className="text-[13px] text-muted-foreground">{k.l}</span></div>
                <p className={`text-2xl font-bold ${k.color||""}`}>{k.v}</p>
                {k.cmp&&<Change value={k.cmp.change} pct={k.cmp.change_pct} expense={k.expense}/>}
                {k.sub&&<span className="text-[13px] text-muted-foreground">{k.sub}</span>}
              </GlassCard>
            ))}
          </div>

          {/* Charts */}
          <div className="grid gap-5 lg:grid-cols-2">
            <GlassCard delay={0.15}>
              <h2 className="text-lg font-semibold mb-4">Spending by Category</h2>
              {monthly.categories.length===0?<p className="text-muted-foreground">No data.</p>:<div className="h-72"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={monthly.categories} dataKey="total" nameKey="name" cx="50%" cy="50%" outerRadius={90} innerRadius={55} label={((e:any)=>`${e.name} ${((e.percent??0)*100).toFixed(0)}%`) as any}>{monthly.categories.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Pie><Tooltip formatter={(v:any)=>formatCurrency(Number(v))}/></PieChart></ResponsiveContainer></div>}
            </GlassCard>
            <GlassCard delay={0.2}>
              <h2 className="text-lg font-semibold mb-4">Category Breakdown</h2>
              <div className="space-y-3 max-h-72 overflow-y-auto">{monthly.categories.map((c,i)=>{const pct=totalForPie?(c.total/totalForPie)*100:0;return <div key={c.name} className="cursor-pointer hover:bg-accent/50 rounded-xl p-2 -mx-2 transition-colors" onClick={()=>setDrillCat({id:c.id,name:c.name})}><div className="flex items-center justify-between text-[14px] mb-1"><div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full" style={{backgroundColor:COLORS[i%COLORS.length]}}/><span>{c.name}</span></div><div className="flex items-center gap-2"><span className="text-muted-foreground text-[13px]">{c.count} txns</span><span className="font-medium">{formatCurrency(c.total)}</span></div></div><div className="h-2 rounded-full bg-secondary overflow-hidden"><motion.div initial={{width:0}} animate={{width:`${pct}%`}} transition={{duration:0.6,delay:0.3+i*0.03}} className="h-full rounded-full" style={{backgroundColor:COLORS[i%COLORS.length]}}/></div></div>})}</div>
            </GlassCard>
          </div>

          {/* Spending Pace + Fixed vs Variable */}
          <div className="grid gap-5 lg:grid-cols-2">
            <GlassCard delay={0.25}>
              <h2 className="text-lg font-semibold mb-4">Spending Pace</h2>
              <div className="h-64">{monthly.spending_velocity.length===0?<p className="text-muted-foreground">No data.</p>:<ResponsiveContainer width="100%" height="100%"><AreaChart data={monthly.spending_velocity}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="date" tick={{fontSize:11}} tickFormatter={d=>d.slice(8)} stroke="var(--muted-foreground)"/><YAxis tick={{fontSize:11}} tickFormatter={v=>`${(v/1000).toFixed(1)}k`} stroke="var(--muted-foreground)"/><Tooltip formatter={(v:any)=>formatCurrency(Number(v))}/><Area type="monotone" dataKey="cumulative" stroke="#34c759" fill="#34c759" fillOpacity={0.12} strokeWidth={2}/></AreaChart></ResponsiveContainer>}</div>
            </GlassCard>
            <GlassCard delay={0.3}>
              <h2 className="text-lg font-semibold mb-4">Fixed vs Variable</h2>
              <div className="space-y-6 pt-4">{[{l:"Recurring / Fixed",v:monthly.recurring_vs_discretionary.recurring,color:"bg-primary"},{l:"Discretionary",v:monthly.recurring_vs_discretionary.discretionary,color:"bg-amber-500"}].map(item=><div key={item.l}><div className="flex justify-between text-[14px] mb-2"><span>{item.l}</span><span className="font-medium">{formatCurrency(item.v)}</span></div><div className="h-3 rounded-full bg-secondary overflow-hidden"><div className={`h-full rounded-full ${item.color}`} style={{width:`${s.expenses?(item.v/s.expenses)*100:0}%`}}/></div></div>)}<p className="text-[13px] text-muted-foreground">{s.expenses?((monthly.recurring_vs_discretionary.recurring/s.expenses)*100).toFixed(0):0}% of spending is fixed costs</p></div>
            </GlassCard>
          </div>

          {/* Account Breakdown */}
          {monthly.account_breakdown?.length>0&&<GlassCard delay={0.35}><h2 className="text-lg font-semibold mb-4 flex items-center gap-2"><CreditCard className="h-5 w-5"/>Spending by Account</h2><div className="grid gap-4 md:grid-cols-2">{monthly.account_breakdown.map(a=><div key={a.name} className="flex items-center justify-between p-4 rounded-2xl bg-accent"><div className="flex items-center gap-3"><div className={`w-3 h-3 rounded-full ${a.type==="credit_card"?"bg-orange-500":"bg-blue-500"}`}/><div><p className="text-[15px] font-medium">{a.name}</p><p className="text-[13px] text-muted-foreground">{a.count} transactions</p></div></div><p className="text-[15px] font-bold">{formatCurrency(a.total)}</p></div>)}</div></GlassCard>}

          {/* Top Merchants + Budget */}
          <div className="grid gap-5 lg:grid-cols-2">
            <GlassCard delay={0.4}><h2 className="text-lg font-semibold mb-4 flex items-center gap-2"><Store className="h-5 w-5"/>Top Merchants</h2>{monthly.top_merchants.length===0?<p className="text-muted-foreground">No data.</p>:<div className="space-y-3">{monthly.top_merchants.map((m,i)=><div key={m.merchant} className="flex items-center justify-between"><div className="flex items-center gap-3"><span className="text-muted-foreground w-5 text-right text-[13px]">{i+1}.</span><span className="text-[15px]">{m.merchant}</span></div><div className="flex items-center gap-2"><Badge variant="secondary" className="rounded-lg text-[12px]">{m.count}x</Badge><span className="font-medium text-[15px]">{formatCurrency(m.total)}</span></div></div>)}</div>}</GlassCard>
            <GlassCard delay={0.45}><h2 className="text-lg font-semibold mb-4">Budget vs Actual</h2>{monthly.budget_vs_actual.length===0?<p className="text-muted-foreground">No budgets.</p>:<div className="space-y-4">{monthly.budget_vs_actual.map(b=><div key={b.name}><div className="flex justify-between text-[14px] mb-1"><span>{b.name}</span><span className={b.pct>100?"text-loss font-medium":"text-muted-foreground"}>{formatCurrency(b.spent)} / {formatCurrency(b.budget)}</span></div><div className="h-2.5 rounded-full bg-secondary overflow-hidden"><div className={`h-full rounded-full ${b.pct>100?"bg-loss":"bg-primary"}`} style={{width:`${Math.min(b.pct,100)}%`}}/></div></div>)}</div>}</GlassCard>
          </div>

          {drillCat&&<CategoryDrillDown open={!!drillCat} onClose={()=>setDrillCat(null)} categoryName={drillCat.name} categoryId={drillCat.id} fromDate={monthly.period.start} toDate={monthly.period.end}/>}
        </>;
      })():tab==="yearly"&&yearly?(()=>{
        const s=yearly.summary;const monthlyData=yearly.monthly.map(m=>({...m,name:MONTHS[m.month-1]}));
        return <>
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">{[{l:"Total Income",v:formatCurrency(s.income),color:"text-gain"},{l:"Total Expenses",v:formatCurrency(s.expenses),color:"text-loss"},{l:"Net Saved",v:formatCurrency(s.net),color:s.net>=0?"text-gain":"text-loss"},{l:"Transactions",v:String(s.txn_count)}].map((k,i)=><GlassCard key={k.l} delay={0.05+i*0.03}><p className="text-[13px] text-muted-foreground mb-2">{k.l}</p><p className={`text-2xl font-bold ${k.color||""}`}>{k.v}</p></GlassCard>)}</div>
          <GlassCard delay={0.2}><h2 className="text-lg font-semibold mb-4">Monthly Income vs Expenses</h2><div className="h-80">{monthlyData.length===0?<p className="text-muted-foreground">No data.</p>:<ResponsiveContainer width="100%" height="100%"><BarChart data={monthlyData}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="name" tick={{fontSize:11}}/><YAxis tick={{fontSize:11}} tickFormatter={v=>`${(v/1000).toFixed(0)}k`}/><Tooltip formatter={(v:any)=>formatCurrency(Number(v))}/><Legend/><Bar dataKey="income" fill="#007aff" name="Income" radius={[4,4,0,0]}/><Bar dataKey="expenses" fill="#ff3b30" name="Expenses" radius={[4,4,0,0]}/></BarChart></ResponsiveContainer>}</div></GlassCard>
        </>;
      })():<div className="h-64 rounded-3xl bg-muted animate-pulse"/>}
    </div>
  );
}
