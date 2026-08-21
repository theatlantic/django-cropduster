/**
 * ReactCrop with Jcrop-style edge resizing under a fixed aspect ratio.
 *
 * Upstream hides the four edge handles whenever `aspect` is set, and its
 * resize model cannot control them well anyway: every resize is anchored to a
 * quadrant corner (`getPointRegion`), and with min dimensions set the "n"
 * and "e" ordinates resolve to a quadrant that disagrees with the anchor
 * `onCropPointerDown` chose, so the box jumps. This subclass takes over the
 * edge ordinates whenever an aspect is set, for pointer drags and keyboard
 * nudges alike: the opposite edge stays fixed and the perpendicular axis
 * stays centered on the selection's midline (`edgeResizeCrop`). Corner
 * ordinates and free-aspect behavior remain upstream's. The stylesheet rule
 * in dialog.css unhides the edge handles upstream's CSS suppresses.
 *
 * `evData`, `getBox()`, `resizeCrop()`, and the two handlers wrapped in the
 * constructor are all in react-image-crop's published declarations, but
 * they are internals in spirit: re-audit this file when upgrading it.
 */

import type { KeyboardEvent, PointerEvent } from "react";
import ReactCrop, {
  areCropsEqual,
  convertToPercentCrop,
  convertToPixelCrop,
} from "react-image-crop";
import type { Ords, PixelCrop, ReactCropProps } from "react-image-crop";

import { edgeResizeCrop, isEdgeOrd } from "../../crop/edgeResize";
import type { EdgeOrd } from "../../crop/edgeResize";

/** The arrow that grows each edge outward; its opposite shrinks. */
const GROW_KEYS: Record<EdgeOrd, string> = {
  n: "ArrowUp",
  e: "ArrowRight",
  s: "ArrowDown",
  w: "ArrowLeft",
};

const SHRINK_KEYS: Record<EdgeOrd, string> = {
  n: "ArrowDown",
  e: "ArrowLeft",
  s: "ArrowUp",
  w: "ArrowRight",
};

export class AspectEdgeReactCrop extends ReactCrop {
  /** The perpendicular midline captured when an edge drag starts. */
  private edgeDragCenter: { x: number; y: number } | null = null;

  constructor(props: ReactCropProps) {
    super(props);

    // Both handlers are class fields, not prototype methods, so they are
    // wrapped here rather than overridden.
    const basePointerDown = this.onCropPointerDown;
    this.onCropPointerDown = (e: PointerEvent<HTMLDivElement>) => {
      this.edgeDragCenter = this.centerFor(e.target);
      basePointerDown(e);
    };

    const baseKeyDown = this.onHandlerKeyDown;
    this.onHandlerKeyDown = (e: KeyboardEvent<HTMLDivElement>, ord: Ords) => {
      if (!this.nudgeEdge(e, ord)) {
        baseKeyDown(e, ord);
      }
    };
  }

  private centerFor(target: EventTarget): { x: number; y: number } | null {
    const ord = target instanceof HTMLElement ? target.dataset.ord : undefined;
    const { crop } = this.props;
    if (!isEdgeOrd(ord) || !crop) {
      return null;
    }
    const box = this.getBox();
    const pixelCrop = convertToPixelCrop(crop, box.width, box.height);
    return {
      x: pixelCrop.x + pixelCrop.width / 2,
      y: pixelCrop.y + pixelCrop.height / 2,
    };
  }

  resizeCrop(): PixelCrop {
    const { evData } = this;
    const aspect = this.props.aspect ?? 0;
    const ord = evData.ord;
    const center = this.edgeDragCenter;
    if (!aspect || !isEdgeOrd(ord) || !center) {
      return super.resizeCrop();
    }

    const box = this.getBox();
    const horizontal = ord === "e" || ord === "w";
    // `onCropPointerDown` anchors every edge ordinate on its opposite edge
    // and shifts the start coordinates by the pointer's distance from the
    // dragged edge, so this difference is the demanded width or height.
    const primary =
      ord === "e"
        ? evData.clientX - evData.startClientX
        : ord === "w"
          ? evData.startClientX - evData.clientX
          : ord === "s"
            ? evData.clientY - evData.startClientY
            : evData.startClientY - evData.clientY;

    return edgeResizeCrop({
      ord,
      primary,
      aspect,
      anchor: horizontal ? evData.startCropX : evData.startCropY,
      center: horizontal ? center.y : center.x,
      bounds: { w: box.width, h: box.height },
      minWidth: this.props.minWidth,
      minHeight: this.props.minHeight,
      maxWidth: this.props.maxWidth,
      maxHeight: this.props.maxHeight,
    });
  }

  /** Handle a primary-axis arrow on an edge handle; false hands the key on. */
  private nudgeEdge(e: KeyboardEvent<HTMLDivElement>, ord: Ords): boolean {
    const { aspect = 0, crop, disabled, onChange, onComplete } = this.props;
    if (!aspect || !isEdgeOrd(ord) || disabled || !crop) {
      return false;
    }
    const grow = e.key === GROW_KEYS[ord];
    if (!grow && e.key !== SHRINK_KEYS[ord]) {
      return false;
    }
    e.stopPropagation();
    e.preventDefault();

    const ctrlCmdPressed = navigator.platform.match("Mac")
      ? e.metaKey
      : e.ctrlKey;
    const offset = ctrlCmdPressed
      ? ReactCrop.nudgeStepLarge
      : e.shiftKey
        ? ReactCrop.nudgeStepMedium
        : ReactCrop.nudgeStep;

    const box = this.getBox();
    const pixelCrop = convertToPixelCrop(crop, box.width, box.height);
    const horizontal = ord === "e" || ord === "w";
    const next = edgeResizeCrop({
      ord,
      primary:
        (horizontal ? pixelCrop.width : pixelCrop.height) +
        (grow ? offset : -offset),
      aspect,
      anchor:
        ord === "e"
          ? pixelCrop.x
          : ord === "w"
            ? pixelCrop.x + pixelCrop.width
            : ord === "s"
              ? pixelCrop.y
              : pixelCrop.y + pixelCrop.height,
      center: horizontal
        ? pixelCrop.y + pixelCrop.height / 2
        : pixelCrop.x + pixelCrop.width / 2,
      bounds: { w: box.width, h: box.height },
      minWidth: this.props.minWidth,
      minHeight: this.props.minHeight,
      maxWidth: this.props.maxWidth,
      maxHeight: this.props.maxHeight,
    });

    if (!areCropsEqual(pixelCrop, next)) {
      const percentCrop = convertToPercentCrop(next, box.width, box.height);
      onChange(next, percentCrop);
      onComplete?.(next, percentCrop);
    }
    return true;
  }
}
