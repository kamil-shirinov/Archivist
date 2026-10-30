// Archivist's review app: a static page over an exported run bundle (D12). It never calls a model, needs
// no key and runs from any file server; it reads data/bundles/index.json and the bundle it names.

import { boot, S } from "./store.js";
import { $, esc, toast } from "./util.js";
import { initTheme, labelRun, refresh } from "./chrome.js";
import * as palette from "./palette.js";
import * as overview from "./views/overview.js";
import * as review from "./views/review.js";
import * as documents from "./views/documents.js";
import * as doc from "./views/document.js";
import * as replay from "./views/replay.js";
import * as accuracy from "./views/accuracy.js";
import * as types from "./views/types.js";
import * as accounts from "./views/accounts.js";
import * as acct from "./views/account.js";
import * as transactions from "./views/transactions.js";

const VIEWS = { overview, review, accounts, acct, transactions, documents, doc, replay, accuracy, types };
const NAV_OF = { doc: "documents", acct: "accounts" };
let current = null;

function parse() {
  const raw = location.hash.slice(1) || "overview";
  const [path, qs] = raw.split("?");
  let view = path, arg = null;
  for (const p of ["doc", "review", "replay", "acct"])
    if (path.startsWith(`${p}-`)) {
      view = p;
      arg = decodeURIComponent(path.slice(p.length + 1));
    }
  if (!(view in VIEWS)) view = "overview";
  return { view, arg, query: new URLSearchParams(qs || "") };
}

function show() {
  const { view, arg, query } = parse();
  if (current && current !== view) VIEWS[current].leave?.();
  current = view;
  for (const n of Object.keys(VIEWS)) $(`v-${n}`).hidden = n !== view;
  document.querySelectorAll(".side a[data-v]").forEach((a) => a.setAttribute("aria-current", a.dataset.v === (NAV_OF[view] || view) ? "page" : "false"));
  scrollTo(0, 0);
  VIEWS[view].enter(arg, query);
}

async function start() {
  initTheme();
  try {
    await boot();
  } catch (e) {
    $("loading").remove();
    $("v-overview").hidden = false;
    $("v-overview").innerHTML =
      `<div class="failed"><h2>The run couldn’t be loaded</h2><p>${esc(e.message)}</p><p>This app reads the exported bundles under <code>data/bundles/</code>. Open it through a web server rooted at the repository (for example <code>python -m http.server</code> there, then <code>/ui/</code>), not from a file.</p></div>`;
    throw e;
  }
  $("loading").remove();
  labelRun();
  refresh();
  palette.init();
  $("add-doc").addEventListener("click", () =>
    toast("Reading new pages happens in the local app, where the models run. This hosted copy replays recorded runs only.")
  );
  for (const v of Object.values(VIEWS)) v.init?.();
  addEventListener("hashchange", show);
  addEventListener("resize", () => VIEWS[current]?.resize?.());
  addEventListener("scroll", () => VIEWS[current]?.scroll?.(), { passive: true });
  addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      palette.open();
      return;
    }
    if (e.key === "Escape" && !$("pal").hidden) {
      palette.close();
      return;
    }
    if (e.target.matches?.("input,select,textarea")) return;
    if (e.key === "/") {
      e.preventDefault();
      palette.open();
      return;
    }
    VIEWS[current]?.key?.(e);
  });
  show();
  document.documentElement.dataset.ready = "1"; // for the browser test: the run is loaded and a view is up
}

start();
