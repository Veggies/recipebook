// Small progressive enhancements; every page works without this file.

// Hairline under the nav bar once content scrolls beneath it (and show the
// compact title on recipe pages once the large title is gone).
const bar = document.querySelector(".bar");
const largeTitle = document.querySelector(".large-title");
if (bar && largeTitle && "IntersectionObserver" in window) {
  new IntersectionObserver(([e]) => bar.classList.toggle("scrolled", !e.isIntersecting), {
    rootMargin: "-44px 0px 0px 0px",
  }).observe(largeTitle);
}

// Recipe page: tap a step to make it current; earlier steps are marked done.
const steps = [...document.querySelectorAll(".step")];
steps.forEach((step, i) => {
  const select = () => {
    const deselect = step.classList.contains("current");
    steps.forEach((s, j) => {
      s.classList.toggle("current", !deselect && j === i);
      s.classList.toggle("done", !deselect && j < i);
    });
  };
  step.addEventListener("click", select);
  step.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(); }
  });
});

// Recipe page on a phone: Ingredients | Steps switch. Each tab keeps its own scroll
// position, so checking an amount and switching back lands on the same step.
const tabs = document.querySelector(".tabs");
const layout = document.querySelector(".recipe-layout");
if (tabs && layout) {
  const buttons = [...tabs.querySelectorAll("[data-tab]")];
  const scrollPos = {};
  const show = (name) => {
    const current = layout.dataset.tab;
    if (current) scrollPos[current] = window.scrollY;
    layout.dataset.tab = name;
    document.querySelectorAll('input[name="tab"]').forEach((i) => { i.value = name; });
    buttons.forEach((b) => {
      const on = b.dataset.tab === name;
      b.setAttribute("aria-selected", String(on));
      b.setAttribute("aria-pressed", String(on));
    });
    if (current && current !== name) {
      // First visit to a tab: start at its top (switch pinned), unless we're still above that.
      // The layout isn't sticky, so its position is a stable reference; the switch's isn't.
      const pinTop = layout.getBoundingClientRect().top + window.scrollY - tabs.offsetHeight - bar.offsetHeight - 8;
      window.scrollTo(0, scrollPos[name] ?? Math.min(window.scrollY, pinTop));
    }
  };
  tabs.hidden = false;
  buttons.forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  // "#steps…" opens the Steps tab; "…notes" scrolls to the notes (where saving a note returns).
  // The hash is dropped afterwards so a reload starts fresh.
  const hash = location.hash;
  const initialTab = hash.startsWith("#steps") ? "steps" : "ingredients";
  if (hash) history.replaceState(null, "", location.pathname);
  show(initialTab);
  if (hash.endsWith("notes")) document.getElementById("notes")?.scrollIntoView();
}

// Keep the screen awake while a recipe is open.
if (steps.length && "wakeLock" in navigator) {
  let lock = null;
  const acquire = async () => {
    try { lock = await navigator.wakeLock.request("screen"); } catch { /* denied or unsupported */ }
  };
  acquire();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && (!lock || lock.released)) acquire();
  });
}

// Add page: when opened from the Share Sheet with ?url=, import straight away.
const addForm = document.querySelector("form[data-autosubmit]");
const showImporting = () => {
  document.querySelector(".add-form").hidden = true;
  document.querySelector(".importing").hidden = false;
};
if (addForm) {
  showImporting();
  addForm.submit();
}
document.querySelector(".add-form")?.addEventListener("submit", showImporting);

// Confirm destructive forms.
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (e) => {
    if (!confirm(form.dataset.confirm)) e.preventDefault();
  });
});

// Appearance: Auto follows the system; Light/Dark are remembered on this device.
const themeButtons = document.querySelectorAll("[data-theme-choice]");
const applyTheme = (choice) => {
  if (choice === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
  themeButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === choice)));
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => {
    m.content = choice === "dark" ? "#000000" : choice === "light" ? "#f2f2f7" : m.media.includes("dark") ? "#000000" : "#f2f2f7";
  });
};
let savedTheme = "auto";
try { savedTheme = localStorage.getItem("theme") || "auto"; } catch {}
applyTheme(savedTheme);
themeButtons.forEach((b) => b.addEventListener("click", () => {
  try { localStorage.setItem("theme", b.dataset.themeChoice); } catch {}
  applyTheme(b.dataset.themeChoice);
}));

