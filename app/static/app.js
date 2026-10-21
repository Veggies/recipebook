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
  // "#steps" opens the Steps tab (saving a note returns there); drop it so a reload starts fresh.
  const initialTab = location.hash === "#steps" ? "steps" : "ingredients";
  if (location.hash === "#steps") history.replaceState(null, "", location.pathname);
  show(initialTab);
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
