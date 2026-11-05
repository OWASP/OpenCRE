/**
 * Scroll the app's real scroll container to the top.
 *
 * `body` is `overflow: hidden` and `#mount` is `overflow-y: auto`
 * (see `app.scss`), so `window.scrollTo(0, 0)` is a no-op and leaves
 * SPA navigations scrolled mid-page. That clips page headings and makes
 * Cypress `be.visible` flake on search / browse routes.
 */
export const scrollMountToTop = (): void => {
  const mount = document.getElementById('mount');
  if (mount) {
    mount.scrollTop = 0;
    return;
  }
  window.scrollTo(0, 0);
};
