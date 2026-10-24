/* deck.js — keyboard and touch navigation for the SVG slide deck.
 *
 * The slides are separate SVG files embedded with <object>. Only the current
 * one is shown; the rest are moved off-screen rather than hidden with
 * display:none, because a display:none <object> never loads its document
 * (verified in a browser) and the deck would stutter on every arrow press.
 *
 * Kept as a separate file rather than inline so it can be linted and cached,
 * and so the <object> markup stays declarative.
 */
(function () {
  "use strict";

  var deck = document.getElementById("deck");
  if (!deck) return;

  var slides = Array.prototype.slice.call(
    deck.querySelectorAll("object.slide"));
  if (!slides.length) return;

  var current = 0;
  var label = document.getElementById("deck-pos");
  var prevBtn = document.getElementById("deck-prev");
  var nextBtn = document.getElementById("deck-next");

  function show(i) {
    // Wrap around, so the arrows are a loop rather than a dead end.
    current = ((i % slides.length) + slides.length) % slides.length;
    slides.forEach(function (s, n) {
      if (n === current) {
        s.classList.add("on");
        s.removeAttribute("aria-hidden");
      } else {
        s.classList.remove("on");
        s.setAttribute("aria-hidden", "true");
      }
    });
    if (label) {
      label.textContent = (current + 1) + " / " + slides.length;
    }
    if (prevBtn) prevBtn.disabled = false;
    if (nextBtn) nextBtn.disabled = false;
  }

  function go(delta) { show(current + delta); }

  if (prevBtn) {
    prevBtn.addEventListener("click", function () { go(-1); });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", function () { go(1); });
  }

  document.addEventListener("keydown", function (e) {
    // Do not hijack keys while the reader is in a form field.
    var t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" ||
               t.tagName === "SELECT" || t.isContentEditable)) {
      return;
    }
    switch (e.key) {
      case "ArrowRight":
      case "PageDown":
      case " ":
        go(1);
        e.preventDefault();
        break;
      case "ArrowLeft":
      case "PageUp":
        go(-1);
        e.preventDefault();
        break;
      case "Home":
        show(0);
        e.preventDefault();
        break;
      case "End":
        show(slides.length - 1);
        e.preventDefault();
        break;
      default:
        break;
    }
  });

  // Swipe on a phone.
  var startX = 0;
  var startY = 0;
  deck.addEventListener("touchstart", function (e) {
    startX = e.changedTouches[0].clientX;
    startY = e.changedTouches[0].clientY;
  }, { passive: true });

  deck.addEventListener("touchend", function (e) {
    var dx = e.changedTouches[0].clientX - startX;
    var dy = e.changedTouches[0].clientY - startY;
    // Only a clear horizontal swipe counts, so scrolling the page still works.
    if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      go(dx < 0 ? 1 : -1);
    }
  }, { passive: true });

  show(0);
})();
