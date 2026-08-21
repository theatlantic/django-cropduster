import "./styles/widget.css";

import { bindRescanListeners } from "./compat/events";
import { installGlobalApi, isDebug } from "./compat/globalApi";
import { DEBUG_BODY } from "./constants/classNames";
import { defineWidgetElement } from "./dom/CropDusterWidgetElement";
import { registry } from "./dom/registry";

installGlobalApi();
defineWidgetElement();

function boot() {
  if (isDebug()) {
    document.body.classList.add(DEBUG_BODY);
  }
  registry.rescan();
  bindRescanListeners(() => registry.rescan());
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
  boot();
}
