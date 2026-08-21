import { afterEach, describe, expect, it, vi } from "vitest";

import { observeValues } from "./valueObserver";
import { flush } from "../testing/fixtures";

function form(html: string): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = html;
  document.body.appendChild(root);
  return root;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("observeValues", () => {
  it("sees a property write, which fires no event", async () => {
    const root = form('<input name="a" value="">');
    const notify = vi.fn();
    const observer = observeValues(root, notify);
    const input = root.querySelector("input")!;

    input.value = "written";

    expect(input.value).toBe("written");
    await flush();
    expect(notify).toHaveBeenCalledTimes(1);
    observer.destroy();
  });

  it("sees a checked write, which is how the delete cascade works", async () => {
    const root = form('<input type="checkbox" name="d">');
    const notify = vi.fn();
    const observer = observeValues(root, notify);

    root.querySelector("input")!.checked = true;

    await flush();
    expect(notify).toHaveBeenCalledTimes(1);
    observer.destroy();
  });

  it("coalesces a burst into one notification", async () => {
    const root = form('<input name="a"><input name="b">');
    const notify = vi.fn();
    const observer = observeValues(root, notify);
    const [a, b] = [...root.querySelectorAll("input")];

    a!.value = "1";
    b!.value = "2";
    a!.dispatchEvent(new Event("change", { bubbles: true }));

    await flush();
    expect(notify).toHaveBeenCalledTimes(1);
    observer.destroy();
  });

  it("does not report our own writes", async () => {
    const root = form('<input name="a">');
    const notify = vi.fn();
    const observer = observeValues(root, notify);
    const input = root.querySelector("input")!;

    observer.suppress(() => {
      input.value = "ours";
    });

    await flush();
    expect(notify).not.toHaveBeenCalled();
    observer.destroy();
  });

  it("reinstalls on recreated inputs, as autosave's revert produces", async () => {
    const root = form('<input name="a" value="one">');
    const notify = vi.fn();
    const observer = observeValues(root, notify);

    // django-autosave deletes every input and rebuilds it from name/value.
    root.innerHTML = '<input name="a" value="two">';
    await flush();
    notify.mockClear();

    root.querySelector("input")!.value = "three";
    await flush();
    expect(notify).toHaveBeenCalledTimes(1);
    observer.destroy();
  });

  it("sees delegated change events", async () => {
    const root = form('<select name="t"><option>a</option></select>');
    const notify = vi.fn();
    const observer = observeValues(root, notify);

    root
      .querySelector("select")!
      .dispatchEvent(new Event("change", { bubbles: true }));

    await flush();
    expect(notify).toHaveBeenCalledTimes(1);
    observer.destroy();
  });

  it("notices option churn from setThumbnails", async () => {
    const root = form('<select multiple name="t"></select>');
    const notify = vi.fn();
    const observer = observeValues(root, notify);

    const option = document.createElement("option");
    option.setAttribute("selected", "selected");
    root.querySelector("select")!.appendChild(option);

    await flush();
    expect(notify).toHaveBeenCalledTimes(1);
    observer.destroy();
  });

  it("restores the prototype accessor on destroy", async () => {
    const root = form('<input name="a">');
    const notify = vi.fn();
    const observer = observeValues(root, notify);
    const input = root.querySelector("input")!;
    expect(Object.getOwnPropertyDescriptor(input, "value")).toBeDefined();

    observer.destroy();

    expect(Object.getOwnPropertyDescriptor(input, "value")).toBeUndefined();
    input.value = "after";
    expect(input.value).toBe("after");
    await flush();
    expect(notify).not.toHaveBeenCalled();
  });

  it("flushes a pending notification on demand", () => {
    const root = form('<input name="a">');
    const notify = vi.fn();
    const observer = observeValues(root, notify);

    root.querySelector("input")!.value = "x";
    observer.flush();

    expect(notify).toHaveBeenCalledTimes(1);
    observer.destroy();
  });
});
