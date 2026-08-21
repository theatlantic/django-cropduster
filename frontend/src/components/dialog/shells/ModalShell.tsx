/**
 * Render the crop dialog in an open shadow root above the current page.
 *
 * The panel is a native `<dialog>` opened with `showModal()`: the browser
 * keeps it in the top layer above any page z-index, makes the page behind it
 * inert, and confines the tab order to the dialog. Only one modal may be
 * open. Completion retains the widget supplied at open time, so a formset
 * rename cannot redirect the result. `close()` restores page scrolling and
 * focus.
 */

import {
  Component,
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
} from "react";
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
} from "react";
import { createRoot } from "react-dom/client";

import { CLOSE_LABEL, DIALOG_LABEL } from "../../../constants/dialogLabels";
import type { DialogConfig } from "../../../state/dialogConfig";
import type { DialogRendererData } from "../../../state/types";
import type { LegacyCompletePayload } from "../../../formset/legacyPayload";
import { DialogApp } from "../DialogApp";
import { ShellContext } from "../shellContext";
import type { DialogWindowApi, ShellContextValue } from "../shellContext";
import { adoptDialogStyles, releaseDialogStyles } from "./adoptStyles";

export const MODAL_TAG = "cropduster-dialog";

export const MODAL_HOST_CLASS = "cropduster-dialog";

const PANEL_CLASS = "cropduster-modal-panel";
const CLOSE_CLASS = "cropduster-modal-close";

export interface ModalHandle {
  readonly host: HTMLElement;
  readonly shadow: ShadowRoot;
  /** Tear the modal down. Idempotent. */
  close(): void;
}

export interface OpenModalOptions {
  config: DialogConfig;
  /**
   * A finished crop, in the shape `CropDuster.complete` takes, plus the
   * renderer-routed URL per thumb name, which that shape has no field for.
   */
  onComplete(
    payload: LegacyCompletePayload,
    rendererData?: DialogRendererData,
  ): void;
  /** Called once the modal is closed, whatever closed it. */
  onClose?(): void;
  /** The document to open in; injectable for tests. */
  document?: Document;
}

interface ModalShellProps {
  config: DialogConfig;
  container: HTMLElement;
  onCommit(
    payload: LegacyCompletePayload,
    rendererData?: DialogRendererData,
  ): void;
  onCancel(): void;
  publish(api: DialogWindowApi | null): void;
}

function ModalShell({
  config,
  container,
  onCommit,
  onCancel,
  publish,
}: ModalShellProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Open before first paint, or the panel would flash in page flow for one
  // frame. Focus starts on the panel so the first Tab remains inside the
  // dialog.
  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) {
      dialog.showModal();
      dialog.focus();
    }
  }, []);

  // With the page inert, every Escape press starts inside the dialog and
  // bubbles here, so an element that owns Escape (an open menu) handles the
  // key first and stops it. preventDefault also stops the browser's own
  // cancel-on-Escape, which would close the dialog a second time.
  const onDialogKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDialogElement>) => {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      onCancel();
    },
    [onCancel],
  );

  // Backdrop hits target the dialog element itself; the app's content covers
  // the whole panel, so a press anywhere inside it targets a descendant.
  // Confirm that both pointer up and pointer down occur on the backdrop
  // before dismissing the dialog. This prevents accidental closes on drags
  // that begin inside the modal (for instance, on a drag handle) but are
  // released outside it.
  const pressedBackdrop = useRef(false);
  const onBackdropPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDialogElement>) => {
      pressedBackdrop.current = event.target === event.currentTarget;
    },
    [],
  );
  const onBackdropPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLDialogElement>) => {
      const pressed = pressedBackdrop.current;
      pressedBackdrop.current = false;
      if (pressed && event.target === event.currentTarget) {
        onCancel();
      }
    },
    [onCancel],
  );

  const shell = useMemo<ShellContextValue>(
    () => ({ container, onCommit, onCancel, publish }),
    [container, onCancel, onCommit, publish],
  );

  return (
    <ShellContext.Provider value={shell}>
      <dialog
        ref={dialogRef}
        className={PANEL_CLASS}
        part="panel"
        aria-label={DIALOG_LABEL}
        tabIndex={-1}
        onKeyDown={onDialogKeyDown}
        // A close this shell did not initiate (a forced cancel, a
        // `method="dialog"` form) still tears everything down.
        onClose={onCancel}
        onPointerDown={onBackdropPointerDown}
        onPointerUp={onBackdropPointerUp}
      >
        <button
          id="dialog-close"
          type="button"
          className={CLOSE_CLASS}
          part="close"
          aria-label={CLOSE_LABEL}
          onClick={onCancel}
        >
          &times;
        </button>
        <DialogApp config={config} />
      </dialog>
    </ShellContext.Provider>
  );
}

interface BoundaryProps {
  onError(error: unknown): void;
  children: ReactNode;
}

/**
 * Close and release the modal if React throws while rendering. Async request
 * failures are handled by the reducer.
 */
class ModalErrorBoundary extends Component<BoundaryProps, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    this.props.onError(error);
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

let current: ModalHandle | null = null;

export function currentModal(): ModalHandle | null {
  return current;
}

/** Open the page-wide modal, or return the one already open. */
export function openModalDialog(options: OpenModalOptions): ModalHandle {
  if (current) {
    return current;
  }

  const doc = options.document ?? document;
  const view = doc.defaultView;

  const host = doc.createElement(MODAL_TAG);
  host.className = MODAL_HOST_CLASS;
  host.setAttribute("data-state", "open");
  const shadow = host.attachShadow({ mode: "open" });
  adoptDialogStyles(shadow, "modal");

  const container = doc.createElement("div");
  container.className = "cropduster-dialog-root";
  shadow.appendChild(container);
  doc.body.appendChild(host);

  // showModal() makes the page inert but does not stop it from scrolling.
  const restoreOverflow = doc.body.style.overflow;
  doc.body.style.overflow = "hidden";
  const previouslyFocused = doc.activeElement;

  const publish = (api: DialogWindowApi | null) => {
    if (!view) {
      return;
    }
    if (api) {
      view.CropDusterDialog = api;
    } else {
      delete view.CropDusterDialog;
    }
  };

  const root = createRoot(container);

  let closed = false;
  const close = () => {
    if (closed) {
      return;
    }
    closed = true;
    if (current === handle) {
      current = null;
    }
    doc.body.style.overflow = restoreOverflow;
    publish(null);
    releaseDialogStyles(shadow);
    host.setAttribute("data-state", "closed");
    shadow.querySelector("dialog")?.close();
    // dialog.close() restores focus on its own, but not on the render-crash
    // path, where showModal() never ran.
    if (previouslyFocused instanceof HTMLElement) {
      previouslyFocused.focus();
    }
    // React cannot unmount this root from its own event handler.
    queueMicrotask(() => {
      root.unmount();
      host.remove();
    });
    options.onClose?.();
  };

  const handle: ModalHandle = { host, shadow, close };
  current = handle;

  root.render(
    <ModalErrorBoundary
      onError={(error) => {
        console.error("cropduster: the crop dialog failed to render", error);
        close();
      }}
    >
      <ModalShell
        config={options.config}
        container={container}
        onCommit={(payload, rendererData) => {
          options.onComplete(payload, rendererData);
          close();
        }}
        onCancel={close}
        publish={publish}
      />
    </ModalErrorBoundary>,
  );

  return handle;
}
