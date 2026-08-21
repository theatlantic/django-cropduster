import { createContext, useContext } from "react";

import type { WidgetConfig } from "../../dom/config";
import type { WidgetSlots } from "../../dom/WidgetInstance";
import type { FormsetBridge, WidgetState } from "../../formset/FormsetBridge";

export interface WidgetContextValue {
  /** The `.cropduster-form` wrapper the widget owns. */
  root: HTMLElement;
  config: WidgetConfig;
  bridge: FormsetBridge;
  slots: WidgetSlots;
  state: WidgetState;
}

export const WidgetContext = createContext<WidgetContextValue | null>(null);

export function useWidget(): WidgetContextValue {
  const value = useContext(WidgetContext);
  if (!value) {
    throw new Error("cropduster: widget component rendered outside a widget");
  }
  return value;
}
