/**
 * Render and update the crop box over the preview.
 *
 * react-image-crop uses display pixels, while Cropduster stores source pixels.
 * Scaling happens here; rounding remains in the reducer. Ratio ranges and
 * minimum sizes are applied around the library's single-aspect API.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { CSSProperties } from "react";
import type { Crop, PixelCrop } from "react-image-crop";

import { AspectEdgeReactCrop } from "./AspectEdgeCrop";

import { calcMinSize, fixedAspectRatio } from "../../crop/geometry";
import { toDisplayPx } from "../../crop/scaling";
import {
  cropKey,
  currentCrop,
  currentSize,
  primarySource,
  sourceScale,
} from "../../state/dialogReducer";
import { useDialog } from "../../state/DialogContext";

/** 4.x's test for "the preview is really there", which a 1x1 blank.gif fails. */
const LOADED_MIN_WIDTH = 1;

/** A 1x1 transparent gif, for a dialog opened with no image to show. */
const BLANK_GIF =
  "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";

interface FitBounds {
  maxWidth: number;
  maxHeight: number;
}

function cssPixels(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * The preview's rendered size, in the fractional units react-image-crop
 * works in. This uses `getBoundingClientRect` which, unlike `offsetWidth`,
 * does not round to whole pixels. Rounding at this step can result in
 * off-by-one errors downstream.
 */
function renderedSize(img: HTMLImageElement): [number, number] {
  const rect = img.getBoundingClientRect();
  return [
    rect.width || img.offsetWidth || img.naturalWidth,
    rect.height || img.offsetHeight || img.naturalHeight,
  ];
}

export function CropCanvas() {
  const { state, controller } = useDialog();
  const imgRef = useRef<HTMLImageElement>(null);
  const [fitBounds, setFitBounds] = useState<FitBounds | null>(null);
  // The display URL whose file has finished loading, so a render in between
  // can treat the preview element as having no pixels yet.
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);

  const source = primarySource(state);
  const size = currentSize(state);
  const scale = sourceScale(state);
  const entry = currentCrop(state);
  const name = cropKey(size);

  // Until its file arrives, the preview element has no intrinsic size: it
  // collapses and the selection ReactCrop draws over it lands in empty
  // space. Every payload reports the preview's dimensions, so the fitted box
  // is reserved up front; the correction effect below then aligns the stored
  // display dimensions, and with them the drawn selection, to the reservation.
  const loaded = Boolean(source.displayUrl) && loadedUrl === source.displayUrl;
  let placeholder: { width: number; height: number } | null = null;
  if (
    !loaded &&
    source.name &&
    source.displayWidth > LOADED_MIN_WIDTH &&
    source.displayHeight > LOADED_MIN_WIDTH
  ) {
    const fit = fitBounds
      ? Math.min(
          1,
          fitBounds.maxWidth / source.displayWidth,
          fitBounds.maxHeight / source.displayHeight,
        )
      : 1;
    placeholder = {
      width: Math.round(source.displayWidth * fit),
      height: Math.round(source.displayHeight * fit),
    };
  }

  // Percentage max-heights resolve through ReactCrop's auto-height wrappers
  // and do not form a real vertical constraint. Measure the image well's
  // content box and give the preview explicit pixel maxima instead.
  useLayoutEffect(() => {
    const img = imgRef.current;
    const container = img?.closest<HTMLElement>("#image-container") ?? null;
    if (!img || !container || state.standalone) {
      return;
    }

    const measure = () => {
      const style = getComputedStyle(container);
      const maxWidth =
        container.clientWidth -
        cssPixels(style.paddingLeft) -
        cssPixels(style.paddingRight);
      const maxHeight =
        container.clientHeight -
        cssPixels(style.paddingTop) -
        cssPixels(style.paddingBottom);
      if (maxWidth <= 0 || maxHeight <= 0) {
        return;
      }
      setFitBounds((previous) => {
        if (
          previous?.maxWidth === maxWidth &&
          previous.maxHeight === maxHeight
        ) {
          return previous;
        }
        return { maxWidth, maxHeight };
      });
    };

    measure();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => measure());
    observer?.observe(container);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [source.displayUrl, state.standalone]);

  const { imageLoaded } = controller;
  useLayoutEffect(() => {
    const img = imgRef.current;
    if (!img) {
      return;
    }
    let cancelled = false;
    const measure = () => {
      if (cancelled || img.naturalWidth <= LOADED_MIN_WIDTH) {
        return;
      }
      setLoadedUrl(source.displayUrl);
      // The preview may be fitted down to the workspace. Its rendered size is
      // the authority for mapping the on-screen crop back to source pixels.
      imageLoaded(...renderedSize(img));
    };
    if (img.complete) {
      measure();
    }
    // `decode()` resolves once the image is ready to paint, which is what the
    // 50ms `naturalWidth` polling loop in 4.x was waiting for. The `load`
    // listener covers browsers and test environments without it, and a decode
    // that rejects (a broken URL) leaves the dialog on the upload step.
    img.decode?.().then(measure, () => undefined);
    img.addEventListener("load", measure);
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => measure());
    observer?.observe(img);
    return () => {
      cancelled = true;
      observer?.disconnect();
      img.removeEventListener("load", measure);
    };
  }, [imageLoaded, source.displayUrl]);

  // The rendered image is the only authority on the scale a crop box is
  // converted through, so a state that disagrees with it is corrected rather
  // than drawn: a box scaled by the wrong preview size overflows the image and
  // walks every drag it converts. Before the file loads, the reserved
  // placeholder box is the same authority.
  useEffect(() => {
    const img = imgRef.current;
    if (!img || (img.naturalWidth <= LOADED_MIN_WIDTH && !placeholder)) {
      return;
    }
    const [width, height] = renderedSize(img);
    if (width <= LOADED_MIN_WIDTH || height <= LOADED_MIN_WIDTH) {
      return;
    }
    if (width !== source.displayWidth || height !== source.displayHeight) {
      imageLoaded(width, height);
    }
  });

  const onChange = useCallback(
    (pixelCrop: PixelCrop) => {
      if (!name) {
        return;
      }
      controller.boxChanged(name, {
        x: pixelCrop.x,
        y: pixelCrop.y,
        w: pixelCrop.width,
        h: pixelCrop.height,
      });
    },
    [controller, name],
  );

  const box = entry?.box ? toDisplayPx(entry.box, scale) : null;
  const crop: Crop | undefined = box
    ? { unit: "px", x: box.x, y: box.y, width: box.w, height: box.h }
    : undefined;

  const aspect = size ? fixedAspectRatio(size) : 0;
  const minSize = size ? calcMinSize(size) : [0, 0];

  const localPreview =
    state.localPreview && state.localPreview.forDisplayUrl === source.displayUrl
      ? state.localPreview.url
      : null;
  const fitStyle: CSSProperties | undefined = fitBounds
    ? { maxWidth: fitBounds.maxWidth, maxHeight: fitBounds.maxHeight }
    : undefined;
  // The reserved box paints the uploaded file itself while the dialog still
  // has it, and a neutral fill otherwise; a pending image element paints
  // nothing of its own, so its background shows until the file covers it.
  const style: CSSProperties | undefined = placeholder
    ? {
        ...fitStyle,
        width: placeholder.width,
        height: placeholder.height,
        backgroundColor: "#f4f4f4",
        ...(localPreview
          ? {
              backgroundImage: `url(${JSON.stringify(localPreview)})`,
              backgroundSize: "100% 100%",
              backgroundRepeat: "no-repeat",
            }
          : {}),
      }
    : fitStyle;

  // Waiting on the saved boxes or on the preview file itself; the progress
  // line makes the announcement, so the veil is decorative.
  const loading = state.hydrating || (Boolean(source.name) && !loaded);

  return (
    <AspectEdgeReactCrop
      crop={crop}
      onChange={onChange}
      {...(aspect ? { aspect } : {})}
      minWidth={(minSize[0] ?? 0) / scale.x}
      minHeight={(minSize[1] ?? 0) / scale.y}
      keepSelection
      disabled={state.hydrating}
    >
      <img
        id="cropbox"
        ref={imgRef}
        src={source.displayUrl || BLANK_GIF}
        srcSet={source.displaySrcset ?? undefined}
        style={style}
        alt=""
      />
      {loading ? (
        <div
          className="cropbox-loading"
          part="canvas-loading"
          aria-hidden="true"
        >
          <span className="cropbox-spinner" part="canvas-spinner" />
        </div>
      ) : null}
    </AspectEdgeReactCrop>
  );
}
