// The landing page's script (docs/landing.py writes the page, docs/make_site.py ships this beside it).
// It makes no request. The page is complete without it; with it, and only for a visitor who has not asked for
// reduced motion, things move: sections fade in, the replay plays on the page, the glass catches the pointer, the
// ledger re-counts when the switch is flipped, a theme change is revealed in a circle from the toggle. What it adds
// for everyone: the ledger's switch and rows, the pipeline's step panels, the charts' tooltips and keys.

(() => {
  const root = document.documentElement;
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  const $ = (selector, within = document) => within.querySelector(selector);
  const $$ = (selector, within = document) => [...within.querySelectorAll(selector)];

  // --- the theme: the system's, or the one chosen in the app (its own localStorage key) -------------------
  // A change is revealed by a circle growing from the toggle, about 600 ms, with the browser's View Transition;
  // where the browser has none the colours cross-fade; with reduced motion it is instant.
  const toggle = $("[data-theme-toggle]");
  const effective = () => root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  if (toggle) {
    const mark = () => toggle.setAttribute("aria-pressed", String(effective() === "dark"));
    const apply = (next) => {
      root.dataset.theme = next;
      try {
        localStorage.setItem("archivist-theme", next);
      } catch {
        /* a browser that keeps nothing: the choice lasts for this page */
      }
      mark();
    };
    mark();
    toggle.addEventListener("click", () => {
      const next = effective() === "dark" ? "light" : "dark";
      if (still.matches) return apply(next);
      if (typeof document.startViewTransition === "function") {
        const box = toggle.getBoundingClientRect();
        const x = box.left + box.width / 2;
        const y = box.top + box.height / 2;
        const reach = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
        const change = document.startViewTransition(() => apply(next));
        change.ready
          .then(() =>
            root.animate(
              { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${reach}px at ${x}px ${y}px)`] },
              { duration: 600, easing: "cubic-bezier(.35,.05,.2,1)", pseudoElement: "::view-transition-new(root)" },
            ),
          )
          .catch(() => {});
      } else {
        root.classList.add("theme-fade");
        apply(next);
        setTimeout(() => root.classList.remove("theme-fade"), 480);
      }
    });
  }

  // --- sections fade in once, as they scroll into view ---------------------------------------------------------
  const reveals = $$(".reveal");
  if ("IntersectionObserver" in window) {
    const seen = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("in");
          seen.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -6% 0px", threshold: 0.04 },
    );
    reveals.forEach((el) => seen.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("in"));
  }

  // --- the navigation marks the section in view ------------------------------------------------------------------
  const links = $$('.nav a[href^="#"]');
  if (links.length && "IntersectionObserver" in window) {
    const spy = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          links.forEach((a) => (a.getAttribute("href") === `#${entry.target.id}` ? a.setAttribute("aria-current", "location") : a.removeAttribute("aria-current")));
        }
      },
      { rootMargin: "-35% 0px -60% 0px" },
    );
    links.forEach((a) => {
      const target = $(a.getAttribute("href"));
      if (target) spy.observe(target);
    });
  }

  // --- glass: a soft highlight that follows the pointer (moved by transform only; none with reduced motion) ------
  $$("[data-glass]").forEach((el) => el.insertAdjacentHTML("afterbegin", '<span class="shine" aria-hidden="true"><i></i></span>'));
  if (!still.matches) {
    let pending = 0;
    let last = null;
    document.addEventListener(
      "pointermove",
      (event) => {
        if (event.pointerType !== "mouse") return;
        last = event;
        if (pending) return;
        pending = requestAnimationFrame(() => {
          pending = 0;
          for (let el = last.target.closest?.("[data-glass]"); el; el = el.parentElement?.closest("[data-glass]")) {
            const box = el.getBoundingClientRect();
            el.style.setProperty("--mx", `${last.clientX - box.left}px`);
            el.style.setProperty("--my", `${last.clientY - box.top}px`);
          }
        });
      },
      { passive: true },
    );
  }

  // --- what a mark says: hovered, focused or tapped, shown beside it -------------------------------------------------
  const tooltip = document.createElement("div");
  tooltip.className = "tooltip";
  tooltip.setAttribute("aria-hidden", "true");
  document.body.append(tooltip);
  const MARKS = ".mk, .cb, .seg b";
  let owner = null;
  let pinned = false;
  const place = (el) => {
    const anchor = $(".pt", el) || el;
    const at = anchor.getBoundingClientRect();
    const size = tooltip.getBoundingClientRect();
    const x = Math.min(Math.max(at.left + at.width / 2 - size.width / 2, 8), innerWidth - size.width - 8);
    const above = at.top - size.height - 10;
    tooltip.style.transform = `translate(${x}px, ${above < 8 ? at.bottom + 10 : above}px)`;
  };
  const showTip = (el) => {
    const text = $(".tip", el)?.textContent;
    if (!text) return;
    owner = el;
    tooltip.textContent = text.replace(/\s+/g, " ").trim();
    place(el);
    tooltip.classList.add("on");
  };
  const hideTip = () => {
    owner = null;
    pinned = false;
    tooltip.classList.remove("on");
  };
  document.addEventListener("pointerover", (event) => {
    const el = event.target.closest?.(MARKS);
    if (el && event.pointerType === "mouse" && !pinned) showTip(el);
  });
  document.addEventListener("pointerout", (event) => {
    if (event.pointerType === "mouse" && !pinned && event.target.closest?.(MARKS)) hideTip();
  });
  document.addEventListener("focusin", (event) => {
    const el = event.target.closest?.(MARKS);
    if (el) showTip(el);
  });
  document.addEventListener("focusout", (event) => {
    if (event.target.closest?.(MARKS)) hideTip();
  });
  document.addEventListener("click", (event) => {
    const el = event.target.closest?.(MARKS);
    if (el && (event.pointerType === "touch" || event.pointerType === "pen" || event.detail === 0 || el === owner)) {
      // a tap (or a key press) keeps the tip until the next tap; a second tap on the same mark closes it
      if (pinned && owner === el) return hideTip();
      showTip(el);
      pinned = true;
    } else if (!el) {
      hideTip();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideTip();
  });
  addEventListener("scroll", () => owner && place(owner), { passive: true });

  // --- the replay: the notes, the marks on the page and the leaders between them appear one step at a time ----------
  const frame = $("[data-replay]");
  if (frame) {
    const notes = $$(".notes li", frame);
    const layers = $$("[data-from]", frame);
    const count = $(".rp-count", frame);
    const replay = $('[data-act="replay"]', frame);
    const pause = $('[data-act="pause"]', frame);
    const rail = $$(".rail li", frame);
    const railWrap = $(".rail-wrap", frame);
    const stage = $(".stage", frame);
    const leaderBox = $(".leaders", frame);
    const pen = $(".layer.pen", frame);
    const GAP = [1000, 1300, 1000, 1000, 1200, 1300, 0]; // how long each step stays alone, in ms
    const leaders = [];
    let shown = notes.length;
    let timer = 0;
    let paused = false;
    let running = false;

    const show = (k) => {
      shown = k;
      notes.forEach((li, i) => {
        li.classList.toggle("on", i < k);
        li.classList.toggle("now", i === k - 1);
      });
      layers.forEach((l) => l.classList.toggle("on", Number(l.dataset.from) <= k && (l.dataset.to === undefined || k <= Number(l.dataset.to))));
      count?.classList.toggle("on", k >= notes.length);
      rail.forEach((li, i) => {
        li.classList.toggle("on", i < k);
        li.classList.toggle("now", i === k - 1);
      });
      railWrap.style.setProperty("--p", String(k <= 1 ? 0 : (k - 1) / (notes.length - 1)));
      leaders.forEach((l, i) => l.classList.toggle("on", i < k));
    };

    // The value the leaders point at: the centre of the pen loop, in the stage's own coordinates.
    const anchor = () => {
      const svg = pen.ownerSVGElement;
      const m = svg.getScreenCTM();
      const b = pen.getBBox();
      const at = (x, y) => ({ x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f });
      const p0 = at(b.x, b.y);
      const p1 = at(b.x + b.width, b.y + b.height);
      return { x: (p0.x + p1.x) / 2, y: (p0.y + p1.y) / 2, r: Math.max(p1.x - p0.x, p1.y - p0.y) / 2 };
    };
    const lay = () => {
      leaders.length = 0;
      leaderBox.textContent = "";
      if (matchMedia("(max-width: 1020px)").matches) return; // the notes stack under the scan: nothing to join
      const s = stage.getBoundingClientRect();
      const c = anchor();
      notes.forEach((li) => {
        const r = li.getBoundingClientRect();
        const x = (li.dataset.side === "l" ? r.right : r.left) - s.left;
        const y = r.top + r.height / 2 - s.top;
        const dx = c.x - s.left - x;
        const dy = c.y - s.top - y;
        const el = document.createElement("i");
        el.className = "leader";
        el.style.cssText = `--x:${x.toFixed(1)}px;--y:${y.toFixed(1)}px;--len:${Math.max(Math.hypot(dx, dy) - c.r - 4, 0).toFixed(1)}px;--a:${Math.atan2(dy, dx).toFixed(4)}rad`;
        leaderBox.append(el);
        leaders.push(el);
      });
      show(shown);
    };

    const next = () => {
      if (paused || !running) return;
      if (shown >= notes.length) {
        running = false;
        pause.disabled = true;
        return;
      }
      show(shown + 1);
      timer = setTimeout(next, GAP[shown - 1] ?? 1000);
    };
    const start = () => {
      clearTimeout(timer);
      root.classList.add("play"); // from here the notes that are not yet shown are hidden
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
    // The rail: a step to look at, which holds the replay there until it is resumed.
    $$("[data-goto]", frame).forEach((b) =>
      b.addEventListener("click", () => {
        clearTimeout(timer);
        root.classList.add("play");
        running = true;
        paused = true;
        pause.disabled = false;
        pause.textContent = "Resume";
        show(Number(b.dataset.goto));
      }),
    );

    const svg = pen.ownerSVGElement;
    const wide = svg.getAttribute("viewBox").split(" ").map(Number);
    const narrow = matchMedia("(max-width: 720px)");
    const crop = () => {
      const [x, y, w, h] = wide;
      svg.setAttribute("viewBox", narrow.matches ? [x + w / 4, y + h / 4, w / 2, h / 2].join(" ") : wide.join(" "));
      lay();
    };
    narrow.addEventListener("change", crop);
    show(notes.length);
    crop();
    if ("ResizeObserver" in window) new ResizeObserver(lay).observe(stage);
    document.fonts?.ready.then(lay);
    if (still.matches) {
      pause.disabled = true; // the settled state stays until the visitor presses Replay
    } else {
      root.classList.add("play");
      show(0);
      if ("IntersectionObserver" in window) {
        const watch = new IntersectionObserver(
          (entries) => {
            if (!entries.some((e) => e.isIntersecting)) return;
            watch.disconnect();
            start();
          },
          { threshold: 0.4 },
        );
        watch.observe($(".scan", frame));
      } else {
        start();
      }
    }
  }

  // --- the ledger: where Archivist runs (the numbers re-count), and a row's evidence --------------------------------
  const ledger = $("#ledger");
  if (ledger) {
    const NUMBER = /\d[\d,]*(?:\.\d+)?/g;
    const decimals = (token) => (token.includes(".") ? token.split(".")[1].length : 0);
    const render = (token, value) => {
      const text = value.toFixed(decimals(token));
      if (!token.includes(",")) return text;
      const [whole, fraction] = text.split(".");
      return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (fraction ? `.${fraction}` : "");
    };
    // The incoming side counts from the outgoing one's figures to its own, each fact by the figures in its text;
    // where the two do not have the same figures it just fades. At rest every fact reads exactly as its file says.
    const recount = (from, to) => {
      const before = $$("[data-fact]", from);
      const jobs = [];
      $$("[data-fact]", to).forEach((el, i) => {
        const a = before[i]?.textContent.match(NUMBER);
        const final = el.textContent;
        const b = final.match(NUMBER);
        if (a && b && a.length === b.length) jobs.push({ el, final, a, b, parts: final.split(NUMBER) });
      });
      if (!jobs.length) return;
      const began = performance.now();
      const step = (now) => {
        const t = Math.min((now - began) / 560, 1);
        const eased = 1 - Math.pow(1 - t, 3);
        for (const job of jobs) {
          job.el.textContent =
            t >= 1
              ? job.final
              : job.b.reduce((text, token, i) => text + render(token, parseFloat(job.a[i].replace(/,/g, "")) + (parseFloat(token.replace(/,/g, "")) - parseFloat(job.a[i].replace(/,/g, ""))) * eased) + job.parts[i + 1], job.parts[0]);
        }
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
    let mode = ledger.dataset.mode;
    const buttons = $$(".ro", ledger);
    const choose = (next) => {
      if (next === mode) return;
      const previous = mode;
      mode = next;
      ledger.dataset.mode = next;
      buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === next)));
      const side = (m) => (m === "hosted" ? ".v.h" : ".v.o");
      $$(".swap", ledger).forEach((swap) => {
        const from = $(side(previous), swap);
        const to = $(side(next), swap);
        from.setAttribute("aria-hidden", "true");
        to.removeAttribute("aria-hidden");
        if (!still.matches) recount(from, to);
      });
      $$(".pane", ledger).forEach((pane) => (pane.hidden = pane.dataset.mode !== next));
    };
    buttons.forEach((b) => b.addEventListener("click", () => choose(b.dataset.mode)));
    ledger.addEventListener("click", (event) => {
      const opener = event.target.closest(".opener");
      if (!opener) return;
      const open = opener.getAttribute("aria-expanded") !== "true";
      opener.setAttribute("aria-expanded", String(open));
      document.getElementById(opener.getAttribute("aria-controls")).hidden = !open;
    });
  }

  // --- the pipeline: a step opens what it checks and what happens when it fails ------------------------------------
  const steps = $$(".pstep");
  const panels = $$(".spanel");
  const closeSteps = () => {
    steps.forEach((s) => s.setAttribute("aria-expanded", "false"));
    panels.forEach((p) => (p.hidden = true));
  };
  steps.forEach((step) =>
    step.addEventListener("click", () => {
      const open = step.getAttribute("aria-expanded") !== "true";
      closeSteps();
      if (!open) return;
      step.setAttribute("aria-expanded", "true");
      document.getElementById(step.getAttribute("aria-controls")).hidden = false;
    }),
  );
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && steps.some((s) => s.getAttribute("aria-expanded") === "true")) closeSteps();
  });

  // --- the real scans: the official answer key or the corrected one -----------------------------------------------
  const keys = $$(".ks");
  keys.forEach((key) =>
    key.addEventListener("click", () => {
      if (key.disabled) return;
      keys.forEach((k) => k.setAttribute("aria-pressed", String(k === key)));
      $$(".rg-set").forEach((set) => (set.hidden = set.dataset.key !== key.dataset.key));
    }),
  );

  // --- the condition chart: an arm turned off and on -------------------------------------------------------------
  $$(".cond").forEach((chart) =>
    $$(".lg", chart).forEach((button) =>
      button.addEventListener("click", () => {
        const on = button.getAttribute("aria-pressed") !== "true";
        button.setAttribute("aria-pressed", String(on));
        const off = new Set((chart.dataset.off || "").split(" ").filter(Boolean));
        if (on) off.delete(button.dataset.arm);
        else off.add(button.dataset.arm);
        chart.dataset.off = [...off].join(" ");
      }),
    ),
  );

  // --- an ordinary laptop: if the first frames are slow, the glass goes solid and the glow stops --------------------
  if (!still.matches && !navigator.webdriver) {
    let frames = 0;
    let slow = 0;
    let before = performance.now();
    const probe = (now) => {
      const took = now - before;
      before = now;
      if (++frames > 8 && took > 34) slow++;
      if (frames < 150) requestAnimationFrame(probe);
      else if (slow > 30) root.classList.add("calm");
    };
    requestAnimationFrame(probe);
  }
})();
