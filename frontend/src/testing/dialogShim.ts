/**
 * jsdom implements HTMLDialogElement's `open` reflection but none of its
 * methods (jsdom/jsdom#3294). The modal shell opens a native dialog, so this
 * setup file supplies the two members it calls. Modal behavior itself (the
 * top layer, the inert page, the confined tab order, cancel-on-Escape) has no
 * jsdom equivalent: the unit tests cover the shell's own handlers, and
 * `e2e/modal.spec.ts` covers the browser's side.
 */

if (
  typeof HTMLDialogElement !== "undefined" &&
  typeof HTMLDialogElement.prototype.showModal !== "function"
) {
  HTMLDialogElement.prototype.showModal = function showModal(
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(
    this: HTMLDialogElement,
    returnValue?: string,
  ) {
    if (!this.open) {
      return;
    }
    if (returnValue !== undefined) {
      this.returnValue = returnValue;
    }
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}

export {};
