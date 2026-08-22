import { expect, test } from "@playwright/test";

test.use({ storageState: { cookies: [], origins: [] } });

test("anonymous Cropduster requests redirect to the demo login page", async ({
  request,
}) => {
  const response = await request.get("/cropduster/", { maxRedirects: 0 });
  expect(response.status()).toBe(302);
  expect(response.headers().location).toBe("/login/?next=/cropduster/");

  const login = await request.get(response.headers().location);
  expect(login.status()).toBe(200);
  expect(await login.text()).toContain('name="username"');
});
