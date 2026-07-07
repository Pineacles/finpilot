"use client";

import { motion } from "motion/react";
import { useOverviewQuery } from "@/hooks/queries";
import { EditLayoutBar } from "@/components/dashboard/edit-layout-bar";
import { useDashboardLayout } from "@/components/dashboard/use-dashboard-layout";
import { WIDGET_BY_ID } from "@/components/dashboard/widget-registry";

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-muted ${className ?? ""}`} />;
}

export default function OverviewPage() {
  const { data, isLoading } = useOverviewQuery();
  const { layout, loading: layoutLoading } = useDashboardLayout();

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";

  const visibleWidgets = layout.filter((item) => item.visible && WIDGET_BY_ID[item.id]);

  if (isLoading || layoutLoading) {
    return (
      <div className="space-y-8">
        <Skeleton className="h-10 w-56" />
        <div className="grid gap-[18px] grid-cols-2">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-56" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <h2 className="text-[28px] font-bold" style={{ letterSpacing: "-0.6px" }}>
          Good {greeting}{data?.display_name ? `, ${data.display_name}` : ""}
        </h2>
        <p className="text-muted-foreground mt-1 text-[14px]">Here&apos;s how your finances are looking today.</p>
      </motion.div>

      <EditLayoutBar />

      <div className="grid gap-[18px] grid-cols-1 md:grid-cols-2">
        {visibleWidgets.map(({ id }) => {
          const Widget = WIDGET_BY_ID[id].component;
          const span = WIDGET_BY_ID[id].span;
          return (
            <div key={id} className={span === "full" ? "md:col-span-2" : undefined}>
              <Widget />
            </div>
          );
        })}
      </div>
    </div>
  );
}
