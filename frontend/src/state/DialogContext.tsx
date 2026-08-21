/**
 * Runs API requests around the pure dialog reducer and reports completion
 * through the current shell.
 *
 * The reducer stores v1 response data. `stateToLegacyComplete()` converts it
 * immediately before completion for existing callers.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import type { ReactNode } from "react";

import {
  crop as cropApi,
  DialogError,
  getState,
  upload as uploadApi,
} from "../api/v1";
import type { CropBox } from "../crop/geometry";
import { useShell } from "../components/dialog/shellContext";
import {
  stateToCanonicalCropBody,
  stateToLegacyComplete,
} from "../formset/legacyPayload";
import {
  allCropsPopulated,
  dialogReducer,
  hydrateModel,
} from "./dialogReducer";
import type { DialogFailure, DialogModel } from "./dialogReducer";
import type { DialogConfig } from "./dialogConfig";
import type { DialogRendererData } from "./types";

export interface DialogController {
  selectFile(file: File | null): void;
  upload(): void;
  /** Enter the upload stage to replace the primary image. */
  beginReplace(): void;
  /** Leave the replace stage with the existing crops untouched. */
  cancelReplace(): void;
  save(): void;
  navigate(delta: number): void;
  navigateTo(index: number): void;
  imageLoaded(width: number, height: number): void;
  /** `box` is in the canvas's display pixels. */
  boxChanged(name: string, box: CropBox): void;
  setStandaloneSize(axis: "w" | "h", value: number | null): void;
  canCommit(): boolean;
}

export interface DialogContextValue {
  config: DialogConfig;
  state: DialogModel;
  controller: DialogController;
}

const DialogContext = createContext<DialogContextValue | null>(null);

export function useDialog(): DialogContextValue {
  const value = useContext(DialogContext);
  if (!value) {
    throw new Error("cropduster: dialog component rendered outside a dialog");
  }
  return value;
}

/** Convert a request failure to reducer state. */
function failureOf(error: unknown): DialogFailure {
  if (error instanceof DialogError) {
    return { message: error.message, code: error.code, field: error.field };
  }
  return { message: String(error), code: null, field: null };
}

/** Build an upload body; named targets have their sizes resolved by the server. */
function uploadBody(config: DialogConfig, state: DialogModel, file: File) {
  const body = new FormData();
  body.append("image", file);
  body.append("sizes", JSON.stringify(state.sizes));
  body.append("upload_to", config.uploadTo ?? "");
  // Widget modals omit preview bounds and use the server defaults.
  const [previewW, previewH] = config.previewSize;
  if (previewW) {
    body.append("preview_width", String(previewW));
  }
  if (previewH) {
    body.append("preview_height", String(previewH));
  }
  if (state.standalone) {
    body.append("standalone", "1");
  }
  return body;
}

export interface DialogProviderProps {
  config: DialogConfig;
  children: ReactNode;
}

