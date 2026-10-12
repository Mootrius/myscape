(function () {
  // The first child is normally <header>, but the link-account banner
  // renders ahead of it (body.landing > *:first-child in myscape.css).
  var firstStop = document.body.firstElementChild;
  var anchors = Array.prototype.slice.call(
    document.querySelectorAll('.landing-anchor:not(.landing-anchor--intro)')
  );
  var footer = document.querySelector('footer');
  var stops = [firstStop].concat(anchors, [footer]).filter(Boolean);
  if (stops.length < 2) return;

  var current = 0;
  var locked = false;
  var lockGen = 0;

  // One persistent listener: scrollend can fire more than once per scroll,
  // and per-goTo add/remove pairs could leave stale listeners behind.
  window.addEventListener('scrollend', function () {
    locked = false;
  });

  // Scroll clamps to the max position, so the footer can't reach its raw
  // offsetTop; clamp each stop's expected position the same way so the
  // footer isn't mistaken for the mindmaps panel.
  function stopY(el) {
    var maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    return Math.min(el.offsetTop, Math.max(0, maxScroll));
  }

  function nearestStop() {
    var y = window.scrollY;
    var idx = 0;
    for (var i = 0; i < stops.length; i++) {
      if (stopY(stops[i]) <= y + 2) idx = i;
    }
    return idx;
  }

  function goTo(index) {
    index = Math.max(0, Math.min(stops.length - 1, index));
    current = index;
    locked = true;
    var myGen = ++lockGen;
    // scrollend doesn't fire for a no-op scrollIntoView (e.g. down on the
    // last panel); this backstop clears the lock, and lockGen stops it
    // clearing a later goTo()'s lock.
    window.setTimeout(function () {
      if (lockGen === myGen) locked = false;
    }, 900);
    stops[current].scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  window.addEventListener('wheel', function (e) {
    if (e.ctrlKey || Math.abs(e.deltaY) < 4) return;
    // The FAQ panel can exceed the screen height; scroll it normally until
    // its edge is in view.
    var faq = e.target.closest ? e.target.closest('.landing-anchor--faq') : null;
    if (faq) {
      var r = faq.getBoundingClientRect();
      if ((e.deltaY > 0 && r.bottom > window.innerHeight + 2) || (e.deltaY < 0 && r.top < -2)) return;
    }
    e.preventDefault();
    if (locked) return;
    goTo(nearestStop() + (e.deltaY > 0 ? 1 : -1));
  }, { passive: false });
})();

// Phone width: the gold app name stays 30px and only shrinks (never grows)
// when it wouldn't fit beside the character, so it never ellipsizes.
(function () {
  var mq = window.matchMedia('(max-width: 700px)');
  function fit() {
    var golds = document.querySelectorAll('[class$="-preview-tagline-gold"]');
    for (var i = 0; i < golds.length; i++) {
      var g = golds[i];
      g.style.fontSize = '';
      if (!mq.matches) continue;
      var wrap = g.closest('[class$="-preview-tagline-wrap"]');
      if (!wrap) continue;
      var wcs = window.getComputedStyle(wrap);
      var avail = wrap.clientWidth - (parseFloat(wcs.paddingLeft) || 0) - (parseFloat(wcs.paddingRight) || 0);
      if (avail <= 0) continue;
      var size = 30;
      if (g.scrollWidth > avail) {
        size = Math.floor(30 * avail / g.scrollWidth);
        g.style.fontSize = size + 'px';
        while (size > 14 && g.scrollWidth > avail) {
          size -= 1;
          g.style.fontSize = size + 'px';
        }
      }
    }
  }
  fit();
  window.addEventListener('resize', fit);
  window.addEventListener('load', fit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
})();

// The intro panel plus header must be exactly one screen. Header height
// varies (link banner, wrapping), so feed the measured gap into a custom
// property used by myscape.css's height calc.
(function () {
  var intro = document.querySelector('.landing-anchor--intro');
  if (!intro) return;

  function sync() {
    var above = intro.getBoundingClientRect().top + window.scrollY;
    document.documentElement.style.setProperty('--landing-intro-above', above + 'px');
  }

  sync();
  window.addEventListener('resize', sync);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(sync);
  }
})();
