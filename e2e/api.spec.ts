import { expect, test, type Page, type Request } from "@playwright/test";

import {
  IMG_JPG,
  openModalDialog,
  previewImages,
  saveAndContinue,
  uploadAndCropAll,
  widget,
} from "./support/cropduster";

/**
 * Requests sent by the modal crop dialog.
 *
 * Both dialog presentations use the version 1 JSON API. The modal also calls
 * `state/` when reopening a saved image, so this spec records all three
 * endpoint requests from the admin page. The legacy formset endpoints remain
 * mounted for downstream rich-text clients, but the widget does not call
 * them.
 *
 * This file is excluded from the `fullpage` Playwright project.
 */

const ADD_URL = "/admin/example/article/add/";

/** Record Cropduster POST requests by path, in request order. */
function recordPosts(page: Page) {
  const posts: {
    path: string;
    csrf: string | undefined;
    target: unknown;
  }[] = [];
  const record = (request: Request) => {
    if (request.method() !== "POST") {
      return;
    }
    const { pathname } = new URL(request.url());
    if (!pathname.startsWith("/cropduster/")) {
      return;
    }
    posts.push({
      path: pathname,
      csrf: request.headers()["x-csrftoken"],
      target: targetOf(request),
    });
  };
  page.on("request", record);
  return () => posts;
}

/**
 * Return the request's `target`, or `undefined` if Playwright cannot read it.
 *
 * Chromium does not expose a multipart body containing a file to Playwright,
 * so the `upload/` body cannot be inspected here. Crop requests use JSON, and
 * the CSRF-protected state request uses URL-encoded form data. The API unit
 * tests check the upload target.
 */
function targetOf(request: Request): unknown {
  const body = request.postDataBuffer()?.toString("utf8");
  if (body === undefined) {
    return undefined;
  }
  const contentType = request.headers()["content-type"] ?? "";
  if (contentType.includes("application/json")) {
    const json = JSON.parse(body) as Record<string, unknown>;
    return json.target ?? null;
  }
  if (contentType.includes("application/x-www-form-urlencoded")) {
    const target = new URLSearchParams(body).get("target");
    return target ? JSON.parse(target) : null;
  }
  return undefined;
}

/** Return the target published in the widget's `data-config`. */
async function renderedTarget(page: Page, prefix: string): Promise<unknown> {
  const raw = await widget(page, prefix)
    .locator("cropduster-widget")
    .getAttribute("data-config");
  return (JSON.parse(raw ?? "{}") as Record<string, unknown>).target ?? null;
}

test("crops through the versioned JSON API, with a CSRF token", async ({
  page,
}) => {
  await page.goto(ADD_URL);
  await page.locator("#id_title").fill(`API article ${Date.now()}`);

  const posts = recordPosts(page);
  const failures: string[] = [];
  page.on("response", (response) => {
    const { pathname } = new URL(response.url());
    if (pathname.startsWith("/cropduster/") && !response.ok()) {
      failures.push(`${response.status()} ${pathname}`);
    }
  });

  const group = widget(page, "lead_image");
  await uploadAndCropAll(await openModalDialog(page, group), IMG_JPG, 2);
  await expect(previewImages(group)).toHaveCount(1);

  const paths = posts().map((post) => post.path);
  expect(paths).toContain("/cropduster/api/v1/upload/");
  expect(paths).toContain("/cropduster/api/v1/crop/");

  // The legacy endpoints remain available and CSRF-exempt, but the widget does
  // not call them.
  expect(paths).not.toContain("/cropduster/upload/");
  expect(paths).not.toContain("/cropduster/crop/");

  // The version 1 endpoints require a CSRF token; only the legacy endpoints
  // retain their exemption.
  for (const post of posts()) {
    expect(
      post.csrf,
      `${post.path} was posted without an X-CSRFToken header`,
    ).toBeTruthy();
  }

  // Without this assertion, a CSRF 403 would appear only as a dialog that
  // failed to advance.
  expect(failures).toEqual([]);

  // Each readable request identifies the field being edited. The server then
  // gets the sizes and upload directory from the model instead of trusting the
  // client. Since the article has not been saved, `object_id` is null and the
  // request is checked against the model's `add` permission.
  const WIRE = {
    content_type: "example.article",
    object_id: null,
    field_name: "lead_image",
  };
  const readable = posts().filter((post) => post.target !== undefined);
  expect(readable.map((post) => post.path)).toContain(
    "/cropduster/api/v1/crop/",
  );
  for (const post of readable) {
    expect([post.path, post.target]).toEqual([post.path, WIRE]);
  }
  expect(await renderedTarget(page, "lead_image")).toEqual({
    model: "example.article",
    objectId: null,
    fieldName: "lead_image",
  });
});

test("names the saved object once there is one", async ({ page }) => {
  await page.goto(ADD_URL);
  await page.locator("#id_title").fill(`API target ${Date.now()}`);

  const group = widget(page, "lead_image");
  await uploadAndCropAll(await openModalDialog(page, group), IMG_JPG, 2);
  await saveAndContinue(page);

  const id = Number(/\/article\/(\d+)\//.exec(page.url())?.[1]);
  expect(id).toBeGreaterThan(0);

  const posts = recordPosts(page);
  const failures: string[] = [];
  page.on("response", (response) => {
    if (
      new URL(response.url()).pathname.startsWith("/cropduster/") &&
      !response.ok()
    ) {
      failures.push(`${response.status()} ${response.url()}`);
    }
  });

  const dialog = await openModalDialog(page, widget(page, "lead_image"));
  await expect(dialog.root.locator("#crop-button:not(.disabled)")).toHaveValue(
    "Save",
  );
  await dialog.root.locator("#crop-button:not(.disabled)").click();
  await dialog.waitForClose();

  expect(posts().length).toBeGreaterThan(0);
  expect(posts().map((post) => post.path)).toContain(
    "/cropduster/api/v1/state/",
  );
  for (const post of posts()) {
    expect([post.path, post.target]).toEqual([
      post.path,
      {
        content_type: "example.article",
        object_id: id,
        field_name: "lead_image",
      },
    ]);
  }
  expect(await renderedTarget(page, "lead_image")).toEqual({
    model: "example.article",
    objectId: id,
    fieldName: "lead_image",
  });
  expect(failures).toEqual([]);
});

test("does not reach the API before there is something to send", async ({
  page,
}) => {
  await page.goto(ADD_URL);

  const posts = recordPosts(page);
  const dialog = await openModalDialog(page, widget(page, "lead_image"));
  await expect(dialog.root.locator("#id_image")).toHaveCount(1);

  // Opening the modal reads `data-config` and the formset already on the page.
  // It should not send another request for each widget click.
  expect(posts()).toEqual([]);
});