export function DialogProvider({ config, children }: DialogProviderProps) {
  const [state, dispatch] = useReducer(dialogReducer, config, hydrateModel);
  const shell = useShell();

  // Async callbacks and imperative shell methods need the latest state.
  const stateRef = useRef(state);
  stateRef.current = state;
  const fileRef = useRef<File | null>(null);
  const inFlight = useRef(false);

  // The object URL standing in for the preview of the last uploaded file.
  // Created only after the server accepts the upload, replaced by the next
  // upload's, revoked when the dialog unmounts. Environments without the
  // File API (jsdom) stage nothing.
  const localPreviewUrl = useRef<string | null>(null);
  const stageLocalPreview = useCallback((file: File): string | null => {
    if (typeof URL.createObjectURL !== "function") {
      return null;
    }
    if (localPreviewUrl.current) {
      URL.revokeObjectURL(localPreviewUrl.current);
    }
    localPreviewUrl.current = URL.createObjectURL(file);
    return localPreviewUrl.current;
  }, []);
  useEffect(() => {
    return () => {
      if (localPreviewUrl.current) {
        URL.revokeObjectURL(localPreviewUrl.current);
        localPreviewUrl.current = null;
      }
    };
  }, []);

  // Existing-image modals request original dimensions and saved crop boxes.
  // Empty widgets and page dialogs already have all required state.
  const { hydrate } = config;
  useEffect(() => {
    if (!hydrate) {
      return;
    }
    let cancelled = false;
    getState(config, hydrate)
      .then((payload) => {
        if (!cancelled) {
          dispatch({ type: "hydrated", payload });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          dispatch({ type: "hydrateFailed", error: failureOf(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [config, hydrate]);

  const selectFile = useCallback((file: File | null) => {
    fileRef.current = file;
    dispatch({ type: "fileSelected", selected: Boolean(file) });
  }, []);

  const upload = useCallback(() => {
    const file = fileRef.current;
    if (!file || inFlight.current) {
      return;
    }
    inFlight.current = true;
    dispatch({ type: "uploadStarted" });
    uploadApi(config, uploadBody(config, stateRef.current, file))
      .then((payload) => {
        fileRef.current = null;
        dispatch({
          type: "uploadSucceeded",
          payload,
          localPreviewUrl: stageLocalPreview(file),
        });
      })
      .catch((error: unknown) => {
        if (!stateRef.current.standalone) {
          fileRef.current = null;
        }
        dispatch({ type: "uploadFailed", error: failureOf(error) });
      })
      .finally(() => {
        inFlight.current = false;
      });
  }, [config, stageLocalPreview]);

  const beginReplace = useCallback(() => {
    if (inFlight.current || stateRef.current.hydrating) {
      return;
    }
    fileRef.current = null;
    dispatch({ type: "beginReplace" });
  }, []);

  const cancelReplace = useCallback(() => {
    if (inFlight.current) {
      return;
    }
    fileRef.current = null;
    dispatch({ type: "cancelReplace" });
  }, []);

  const canCommit = useCallback(
    () =>
      stateRef.current.phase === "crop" &&
      allCropsPopulated(stateRef.current) &&
      !stateRef.current.hydrating &&
      !inFlight.current,
    [],
  );

  const save = useCallback(() => {
    if (!canCommit()) {
      return;
    }
    inFlight.current = true;
    dispatch({ type: "cropSubmitStarted" });
    cropApi(config, stateToCanonicalCropBody(stateRef.current))
      .then((payload) => {
        dispatch({ type: "cropSubmitSucceeded", payload });
      })
      .catch((error: unknown) => {
        dispatch({ type: "cropSubmitFailed", error: failureOf(error) });
      })
      .finally(() => {
        inFlight.current = false;
      });
  }, [canCommit, config]);

  const controller = useMemo<DialogController>(
    () => ({
      selectFile,
      upload,
      beginReplace,
      cancelReplace,
      save,
      canCommit,
      navigate: (delta) => dispatch({ type: "navigate", delta }),
      navigateTo: (index) => dispatch({ type: "navigateTo", index }),
      imageLoaded: (width, height) =>
        dispatch({ type: "imageLoaded", width, height }),
      boxChanged: (name, box) => dispatch({ type: "boxChanged", name, box }),
      setStandaloneSize: (axis, value) =>
        dispatch({ type: "standaloneSizeChanged", axis, value }),
    }),
    [beginReplace, canCommit, cancelReplace, save, selectFile, upload],
  );

  // Convert once, after Save completes, for existing completion callbacks.
  const delivered = useRef(false);
  const { onCommit } = shell;
  useEffect(() => {
    if (!state.complete || delivered.current) {
      return;
    }
    delivered.current = true;
    const rendererData: DialogRendererData = {
      preview: {
        url: state.preview.url,
        srcset: state.preview.srcset ?? null,
      },
      thumbs: {},
    };
    for (const thumb of Object.values(state.thumbs)) {
      if (thumb.id !== null && thumb.url) {
        rendererData.thumbs[thumb.name] = {
          url: thumb.url,
          srcset: thumb.srcset,
        };
      }
    }
    onCommit(stateToLegacyComplete(state), rendererData);
  }, [onCommit, state]);

  const { publish } = shell;
  useEffect(() => {
    if (!publish) {
      return;
    }
    publish({
      canCommit,
      commit: save,
      get state() {
        return stateRef.current;
      },
    });
    return () => publish(null);
  }, [canCommit, publish, save]);

  const value = useMemo<DialogContextValue>(
    () => ({ config, state, controller }),
    [config, controller, state],
  );

  return (
    <DialogContext.Provider value={value}>{children}</DialogContext.Provider>
  );
}
