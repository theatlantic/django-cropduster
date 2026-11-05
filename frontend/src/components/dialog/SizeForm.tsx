/**
 * Edit the standalone dialog's output size.
 *
 * Values commit on blur or Enter because validating intermediate keystrokes
 * would make a multi-digit value impossible to enter on some images.
 */

import { useCallback, useState } from "react";

import { HEIGHT, WIDTH } from "../../constants/dialogLabels";
import { syncSizeForm } from "../../crop/sizeForm";
import type { PlaceholderUpdate } from "../../crop/sizeForm";
import { currentCrop, primarySource } from "../../state/dialogReducer";
import { useDialog } from "../../state/DialogContext";

type Axis = "w" | "h";

function placeholderOf(update: PlaceholderUpdate): string | undefined {
  // "keep" only ever happens on the branch where the field itself has a value,
  // so there is no placeholder to see either way.
  return update.action === "set" ? update.value : undefined;
}

function numeric(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

export function SizeForm() {
  const { state, controller } = useDialog();
  const [draft, setDraft] = useState<Partial<Record<Axis, string>>>({});

  const source = primarySource(state);
  const box = currentCrop(state)?.box ?? null;
  const size = state.sizes[0];

  const sync = syncSizeForm({
    standalone: true,
    sizesRaw: JSON.stringify(state.sizes),
    origW: String(source.width),
    origH: String(source.height),
    cropW: numeric(box?.w),
    cropH: numeric(box?.h),
  });

  const commit = useCallback(
    (axis: Axis, raw: string) => {
      setDraft((current) => ({ ...current, [axis]: undefined }));
      if (raw !== "0" && !raw) {
        controller.setStandaloneSize(axis, null);
        return;
      }
      const value = parseInt(raw, 10);
      const limit = axis === "w" ? source.width : source.height;
      const max = axis === "w" ? size?.max_w : size?.max_h;
      const rejected =
        Number.isNaN(value) ||
        value < 1 ||
        Boolean(limit && value > limit) ||
        Boolean(max && value > max);
      if (rejected) {
        // 4.x put the value the field had at focus back; discarding the draft
        // is the same thing, since the field renders from the size.
        return;
      }
      controller.setStandaloneSize(axis, value);
    },
    [controller, size?.max_h, size?.max_w, source.height, source.width],
  );

  const field = (
    axis: Axis,
    label: string,
    id: string,
    value: string | null,
  ) => (
    <div
      className={`row form-row ${axis === "w" ? "width" : "height"}`}
      part="size-row"
    >
      <label htmlFor={id} part="size-label">
        {label}
      </label>
      <input
        type="text"
        id={id}
        part="size-input"
        value={draft[axis] ?? value ?? ""}
        placeholder={placeholderOf(
          axis === "w" ? sync.widthPlaceholder : sync.heightPlaceholder,
        )}
        onChange={(event) =>
          setDraft((current) => ({ ...current, [axis]: event.target.value }))
        }
        onBlur={(event) => commit(axis, event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit(axis, event.currentTarget.value);
          }
        }}
      />
    </div>
  );

  return (
    <form
      id="size"
      part="size-form"
      hidden={!sync.showRows}
      onSubmit={(e) => e.preventDefault()}
    >
      {field("w", WIDTH, "id_size-width", sync.width)}
      {field("h", HEIGHT, "id_size-height", sync.height)}
    </form>
  );
}
