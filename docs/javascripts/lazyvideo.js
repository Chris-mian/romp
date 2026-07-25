// Play each demo clip only while it is on screen.
//
// The home page carries five clips. With a plain `autoplay`, a browser fetches
// every one of them the moment the page opens, so a phone on a slow link pays
// for the whole page before it can read the first paragraph. The markup instead
// sets preload="none" and marks the clip with data-romp-autoplay; nothing is
// fetched until this script starts it, which happens as it scrolls into view.
// Clips pause on the way out, so a background tab is not decoding video either.
//
// Without JavaScript the clips still render with their controls, so pressing
// play works; the control bar is only hidden as an enhancement, never as a
// requirement (see the hover wiring below).
function rompWireVideos() {
  // Skip clips already wired, so running twice on one page costs nothing.
  var vids = document.querySelectorAll("video[data-romp-autoplay]:not([data-romp-wired])");
  if (!vids.length) return;
  vids.forEach(function (v) { v.setAttribute("data-romp-wired", ""); });

  var play = function (v) { var p = v.play(); if (p && p.catch) p.catch(function () {}); };

  // Controls stay out of the way until you want them. A looping demo clip with a
  // permanent control bar reads as a video player you are supposed to operate,
  // when it is really a moving figure; the bar also covers the bottom of the
  // frame, which is where the status strip sits in several of these captures.
  //
  // `controls` is all-or-nothing in HTML, so this toggles the property instead.
  // The markup keeps the attribute, which means no-JS readers still get a
  // working player and we only ever take controls AWAY as an enhancement.
  //
  // Shown on hover, on keyboard focus, and whenever the clip is paused — if a
  // reader has stopped it, they need the way to start it again. Hidden only
  // while it is playing, so the bar never vanishes out from under a pointer.
  vids.forEach(function (v) {
    var show = function () { v.controls = true; };
    var hide = function () { if (!v.paused) v.controls = false; };
    v.controls = false;
    v.addEventListener("pointerenter", show);
    v.addEventListener("pointerleave", hide);
    v.addEventListener("focus", show);
    v.addEventListener("blur", hide);
    v.addEventListener("pause", show);
  });

  if (!("IntersectionObserver" in window)) {
    vids.forEach(play);   // no observer: fall back to the old always-on behavior
    return;
  }

  // The margin starts a clip just before it reaches the viewport, so it is
  // already running by the time it is fully in view.
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) play(e.target);
      else e.target.pause();
    });
  }, { rootMargin: "250px 0px" });

  vids.forEach(function (v) { io.observe(v); });
}

// Instant navigation swaps the page body without a reload, so rewire per navigation.
if (typeof document$ !== "undefined") document$.subscribe(rompWireVideos);

// Wire the first page directly too. document$ only emits once Material's own
// bundle has initialized, and when that fails the clips would otherwise sit
// dead with no way to start them.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", rompWireVideos);
} else {
  rompWireVideos();
}
