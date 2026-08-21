/**
 * The crop header's source control: a chip naming the current image, opening
 * a menu with the file's metadata, the replace action, and a full-size link.
 *
 * The menu reserves space for per-crop override sources; new entries
 * insert between the metadata block and the replace action.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  FocusEvent as ReactFocusEvent,
  KeyboardEvent as ReactKeyboardEvent,
} from "react";

import {
  IMAGE_CHIP_LABEL,
  REPLACE_IMAGE,
  SOURCE_MENU_LABEL,
  VIEW_FULL_SIZE,
  replaceResets,
} from "../../constants/dialogLabels";
import {
  displayFilename,
  imageDetail,
  middleTruncate,
} from "../../lib/filename";
import { primarySource } from "../../state/dialogReducer";
import { useDialog } from "../../state/DialogContext";

const MENU_ITEM = "[role='menuitem']";

export function SourceChip() {
  const { state, controller } = useDialog();
  const source = primarySource(state);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const close = useCallback((refocus: boolean) => {
    setOpen(false);
    if (refocus) {
      chipRef.current?.focus();
    }
  }, []);

  // Dismiss on any click outside the chip and menu. Capture phase, so the
  // dismissing click cannot also activate whatever is under it (the modal
  // backdrop in particular, whose click closes the whole dialog).
  useEffect(() => {
    if (!open) {
      return;
    }
    const doc = wrapRef.current?.ownerDocument ?? document;
    const onDocumentClick = (event: MouseEvent) => {
      const wrap = wrapRef.current;
      if (wrap && event.composedPath().includes(wrap)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    };
    doc.addEventListener("click", onDocumentClick, true);
    return () => doc.removeEventListener("click", onDocumentClick, true);
  }, [open]);

  useEffect(() => {
    if (open) {
      menuRef.current?.querySelector<HTMLElement>(MENU_ITEM)?.focus();
    }
  }, [open]);

  const onBlur = (event: ReactFocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget;
    if (open && (!(next instanceof Node) || !wrapRef.current?.contains(next))) {
      setOpen(false);
    }
  };

  const onChipKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      setOpen(true);
    }
  };

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      // Stop the press before it bubbles to the modal shell's own Escape
      // handler; preventDefault also stops the browser from treating it as a
      // dialog cancel. Only the menu closes.
      event.preventDefault();
      event.stopPropagation();
      close(true);
      return;
    }
    const items = [
      ...(menuRef.current?.querySelectorAll<HTMLElement>(MENU_ITEM) ?? []),
    ];
    if (!items.length) {
      return;
    }
    const from =
      event.target instanceof Element
        ? items.indexOf(event.target.closest(MENU_ITEM) as HTMLElement)
        : -1;
    let to = -1;
    if (event.key === "ArrowDown") {
      to = from < 0 ? 0 : (from + 1) % items.length;
    } else if (event.key === "ArrowUp") {
      to = from <= 0 ? items.length - 1 : from - 1;
    } else if (event.key === "Home") {
      to = 0;
    } else if (event.key === "End") {
      to = items.length - 1;
    } else {
      return;
    }
    event.preventDefault();
    items[to]?.focus();
  };

  if (!source.name) {
    return null;
  }

  const filename = displayFilename(source.name);
  const detail = imageDetail(source.width, source.height, filename);
  const chipDisabled = state.phase !== "crop" || state.hydrating;

  return (
    <div
      ref={wrapRef}
      className="source-chip-wrap"
      part="source"
      onBlur={onBlur}
    >
      <button
        ref={chipRef}
        id="source-chip"
        type="button"
        className="source-chip"
        part="source-chip"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? "source-menu" : undefined}
        title={filename}
        disabled={chipDisabled}
        onClick={() => (open ? close(true) : setOpen(true))}
        onKeyDown={onChipKeyDown}
      >
        <span className="source-chip-label">{IMAGE_CHIP_LABEL}</span>
        <span className="source-chip-value">{middleTruncate(filename)}</span>
        <span className="source-chip-caret" aria-hidden="true" />
      </button>
      {open ? (
        <div
          ref={menuRef}
          id="source-menu"
          className="source-menu"
          part="source-menu"
          role="menu"
          aria-label={SOURCE_MENU_LABEL}
          onKeyDown={onMenuKeyDown}
        >
          <div className="source-menu-meta" part="source-menu-meta">
            <div className="source-menu-filename">{filename}</div>
            {detail ? <div className="source-menu-detail">{detail}</div> : null}
          </div>
          <div className="source-menu-divider" role="separator" />
          <button
            id="replace-image-menuitem"
            type="button"
            role="menuitem"
            tabIndex={-1}
            className="source-menu-item"
            part="source-menu-item"
            onClick={() => {
              close(false);
              controller.beginReplace();
            }}
          >
            <span className="source-menu-item-title">{REPLACE_IMAGE}</span>
            <span className="source-menu-item-detail">
              {replaceResets(state.sizes.length)}
            </span>
          </button>
          {source.url ? (
            <>
              <div className="source-menu-divider" role="separator" />
              <a
                id="view-full-size-menuitem"
                role="menuitem"
                tabIndex={-1}
                className="source-menu-item"
                part="source-menu-item"
                href={source.url}
                target="_blank"
                rel="noreferrer"
                onClick={() => close(true)}
              >
                <span className="source-menu-item-title">
                  {VIEW_FULL_SIZE}
                  <svg
                    className="source-menu-item-icon"
                    viewBox="0 0 12 12"
                    aria-hidden="true"
                  >
                    <path d="M4.75 1.5H2.5A1 1 0 0 0 1.5 2.5v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V7.25M7 1.5h3.5V5M10.25 1.75 5.5 6.5" />
                  </svg>
                </span>
              </a>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
