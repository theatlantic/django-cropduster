/**
 * Render the upload button into the existing anchor and handle clicks on that
 * anchor so dynamically inserted rows work without rebinding.
 */

import { useEffect } from "react";

import { BUTTON, SELECTORS } from "../../constants/classNames";
import { readData } from "../../dom/jquery";
import { show } from "../../compat/globalApi";
import { isStoredImagePath } from "../../lib/filename";
import { useWidget } from "./context";

/**
 * The data field a click belongs to.
 *
 * 4.x walked up to the enclosing admin row and took the first
 * `.cropduster-data-field` in it. That resolution is kept, since it is what
 * survives cloning, but a result outside this widget's own form is discarded:
 * two cropduster fields grouped into a single `fieldsets` row share one
 * `.form-row`, and 4.x sent both buttons to the first field.
 */
function resolveDataField(
  anchor: Element,
  root: HTMLElement,
): HTMLInputElement | null {
  const row = anchor.closest(SELECTORS.row);
  const fromRow = row?.querySelector<HTMLInputElement>(SELECTORS.dataField);
  if (fromRow && root.contains(fromRow)) {
    return fromRow;
  }
  return root.querySelector<HTMLInputElement>(SELECTORS.dataField);
}

export function UploadButton() {
  const { slots, root, config, state } = useWidget();
  const anchor = slots.button;

  useEffect(() => {
    if (!anchor) {
      return;
    }
    const onClick = (event: MouseEvent) => {
      const target = (event.target as Element | null)?.closest<HTMLElement>(
        SELECTORS.customField,
      );
      if (!target) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const dataField = resolveDataField(target, root);
      const prefix = dataField?.getAttribute("name");
      if (!prefix) {
        return;
      }
      let url = String(readData(target, "cropdusterUrl") ?? "");
      const uploadTo = readData(dataField, "uploadTo");
      if (uploadTo) {
        const separator = url.indexOf("?") >= 0 ? "&" : "?";
        url += `${separator}upload_to=${encodeURI(String(uploadTo))}`;
      }
      show(prefix, url);
    };
    anchor.addEventListener("click", onClick);
    return () => anchor.removeEventListener("click", onClick);
  }, [anchor, root]);

  // With an image in place the dialog opens on the crop stage, so the
  // button's label offers editing; replacing the image is done inside the
  // dialog.
  const label = isStoredImagePath(state.origImage)
    ? config.labels.edit
    : config.labels.upload;

  return (
    <>
      <div className={BUTTON}>{label}</div>
      <div style={{ clear: "both", height: "3px" }} />
    </>
  );
}