// Shopping list, step 1: the button shows how many recipes are picked.
const pickForm = document.querySelector(".pick-form");
if (pickForm) {
  const submit = pickForm.querySelector("[data-pick-submit]");
  const update = () => {
    const n = pickForm.querySelectorAll('input[name="r"]:checked').length;
    submit.disabled = n === 0;
    submit.textContent = n ? `Build List (${n} recipe${n === 1 ? "" : "s"})` : "Pick at least one recipe";
  };
  pickForm.addEventListener("change", update);
  update();
}

// Shopping list, steps 2-3: tick what you have, then the final list to copy or share.
// Ticks are remembered on this device per set of recipes, so the page can be closed and reopened.
const shop = document.querySelector(".shop");
if (shop) {
  const storeKey = `shop:${shop.dataset.listId}`;
  const load = () => { try { return JSON.parse(localStorage.getItem(storeKey)) || {}; } catch { return {}; } };
  const save = (state) => { try { localStorage.setItem(storeKey, JSON.stringify(state)); } catch {} };
  const state = load();
  state.have ||= [];
  state.got ||= [];
  const haveBoxes = [...shop.querySelectorAll("[data-have]")];
  haveBoxes.forEach((box) => {
    box.checked = state.have.includes(box.dataset.have);
    box.addEventListener("change", () => {
      state.have = haveBoxes.filter((b) => b.checked).map((b) => b.dataset.have);
      save(state);
    });
  });

  const review = shop.querySelector('[data-phase="review"]');
  const final = shop.querySelector('[data-phase="final"]');
  const finalList = final.querySelector("[data-final]");

  // [{aisle, lines: [{key, text, html}]}] for everything not already at home.
  const needed = () => [...review.querySelectorAll("[data-aisle-items]")].map((ul) => ({
    aisle: ul.dataset.aisleItems,
    lines: [...ul.querySelectorAll("[data-have]")].filter((b) => !b.checked).map((b) => {
      const ing = b.closest("label").querySelector(".ing");
      const clone = ing.cloneNode(true);
      clone.querySelector(".src")?.remove();
      return { key: b.dataset.have, text: ing.dataset.line, html: clone.innerHTML };
    }),
  })).filter((g) => g.lines.length);

  const asText = (groups) => groups.map((g) => [g.aisle, ...g.lines.map((l) => l.text)].join("\n")).join("\n\n");

  const renderFinal = () => {
    const groups = needed();
    const total = groups.reduce((n, g) => n + g.lines.length, 0);
    final.querySelector("[data-summary]").textContent = total
      ? `${total} item${total === 1 ? "" : "s"} to buy · ${state.have.length} already at home`
      : "You have everything already.";
    finalList.replaceChildren(...groups.flatMap((g) => {
      const h = document.createElement("h3");
      h.className = "group-h";
      h.textContent = g.aisle;
      const ul = document.createElement("ul");
      ul.className = "list checklist";
      g.lines.forEach((l) => {
        const li = document.createElement("li");
        li.innerHTML = `<label><input type="checkbox"><span class="ing">${l.html}</span></label>`;
        const box = li.querySelector("input");
        box.checked = state.got.includes(l.key);  // ticked off in the store
        box.addEventListener("change", () => {
          state.got = box.checked ? [...state.got, l.key] : state.got.filter((k) => k !== l.key);
          save(state);
        });
        ul.append(li);
      });
      return [h, ul];
    }));
    return groups;
  };

  const showPhase = (phase) => {
    review.hidden = phase !== "review";
    final.hidden = phase !== "final";
    if (phase === "final") renderFinal();
    state.phase = phase;
    save(state);
    window.scrollTo(0, 0);
  };
  shop.querySelector("[data-finalize]").addEventListener("click", () => showPhase("final"));
  shop.querySelector("[data-back]").addEventListener("click", () => showPhase("review"));
  if (state.phase === "final") showPhase("final");

  const toast = (message) => {
    const t = document.createElement("div");
    t.className = "toast";
    t.textContent = message;
    document.body.append(t);
    setTimeout(() => t.remove(), 1800);
  };
  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); toast("Copied"); } catch { toast("Couldn't copy"); }
  };
  shop.querySelector("[data-copy]").addEventListener("click", () => copy(asText(needed())));
  shop.querySelector("[data-share]").addEventListener("click", async () => {
    const text = asText(needed());
    if (navigator.share) {
      // iPhone share sheet - pick Notes. AbortError just means the sheet was dismissed.
      try { await navigator.share({ title: "Shopping List", text }); } catch (e) { if (e.name !== "AbortError") copy(text); }
    } else {
      copy(text);
    }
  });
}
