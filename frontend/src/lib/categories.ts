import { Category } from "@/lib/api";

export interface CategoryGroup extends Category {
  children: Category[];
}

/** Group flat categories into parent -> children, alphabetically sorted.
 * Shared by every category picker (transactions table, add-transaction
 * dialog, merchants page) so the grouping logic can't drift between them. */
export function groupCategories(categories: Category[]): CategoryGroup[] {
  const parents = categories
    .filter((c) => !c.parent_id)
    .sort((a, b) => a.name.localeCompare(b.name));
  const children = categories.filter((c) => c.parent_id);
  return parents.map((p) => ({
    ...p,
    children: children
      .filter((c) => c.parent_id === p.id)
      .sort((a, b) => a.name.localeCompare(b.name)),
  }));
}
