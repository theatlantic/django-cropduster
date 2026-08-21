/**
 * Golden renderer URLs for the widget-card tests. `{Y}/{m}` and `{DIR}`
 * replace date- and run-specific path segments.
 */

export const HEADSHOT_DIR = "author/headshots/{Y}/{m}/{DIR}";
export const LEAD_IMAGE_DIR = "article/lead_image/{Y}/{m}/{DIR}";
export const STANDALONE_DIR = "img/posts/{Y}/{m}/{DIR}";

/**
 * Query appended by `FileRenderer`. Fixtures include renderer and storage URLs
 * because the 4.x completion payload returns storage URLs.
 */
export const CACHE_BUSTER = "?mod=1755000000";

export const THUMBOR_SOURCE_WIDTH = 1684;
export const THUMBOR_SOURCE_HEIGHT = 2000;
export const THUMBOR_MAIN_CROP = {
  x: 0,
  y: 311,
  width: 1684,
  height: 1378,
};
export const THUMBOR_PREVIEW_1X = `https://thumbor.example.com/unsafe/fit-in/800x500/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_PREVIEW_2X = `https://thumbor.example.com/unsafe/fit-in/1600x1000/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_PREVIEW_SRCSET = `${THUMBOR_PREVIEW_2X} 2x`;

export const THUMBOR_MAIN_1X = `https://thumbor.example.com/unsafe/0x311:1684x1689/220x180/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_MAIN_2X = `https://thumbor.example.com/unsafe/0x311:1684x1689/440x360/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_MAIN_SRCSET = `${THUMBOR_MAIN_1X}, ${THUMBOR_MAIN_2X} 2x`;
export const THUMBOR_AUTO_1X = `https://thumbor.example.com/unsafe/0x311:1684x1689/110x90/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_AUTO_2X = `https://thumbor.example.com/unsafe/0x311:1684x1689/220x180/media/${HEADSHOT_DIR}/original.jpg`;
export const THUMBOR_AUTO_SRCSET = `${THUMBOR_AUTO_1X}, ${THUMBOR_AUTO_2X} 2x`;
