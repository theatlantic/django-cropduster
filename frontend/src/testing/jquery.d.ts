/**
 * Types for the real jQuery the compatibility tests run against.
 *
 * Only the methods those tests touch are declared, and they are the ones the
 * downstream scripts use: `.val()` and `.attr()` update the formset, `.data()`
 * stores sizes, and `.on()` / `.trigger()` publish `cropduster:update`. The full
 * `@types/jquery` package is not a dependency here: cropduster ships no jQuery,
 * and the production code models what it needs in `dom/jquery.ts`.
 */
declare module "jquery" {
  interface JQueryTestObject {
    data(key: string): unknown;
    data(key: string, value: unknown): unknown;
    val(): unknown;
    val(value: unknown): JQueryTestObject;
    attr(name: string): string | undefined;
    attr(name: string, value: unknown): JQueryTestObject;
    on(
      type: string,
      handler: (event: unknown, ...args: never[]) => void,
    ): JQueryTestObject;
    off(
      type: string,
      handler?: (event: unknown, ...args: never[]) => void,
    ): JQueryTestObject;
    trigger(type: string, extraParameters?: unknown[]): unknown;
  }

  interface JQueryTestStatic {
    (target: unknown): JQueryTestObject;
    fn: { jquery: string };
    /** Return the instance so tests can create a second copy. */
    noConflict(removeAll?: boolean): JQueryTestStatic;
  }

  const jQuery: JQueryTestStatic;
  export default jQuery;
}
