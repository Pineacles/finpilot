"use client";

import { useCallback, useMemo } from "react";
import { useSettingsQuery, useUpdateSettings } from "@/hooks/queries";
import { DEFAULT_LAYOUT, LayoutItem, WIDGET_BY_ID, WidgetId } from "./widget-registry";

const SETTINGS_KEY = "dashboard_layout";

function parseLayout(raw: string | undefined): LayoutItem[] {
  if (!raw) return DEFAULT_LAYOUT;
  try {
    const parsed = JSON.parse(raw) as LayoutItem[];
    if (!Array.isArray(parsed) || parsed.length === 0) return DEFAULT_LAYOUT;
    // Drop entries for widgets that no longer exist, then append any new
    // widgets (added to the registry after this layout was saved) as visible.
    const known = parsed.filter((item) => item && WIDGET_BY_ID[item.id]);
    const knownIds = new Set(known.map((item) => item.id));
    const missing = DEFAULT_LAYOUT.filter((item) => !knownIds.has(item.id));
    return [...known, ...missing];
  } catch {
    return DEFAULT_LAYOUT;
  }
}

/** Persists widget visibility + order as JSON under the `dashboard_layout`
 * user setting (generic k/v store, see backend/app/services/settings.py).
 * Array order IS the display order; no separate `order` field needed. */
export function useDashboardLayout() {
  const settingsQuery = useSettingsQuery();
  const updateSettings = useUpdateSettings();

  const layout = useMemo(() => parseLayout(settingsQuery.data?.settings?.[SETTINGS_KEY]), [settingsQuery.data]);

  const persist = useCallback(
    (next: LayoutItem[]) => updateSettings.mutateAsync({ [SETTINGS_KEY]: JSON.stringify(next) }),
    [updateSettings],
  );

  const toggleVisible = useCallback((id: WidgetId) => {
    persist(layout.map((item) => (item.id === id ? { ...item, visible: !item.visible } : item)));
  }, [layout, persist]);

  const move = useCallback((id: WidgetId, direction: -1 | 1) => {
    const idx = layout.findIndex((item) => item.id === id);
    const swapWith = idx + direction;
    if (idx < 0 || swapWith < 0 || swapWith >= layout.length) return;
    const next = [...layout];
    [next[idx], next[swapWith]] = [next[swapWith], next[idx]];
    persist(next);
  }, [layout, persist]);

  const resetToDefault = useCallback(() => persist(DEFAULT_LAYOUT), [persist]);

  return {
    layout,
    loading: settingsQuery.isLoading,
    saving: updateSettings.isPending,
    toggleVisible,
    moveUp: (id: WidgetId) => move(id, -1),
    moveDown: (id: WidgetId) => move(id, 1),
    resetToDefault,
  };
}
