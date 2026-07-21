// Keep the header nav's active tab (the blue + bold one) in sync with the current
// page. The nav tabs render inline in the header (overrides/partials/header.html),
// and Material's instant navigation keeps the header across page loads — so the
// server-rendered active tab never moves on an in-page click (the clicked tab only
// looks blue because it is :focus-ed). Resync the --active class here.
function rompSyncTabs() {
  var here = location.pathname.replace(/\/+$/, "");
  document.querySelectorAll(".md-header__tabs .md-tabs__item").forEach(function (li) {
    var a = li.querySelector(".md-tabs__link");
    if (!a) return;
    var href = new URL(a.getAttribute("href"), location.href).pathname.replace(/\/+$/, "");
    li.classList.toggle("md-tabs__item--active", href === here);
  });
}

// Move --active to the clicked tab immediately, before navigation settles.
document.addEventListener("click", function (e) {
  var link = e.target.closest && e.target.closest(".md-header__tabs .md-tabs__link");
  if (!link) return;
  document.querySelectorAll(".md-header__tabs .md-tabs__item").forEach(function (li) {
    li.classList.toggle("md-tabs__item--active", li.contains(link));
  });
});

// Resync on every navigation (initial load, instant nav, back/forward).
if (typeof document$ !== "undefined") {
  document$.subscribe(rompSyncTabs);
} else {
  rompSyncTabs();
}
