// The local app's additions to the review app (P35): the Read a page view, its place in the side bar,
// and the mode pill in the header. main.js loads this module only when the page carries
// <meta name="archivist-live">, which the local server (python -m archivist.live) adds to the page it
// serves. ui/index.html has no such tag, so the published site loads none of this: it offers no live
// read and has no upload box (D12, D13).

import { $ } from "../util.js";
import * as view from "./view.js";
import { pill } from "./core.js";

export const views = () => ({ live: view });

export function install() {
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = new URL("../../css/live.css", import.meta.url).href;
  document.head.appendChild(css);

  const mode = document.createElement("span");
  mode.id = "mode-pill";
  mode.className = "modepill";
  mode.setAttribute("role", "status");
  document.querySelector(".top-r").prepend(mode);
  pill();

  const link = document.createElement("a");
  link.href = "#live";
  link.dataset.v = "live";
  link.innerHTML = `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="2.2" fill="currentColor"/></svg>Read a page`;
  document.querySelector(".side .grp").before(link); // after Overview and the Review queue

  const section = document.createElement("section");
  section.className = "view";
  section.id = "v-live";
  section.hidden = true;
  section.setAttribute("aria-labelledby", "l-t");
  section.innerHTML = view.markup();
  $("v-types").before(section);
}
