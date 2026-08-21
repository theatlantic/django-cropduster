/** Renderer URLs the widget reads from its server-rendered markup. */

/** Renderer URLs passed beside the frozen legacy completion payload. */
export interface RendererImageData {
  url: string | null;
  srcset: string | null;
}

export interface DialogRendererData {
  preview: RendererImageData;
  thumbs: Record<string, RendererImageData>;
}
