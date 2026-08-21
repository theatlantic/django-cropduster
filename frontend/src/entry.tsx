/**
 * Install the compatibility API and custom element before DOMContentLoaded,
 * then mount the page dialog after its host has been parsed.
 */

import "./styles/widget.css";

import { bindRescanListeners } from "./compat/events";
import { installGlobalApi, isDebug } from "./compat/globalApi";
import { mountPageShell } from "./components/dialog/shells/PageShell";
import { DEBUG_BODY } from "./constants/classNames";
import { defineWidgetElement } from "./dom/CropDusterWidgetElement";
import { registry } from "./dom/registry";

/** The dialog page's mount point (`cropduster/upload.html`). */
const DIALOG_APP_ID = "cropduster-app";

installGlobalApi();
defineWidgetElement();

function mountDialogApp() {
  const host = document.getElementById(DIALOG_APP_ID);
  if (host) {
    mountPageShell(host);
  }
}

function boot() {
  if (isDebug()) {
    document.body.classList.add(DEBUG_BODY);
  }
  registry.rescan();
  bindRescanListeners(() => registry.rescan());
  mountDialogApp();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
  boot();
}
