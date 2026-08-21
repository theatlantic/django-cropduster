/**
 * Render the full-page dialog opened by `CropDuster.show()` or CKEditor.
 *
 * An open shadow root isolates the dialog from admin and grappelli styles while
 * remaining accessible to Selenium and CKEditor. Dialog styles are embedded in
 * the bundle because linked stylesheets cannot cross the shadow boundary.
 */

import { useCallback, useMemo } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";

import { readDialogConfig } from "../../../state/dialogConfig";
import type { DialogConfig } from "../../../state/dialogConfig";
import type { LegacyCompletePayload } from "../../../formset/legacyPayload";
import {
  closeDialogWindow,
  deliverCompletion,
} from "../../../window/completeChannel";
import { DialogApp } from "../DialogApp";
import { ShellContext } from "../shellContext";
import type { ShellContextValue } from "../shellContext";
import { adoptDialogStyles } from "./adoptStyles";

export interface PageShellProps {
  config: DialogConfig;
  container: HTMLElement;
  /** The window the dialog reports to and closes; injectable for tests. */
  view?: Window;
}

export function PageShell({ config, container, view }: PageShellProps) {
  const target = view ?? window;

  const onCommit = useCallback(
    (payload: LegacyCompletePayload) => {
      deliverCompletion(
        payload,
        { elId: config.elId, callbackFn: config.callbackFn },
        target,
      );
      // 4.x closed unconditionally, including when nothing was listening; in
      // CKEditor's iframe the call is a no-op and its own OK handler hides the
      // dialog.
      closeDialogWindow(target);
    },
    [config.callbackFn, config.elId, target],
  );

  const shell = useMemo<ShellContextValue>(
    () => ({
      container,
      onCommit,
      onCancel: () => closeDialogWindow(target),
      publish: (api) => {
        if (api) {
          target.CropDusterDialog = api;
        } else {
          delete target.CropDusterDialog;
        }
      },
    }),
    [container, onCommit, target],
  );

  return (
    <ShellContext.Provider value={shell}>
      <DialogApp config={config} />
    </ShellContext.Provider>
  );
}

const mounted = new WeakMap<Element, Root>();

export interface MountOptions {
  view?: Window;
}

/**
 * Mount the dialog on a page that has a `#cropduster-app` element. Idempotent:
 * a second call on the same host returns the root the first one made.
 */
export function mountPageShell(
  host: HTMLElement,
  options: MountOptions = {},
): Root {
  const existing = mounted.get(host);
  if (existing) {
    return existing;
  }

  const view = options.view ?? window;
  const shadow = host.shadowRoot ?? host.attachShadow({ mode: "open" });
  adoptDialogStyles(shadow, "page");

  const container = host.ownerDocument.createElement("div");
  container.className = "cropduster-dialog-root";
  shadow.appendChild(container);

  const config = readDialogConfig(host, {
    search: view.location.search,
    pathname: view.location.pathname,
  });

  const root = createRoot(container);
  mounted.set(host, root);
  root.render(<PageShell config={config} container={container} view={view} />);
  return root;
}
