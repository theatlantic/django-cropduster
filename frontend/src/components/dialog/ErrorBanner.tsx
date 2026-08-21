/**
 * Render API failures and warnings as text. Keep `#error-container` mounted so
 * Selenium can wait for it before or after an error.
 */

import { PER_SIZE_SOURCE_UNSUPPORTED } from "../../api/v1";
import { useDialog } from "../../state/DialogContext";
import type { DialogState } from "../../state/types";

/** Replace the reserved source 501 (`"not implemented"`) with a message the
 * editor can act on. */
function sourceUnsupported(field: string | null): string {
  const size = (field ?? "").replace(/^thumbs\./, "");
  return size
    ? `This version of cropduster can only crop ${size} from the image itself. ` +
        "Upload the other image to this field, or crop it separately."
    : "This version of cropduster can only crop from the image itself.";
}

/** Return the server message unless the client has a specific replacement. */
export function errorMessage(state: DialogState): string | null {
  if (state.errorCode === PER_SIZE_SOURCE_UNSUPPORTED) {
    return sourceUnsupported(state.errorField);
  }
  return state.error;
}

export function ErrorBanner() {
  const { state } = useDialog();
  const message = errorMessage(state);

  return (
    <div className="dialog-messages" part="messages">
      <div
        id="error-container"
        part="error-container"
        role="alert"
        aria-atomic="true"
        hidden={!message}
      >
        <p className="errornote" part="error-note">
          {message ?? ""}
        </p>
      </div>
      {state.warnings.length ? (
        <ul className="messagelist grp-messagelist" part="warnings">
          {state.warnings.map((warning, i) => (
            <li
              className="warning grp-warning"
              part="warning"
              key={`${warning.code}-${i}`}
            >
              {warning.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
