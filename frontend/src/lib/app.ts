/** Running inside the Snazzlebop store app (its web view adds "SnazzlebopApp/<version>" to the user
 * agent). App stores sell digital extras through their own billing and allow ads only through their
 * own SDKs, so inside the app nothing is sold and no web ads show; Plus bought on the web still works. */
export const inApp = typeof navigator !== "undefined" && /\bSnazzlebopApp\//.test(navigator.userAgent);
