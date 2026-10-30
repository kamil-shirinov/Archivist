// Moving between views. Only the main content moves: the top bar, the run bar and the sidebar are
// never animated. The new content comes in (its header, then its panels a step apart, at most six
// steps) and the old content fades out under it. Where the browser has the View Transitions API the
// swap is one, with only the visible view named, so everything else is held perfectly still; where it
// has not, the new content comes in the same way and the old is simply replaced. With reduced motion
// the new content only fades, in 120 ms, and nothing moves.
//
// The hover and pin lines are drawn from the positions of things, so they wait: `data-entering` is
// set on the page until the entrance has finished and the view's `entered` hook then draws them again.
//
// A new view starts at the top; going back to a page you were on puts you where you were. Each history
// entry carries an id in its state and the scroll position it was left at is kept under that id.

import { setSync } from "./util.js";

const root = document.documentElement;
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const scrolls = new Map();
let currentId = null;
let entering = 0;

if ("scrollRestoration" in history) history.scrollRestoration = "manual"; // we put it back ourselves

const newId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));

// Put the page back at y, as soon as it is tall enough to be there (a view that draws a frame late
// is given a few frames).
function scrollBack(y, tries = 12) {
  if (y === 0) return scrollTo(0, 0);
  if (root.scrollHeight - innerHeight >= y - 1 || tries === 0) return scrollTo(0, y);
  requestAnimationFrame(() => scrollBack(y, tries - 1));
}

// The entrance: the view's children rise and fade in, header first (the CSS sets each one's step). It
// is over when every one of those animations has finished.
function enterView(section, entered) {
  const token = ++entering;
  section.classList.remove("enter");
  void section.offsetWidth; // restart the animations: this is also how a step to another document comes in
  section.classList.add("enter");
  const ours = section.getAnimations({ subtree: true }).filter((a) => a.animationName === "view-in" || a.animationName === "view-fade");
  const finish = () => {
    if (token !== entering) return; // a later view has taken over
    delete root.dataset.entering;
    section.classList.remove("enter");
    entered?.();
  };
  Promise.all(ours.map((a) => a.finished.catch(() => {}))).then(finish);
  setTimeout(finish, 800); // never leave the page waiting on an animation
}

// Show another view. `apply` does everything that changes (hide the old, show and fill the new) and
// returns the visible view's element; `entered` is called when the entrance is over.
export function navigate(apply, entered, { first = false } = {}) {
  const known = history.state?.vt;
  const id = known ?? newId();
  if (currentId != null) scrolls.set(currentId, scrollY);
  if (known == null) history.replaceState({ ...(history.state || {}), vt: id }, "");
  const back = known != null && scrolls.has(known);
  currentId = id;
  const swap = () => {
    root.dataset.entering = "1"; // no thread is drawn from here until the entrance is over, not even by the view's own first frame
    setSync(true); // rendering is paused while a transition swaps the content: lay out now, not next frame
    let section;
    try {
      section = apply();
    } catch (e) {
      delete root.dataset.entering;
      throw e;
    } finally {
      setSync(false);
    }
    if (back) scrollBack(scrolls.get(id));
    else scrollTo(0, 0);
    enterView(section, entered);
  };
  if (first || reduced.matches || !document.startViewTransition) return swap();
  root.dataset.vt = "1"; // names the visible view for the transition, and only for its length
  const t = document.startViewTransition(swap);
  t.ready.catch(() => {}); // skipped by a quicker click: nothing to report
  t.finished.catch(() => {}).finally(() => delete root.dataset.vt);
}
