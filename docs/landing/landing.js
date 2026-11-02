// The landing page's script (docs/landing.py writes the page, docs/make_site.py ships this beside it).
// It makes no request: the theme toggle, the sections fading in as they come into view, and the replay
// panel, which plays one recorded decision row by row. The page is complete without it; with it, and only
// for a visitor who has not asked for reduced motion, the rows start by themselves.

(() => {
  const root = document.documentElement;
  const still = matchMedia("(prefers-reduced-motion: reduce)");

  // The theme: the system's, or the one chosen in the app (its own localStorage key).
  const toggle = document.querySelector("[data-theme-toggle]");
  const effective = () => root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  if (toggle) {
    const mark = () => toggle.setAttribute("aria-pressed", String(effective() === "dark"));
    mark();
    toggle.addEventListener("click", () => {
      const next = effective() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try {
        localStorage.setItem("archivist-theme", next);
      } catch {
        /* a browser that keeps nothing: the choice lasts for this page */
      }
      mark();
    });
  }

  // Each section fades in once, as it scrolls into view.
  const reveals = [...document.querySelectorAll(".reveal")];
  if ("IntersectionObserver" in window) {
    const seen = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          e.target.classList.add("in");
          seen.unobserve(e.target);
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.06 },
    );
    reveals.forEach((el) => seen.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("in"));
  }

  // The replay: the log's rows, and the marks on the page's crop, appear one step at a time. Each row and
  // each mark names the step it belongs to (data-from, and data-to for one that only shows for a while); step k
  // shows what belongs to it.
  const panel = document.querySelector("[data-replay]");
  if (!panel) return;
  const rows = [...panel.querySelectorAll(".rp-log li")];
  const layers = [...panel.querySelectorAll("[data-from]")];
  const count = panel.querySelector(".rp-count");
  const replay = panel.querySelector('[data-act="replay"]');
  const pause = panel.querySelector('[data-act="pause"]');
  const GAP = [1000, 1300, 1000, 1000, 1200, 1300, 0]; // how long each row stays alone, in ms
  let shown = rows.length;
  let timer = 0;
  let paused = false;
  let running = false;

  const show = (k) => {
    shown = k;
    rows.forEach((r, i) => r.classList.toggle("on", i < k));
    layers.forEach((l) => l.classList.toggle("on", Number(l.dataset.from) <= k && (l.dataset.to === undefined || k <= Number(l.dataset.to))));
    count?.classList.toggle("on", k >= rows.length);
  };
  const next = () => {
    if (paused || !running) return;
    if (shown >= rows.length) {
      running = false;
      pause.disabled = true;
      return;
    }
    show(shown + 1);
    timer = setTimeout(next, GAP[shown - 1] ?? 1000);
  };
  const start = () => {
    clearTimeout(timer);
    root.classList.add("play"); // from here the rows that are not yet shown are hidden
    show(0);
    paused = false;
    running = true;
    pause.disabled = false;
    pause.textContent = "Pause";
    timer = setTimeout(next, 450);
  };
  replay.addEventListener("click", start);
  pause.addEventListener("click", () => {
    if (!running) return;
    paused = !paused;
    pause.textContent = paused ? "Resume" : "Pause";
    clearTimeout(timer);
    if (!paused) next();
  });

  if (still.matches) {
    pause.disabled = true; // the settled state stays until the visitor presses Replay
    return;
  }
  if (!root.classList.contains("play")) root.classList.add("play");
  show(0);
  if ("IntersectionObserver" in window) {
    const watch = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        watch.disconnect();
        start();
      },
      { threshold: 0.35 },
    );
    watch.observe(panel);
  } else {
    start();
  }
})();
