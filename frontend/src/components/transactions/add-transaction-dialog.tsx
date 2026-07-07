"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Category } from "@/lib/api";
import { groupCategories } from "@/lib/categories";
import { useCreateTransaction } from "@/hooks/queries";
import { Plus } from "lucide-react";

interface AccountOption {
  id: string;
  name: string;
  type: string;
  currency: string;
}

interface AddTransactionDialogProps {
  accounts: AccountOption[];
  categories: Category[];
  onCreated?: () => void;
}

const today = () => new Date().toISOString().split("T")[0];

const emptyForm = (accounts: AccountOption[]) => ({
  date: today(),
  merchant: "",
  amount: "",
  kind: "expense" as "expense" | "income",
  account_id: accounts[0]?.id ?? "",
  category_id: "",
  notes: "",
});

/** "Add transaction" button + dialog — the manual counterpart to CSV import.
 * Lets the user (or their agent, via the same underlying endpoint) record a
 * transaction that never came through a bank file. */
export function AddTransactionDialog({ accounts, categories, onCreated }: AddTransactionDialogProps) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm(accounts));
  const [error, setError] = useState("");
  const createTransaction = useCreateTransaction();

  const groupedCategories = groupCategories(categories);
  const selectedAccount = accounts.find((a) => a.id === form.account_id);

  const reset = () => {
    setForm(emptyForm(accounts));
    setError("");
  };

  const submit = async () => {
    setError("");
    const magnitude = parseFloat(form.amount);
    if (!form.merchant.trim()) { setError("Merchant is required."); return; }
    if (!form.account_id) { setError("Choose an account."); return; }
    if (!magnitude || magnitude <= 0) { setError("Enter an amount greater than zero."); return; }

    try {
      await createTransaction.mutateAsync({
        account_id: form.account_id,
        date: form.date,
        merchant: form.merchant.trim(),
        amount: form.kind === "expense" ? -Math.abs(magnitude) : Math.abs(magnitude),
        currency: selectedAccount?.currency ?? "CHF",
        category_id: form.category_id || undefined,
        notes: form.notes || undefined,
      });
      reset();
      setOpen(false);
      onCreated?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create transaction");
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset(); }}>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-xl bg-primary text-primary-foreground px-4 h-11 text-[15px] font-medium hover:brightness-110 active:scale-[0.98] cursor-pointer transition-all"
      >
        <Plus className="h-4 w-4" />
        Add transaction
      </button>

      <DialogContent className="rounded-3xl sm:max-w-md">
        <DialogHeader><DialogTitle>Add Transaction</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-1.5">
            {(["expense", "income"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setForm({ ...form, kind: k })}
                className={`py-2.5 rounded-xl text-[14px] font-medium transition-all cursor-pointer capitalize ${form.kind === k ? "bg-primary text-primary-foreground" : "bg-accent text-muted-foreground hover:text-foreground"}`}
              >
                {k}
              </button>
            ))}
          </div>

          <div>
            <label className="text-[13px] text-muted-foreground block mb-1.5">Merchant</label>
            <Input
              placeholder="Migros, Salary, Landlord..."
              value={form.merchant}
              onChange={(e) => setForm({ ...form, merchant: e.target.value })}
              className="rounded-xl h-11"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[13px] text-muted-foreground block mb-1.5">Amount</label>
              <Input
                type="number"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                className="rounded-xl h-11"
              />
            </div>
            <div>
              <label className="text-[13px] text-muted-foreground block mb-1.5">Date</label>
              <Input
                type="date"
                value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })}
                className="rounded-xl h-11"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[13px] text-muted-foreground block mb-1.5">Account</label>
              <select
                value={form.account_id}
                onChange={(e) => setForm({ ...form, account_id: e.target.value })}
                className="w-full h-11 rounded-xl bg-accent px-3 text-[14px] border-0 outline-none cursor-pointer"
              >
                {accounts.length === 0 && <option value="">No accounts</option>}
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[13px] text-muted-foreground block mb-1.5">Category</label>
              <select
                value={form.category_id}
                onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                className="w-full h-11 rounded-xl bg-accent px-3 text-[14px] border-0 outline-none cursor-pointer"
              >
                <option value="">Uncategorized</option>
                {groupedCategories.map((g) => (
                  <optgroup key={g.id} label={g.name}>
                    {g.children.length > 0 ? (
                      g.children.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)
                    ) : (
                      <option value={g.id}>{g.name}</option>
                    )}
                  </optgroup>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="text-[13px] text-muted-foreground block mb-1.5">Notes (optional)</label>
            <Input
              placeholder="Notes..."
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="rounded-xl h-11"
            />
          </div>

          {error && <p className="text-[13px] text-loss">{error}</p>}

          <button
            onClick={submit}
            disabled={createTransaction.isPending}
            className="w-full h-11 rounded-xl bg-primary text-primary-foreground font-semibold text-[15px] hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50"
          >
            {createTransaction.isPending ? "Saving..." : "Add Transaction"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
