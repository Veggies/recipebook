// Small progressive enhancements; every page works without this file.

// Large title collapses into the nav bar: once it scrolls under the bar, the bar frosts
// over and shows the small title.
const bar = document.querySelector(".bar");
const largeTitle = document.querySelector(".large-title");
if (bar && largeTitle && "IntersectionObserver" in window) {
  document.body.classList.add("has-large-title");
  new IntersectionObserver(([e]) => bar.classList.toggle("scrolled", !e.isIntersecting), {
    rootMargin: `-${bar.offsetHeight}px 0px 0px 0px`,
  }).observe(largeTitle);
}

// Label each navigation for the page transition in base.html: links into the app push,
// data-nav="back" pops, data-nav="tab" switches tabs without animating.
const markNav = (kind) => { try { sessionStorage.setItem("nav", kind); } catch {} };
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || a.target || a.origin !== location.origin || e.metaKey || e.ctrlKey || e.shiftKey) return;
  const kind = a.dataset.nav || "push";
  if (kind !== "tab") markNav(kind);
});

// Home Screen app: swipe in from the left edge to go back, as in native apps (Safari
// already does this in the browser, so only standalone mode needs it).
const backLink = document.querySelector('a[data-nav="back"]');
if (backLink && matchMedia("(display-mode: standalone)").matches) {
  let start = null;
  addEventListener("touchstart", (e) => {
    const t = e.touches[0];
    start = t.clientX < 24 ? { x: t.clientX, y: t.clientY } : null;
  }, { passive: true });
  addEventListener("touchend", (e) => {
    if (!start) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - start.x, dy = Math.abs(t.clientY - start.y);
    start = null;
    if (dx > 70 && dy < dx / 2) { markNav("back"); location.href = backLink.href; }
  }, { passive: true });
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
  document.querySelector(".add-more")?.setAttribute("hidden", "");
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

// Recipe editor: a plain form instead of a text format. Lines behave like Notes - return
// starts the next one, backspace on an empty line removes it, a pasted list becomes lines.
const editor = document.querySelector("#editor");
if (editor) {
  let dirty = false;
  let uploading = false;
  const markDirty = () => { dirty = true; };
  editor.addEventListener("input", markDirty);

  const autosize = (ta) => { ta.style.height = "auto"; ta.style.height = `${ta.scrollHeight}px`; };
  const fromTemplate = (id) => document.getElementById(id).content.firstElementChild.cloneNode(true);
  const kindOf = (el) => el.closest(".ed-group").dataset.kind;

  const addRow = (afterRow, kind, text = "") => {
    const row = fromTemplate(`tpl-${kind}-row`);
    const field = row.querySelector(".ed-line");
    field.value = text;
    afterRow.after(row);
    if (field.tagName === "TEXTAREA") autosize(field);
    return field;
  };

  const updateGroupButtons = () => {
    document.querySelectorAll(".ed-groups").forEach((groups) => {
      const many = groups.children.length > 1;
      groups.querySelectorAll(".ed-del-group").forEach((b) => { b.hidden = !many; });
    });
  };

  editor.addEventListener("keydown", (e) => {
    const field = e.target.closest(".ed-line");
    if (!field || e.isComposing) return;
    const row = field.closest(".ed-row");
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      addRow(row, kindOf(row)).focus();
      markDirty();
    } else if (e.key === "Backspace" && field.value === "" && row.parentElement.children.length > 1) {
      e.preventDefault();
      const prev = row.previousElementSibling?.querySelector(".ed-line");
      row.remove();
      if (prev) { prev.focus(); prev.setSelectionRange(prev.value.length, prev.value.length); }
      markDirty();
    }
  });

  editor.addEventListener("paste", (e) => {
    const field = e.target.closest(".ed-line");
    const text = e.clipboardData?.getData("text") || "";
    if (!field || !text.includes("\n")) return;
    e.preventDefault();
    // Pasted list: one line per row, minus bullets and step numbers.
    const lines = text.split(/\r?\n/).map((l) => l.replace(/^\s*(?:[-*•▢☐]|\d+[.)])\s*/, "").trim()).filter(Boolean);
    let row = field.closest(".ed-row");
    field.value = (field.value + " " + lines.shift()).trim();
    let last = field;
    lines.forEach((line) => { last = addRow(row, kindOf(row), line); row = last.closest(".ed-row"); });
    last.focus();
    markDirty();
  });

  editor.addEventListener("input", (e) => {
    if (e.target.matches("textarea")) autosize(e.target);
  });
  editor.querySelectorAll("textarea").forEach(autosize);

  editor.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.matches(".ed-del")) {
      const row = btn.closest(".ed-row");
      if (row.parentElement.children.length > 1) row.remove();
      else { row.querySelector(".ed-line").value = ""; }
      markDirty();
    } else if (btn.matches(".ed-add")) {
      const rows = btn.closest(".ed-group").querySelector(".ed-rows");
      addRow(rows.lastElementChild, kindOf(btn)).focus();
    } else if (btn.matches(".ed-add-group")) {
      const group = fromTemplate(`tpl-${btn.dataset.kind}-group`);
      document.querySelector(`.ed-groups[data-kind="${btn.dataset.kind}"]`).append(group);
      updateGroupButtons();
      group.querySelector(".ed-group-name").focus();
      markDirty();
    } else if (btn.matches(".ed-del-group")) {
      const group = btn.closest(".ed-group");
      const filled = [...group.querySelectorAll(".ed-line")].some((f) => f.value.trim());
      if (!filled || confirm("Remove this section and everything in it?")) {
        group.remove();
        updateGroupButtons();
        markDirty();
      }
    }
  });
  updateGroupButtons();

  // Photo: shrink on the phone (fast uploads, and Safari turns HEIC into JPEG here), then upload.
  const photo = editor.querySelector(".photo-pick");
  const photoInput = editor.querySelector("#photo-file");
  const photoLabel = editor.querySelector("[data-photo-label]");
  const imageUrl = editor.querySelector("#image_url");
  const setPhoto = (url) => {
    imageUrl.value = url;
    photo.querySelector(".photo-preview").src = url;
    photo.classList.toggle("has-photo", !!url);
    photoLabel.textContent = url ? "Change Photo" : "Add Photo";
    markDirty();
  };
  const shrink = async (file) => {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  };
  photoInput.addEventListener("change", async () => {
    const file = photoInput.files[0];
    if (!file) return;
    uploading = true;
    photoLabel.textContent = "Uploading…";
    try {
      let blob = file;
      try { blob = await shrink(file); } catch { /* send the original; the server resizes too */ }
      const body = new FormData();
      body.append("file", blob, "photo.jpg");
      const resp = await fetch("/api/images", { method: "POST", body });
      if (!resp.ok) throw new Error((await resp.json()).detail || "Upload failed");
      setPhoto((await resp.json()).url);
    } catch (err) {
      alert(`Couldn't add that photo. ${err.message}`);
      photoLabel.textContent = imageUrl.value ? "Change Photo" : "Add Photo";
    } finally {
      uploading = false;
      photoInput.value = "";
    }
  });
  photo.querySelector(".photo-remove").addEventListener("click", () => setPhoto(""));

  const value = (id) => editor.querySelector(`#${id}`)?.value ?? "";
  const collect = (kind) => [...document.querySelectorAll(`.ed-groups[data-kind="${kind}"] .ed-group`)].map((g) => {
    const lines = [...g.querySelectorAll(".ed-line")];
    return kind === "ingredients"
      ? { name: g.querySelector(".ed-group-name").value,
          items: lines.map((f) => ("amount" in f.dataset
            ? { line: f.value, amount: f.dataset.amount, item: f.dataset.item }
            : { line: f.value })) }
      : { name: g.querySelector(".ed-group-name").value, steps: lines.map((f) => f.value) };
  });

  editor.addEventListener("submit", (e) => {
    if (uploading) { e.preventDefault(); alert("Wait for the photo to finish uploading."); return; }
    if (!value("title").trim()) { e.preventDefault(); alert("Give the recipe a name first."); editor.querySelector("#title").focus(); return; }
    editor.elements.recipe.value = JSON.stringify({
      title: value("title"), description: value("description"), image_url: imageUrl.value,
      servings: value("servings"), prep_time: value("prep_time"), cook_time: value("cook_time"),
      total_time: value("total_time"), tags: value("tags"), notes: value("notes"),
      needs_review: !!editor.querySelector("#needs_review")?.checked,
      ingredient_groups: collect("ingredients"), step_groups: collect("steps"),
    });
    dirty = false;
  });

  document.querySelector("[data-cancel]")?.addEventListener("click", (e) => {
    if (!dirty) return;
    if (confirm("Discard your changes?")) dirty = false;  // don't ask again on the way out
    else { e.preventDefault(); e.stopImmediatePropagation(); }
  });
  addEventListener("beforeunload", (e) => { if (dirty) e.preventDefault(); });
}
