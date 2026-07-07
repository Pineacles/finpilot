"use client";

import { Search, X } from "lucide-react";
import { cn } from "@/lib/format";

interface TransactionFiltersProps {
  value: string;
  onChange: (value: string) => void;
}

/** Search bar for the transactions table — merchant, description, category. */
export function TransactionFilters({ value, onChange }: TransactionFiltersProps) {
  return (
    <div className="relative">
      <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search merchant, description, category..."
        className={cn(
          "w-full h-[44px] rounded-[14px] bg-accent pl-10 pr-4 text-[15px] outline-none",
          "placeholder:text-muted-foreground/60 transition-all",
          "focus:ring-2 focus:ring-primary/30",
        )}
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 cursor-pointer"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
      )}
    </div>
  );
}
