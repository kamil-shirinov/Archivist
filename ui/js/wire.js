// The thread: a thin gold line from a value in the record to the same value on the page.

export function hideWire(svg) {
  svg.querySelector("path").style.opacity = 0;
  svg.querySelector("circle").style.opacity = 0;
}

// Draw it from `from` to `to` inside `host`, clipped to the `clip` box (the page); `dir` is "l" when
// the page is to the left of the thing it is drawn from, "r" when to the right.
export function wire(svg, host, from, to, clip, dir) {
  // While a view is still coming in its content moves: the thread waits, and each view draws it again
  // when the entrance is over (its `entered` hook).
  if (document.documentElement.dataset.entering) return hideWire(svg);
  if (!from || !to || getComputedStyle(svg).display === "none") return hideWire(svg);
  const h = host.getBoundingClientRect(), a = from.getBoundingClientRect(), b = to.getBoundingClientRect(), c = clip.getBoundingClientRect();
  const inside = (r, k, m) => r.bottom > k.top + m && r.top < k.bottom - m && r.right > k.left + m && r.left < k.right - m;
  if (!inside(b, c, 6) || !inside(a, { top: 56, bottom: innerHeight, left: 0, right: innerWidth }, 2)) return hideWire(svg);
  const y1 = a.top + a.height / 2 - h.top, y2 = b.top + b.height / 2 - h.top;
  let x1, x2;
  if (dir === "l") {
    x1 = a.left - h.left - 2;
    x2 = Math.min(b.right, c.right - 6) - h.left + 6;
  } else {
    x1 = a.right - h.left + 2;
    x2 = Math.max(b.left, c.left + 6) - h.left - 6;
  }
  const d = Math.max(50, Math.abs(x1 - x2) * 0.45) * (dir === "l" ? -1 : 1);
  const p = svg.querySelector("path"), dot = svg.querySelector("circle");
  p.setAttribute("d", `M${x1},${y1} C${x1 + d},${y1} ${x2 - d},${y2} ${x2},${y2}`);
  dot.setAttribute("cx", x2);
  dot.setAttribute("cy", y2);
  p.style.opacity = 0.9;
  dot.style.opacity = 1;
}

// Keep calling fn for ms milliseconds, once a frame (a camera is moving).
export function follow(fn, ms) {
  const t0 = performance.now();
  (function step(t) {
    fn();
    if (t - t0 < ms) requestAnimationFrame(step);
  })(t0);
}

export function noAnim(el, fn) {
  el.style.transition = "none";
  fn();
  void el.offsetWidth;
  el.style.transition = "";
}
