// Pairs with myscape.css's `user-select: none`: Firefox has no CSS
// equivalent of -webkit-user-drag, so preventDefault() on dragstart,
// delegated on document to cover icons injected later.
document.addEventListener('dragstart', (e) => {
  if (e.target.tagName === 'IMG') e.preventDefault();
});

document.getElementById('logoutBtn')?.addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/';
});

document.getElementById('generateLinkBtn')?.addEventListener('click', async (e) => {
  const btn = e.target;
  const errorEl = document.getElementById('linkError');
  errorEl.classList.remove('show');

  if (btn.dataset.code) {
    try {
      await navigator.clipboard.writeText(btn.dataset.code);
      btn.textContent = 'COPIED TO CLIPBOARD';
      btn.removeAttribute('title');
      btn.disabled = true;
    } catch (err) {
      errorEl.textContent = 'Could not copy the code -- please copy it manually.';
      errorEl.classList.add('show');
    }
    return;
  }

  btn.disabled = true;
  try {
    const res = await fetch('/api/link/start', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorEl.textContent = describeError(data, 'Could not generate a code. Please try again.');
      errorEl.classList.add('show');
      return;
    }
    btn.textContent = data.code;
    btn.dataset.code = data.code;
    btn.classList.add('link-banner-btn--code');
    btn.title = 'Click to copy this code to your clipboard.';
  } catch (err) {
    errorEl.textContent = 'Something went wrong. Please try again.';
    errorEl.classList.add('show');
  } finally {
    btn.disabled = false;
  }
});

function describeError(data, fallback) {
  if (!data || !data.detail) return fallback;
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail) && data.detail[0]?.msg) return data.detail[0].msg;
  return fallback;
}

// Linking happens in the RuneLite plugin, so poll the session "who am I"
// endpoint every few seconds and reload once account_hash is set.
const linkBanner = document.getElementById('linkBanner');
if (linkBanner) {
  const linkPollInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/auth/me');
      if (!res.ok) return; // e.g. session expired -- a normal reload will sort that out
      const data = await res.json();
      if (data.account_hash) {
        clearInterval(linkPollInterval);
        window.location.reload();
      }
    } catch (err) {
    }
  }, 3000);
}

// Friend-request count next to ACCOUNT (see _nav_sides): polls every 10s,
// pausing while the tab is hidden, and broadcasts a window event for the
// account page.
(function () {
  const badge = document.getElementById('navAccountBadge');
  if (!badge) return;
  function apply(data) {
    const total = (data && data.total) || 0;
    badge.textContent = total > 99 ? '99+' : String(total);
    badge.hidden = total <= 0;
    window.dispatchEvent(new CustomEvent('myscape:friend-notifications', { detail: data }));
  }
  async function poll() {
    if (document.hidden) return;
    try {
      const res = await fetch('/api/friends/notifications');
      if (!res.ok) return;
      apply(await res.json());
    } catch (err) {
    }
  }
  window.myscapePollFriendNotifications = poll;
  poll();
  setInterval(poll, 10000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
})();

// Site-wide hover tooltip for elements with data-tooltip (see
// .myscape-tooltip in myscape.css). SHOW_DELAY is short but avoids flashing
// tooltips while sweeping across dense grids (e.g. Collection Log). Hiding
// is immediate.
(function () {
  const SHOW_DELAY = 150;
  let tooltipEl = null;
  let showTimer = null;
  let currentTarget = null;
  // Set by window.myscapeDismissTooltip(el): el stays tooltip-free until the
  // pointer moves onto something else, so a button that was just pressed does
  // not show its tooltip again on the next mouse move.
  let suppressedTarget = null;

  function ensureTooltipEl() {
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.className = 'myscape-tooltip';
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }

  // Centered above the target; flips below if no room and clamps to the
  // viewport. Measured after the text is set (opacity: 0 still lays out,
  // unlike display: none, hence the CSS fades via opacity/transform).
  function positionTooltip(target, el) {
    const rect = target.getBoundingClientRect();
    const tipRect = el.getBoundingClientRect();
    const gap = 8;
    let left = rect.left + rect.width / 2 - tipRect.width / 2;
    let top = rect.top - tipRect.height - gap;
    if (top < 4) top = rect.bottom + gap;
    const maxLeft = window.innerWidth - tipRect.width - 4;
    if (left < 4) left = 4;
    else if (left > maxLeft) left = Math.max(4, maxLeft);
    el.style.left = left + 'px';
    el.style.top = top + 'px';
  }

  // Touch screens: window.myscapeTouchTooltipFilter(el) returning false
  // suppresses a tooltip.
  function tooltipAllowed(target) {
    if (!window.matchMedia('(hover: none)').matches) return true;
    var filter = window.myscapeTouchTooltipFilter;
    return typeof filter !== 'function' || filter(target) !== false;
  }

  function showTooltip(target) {
    if (currentTarget !== target) return;
    // A re-rendered-away target has an all-zero rect (tooltip would land
    // top-left).
    if (!target.isConnected) return;
    if (!tooltipAllowed(target)) return;
    const text = target.getAttribute('data-tooltip');
    if (!text) return;
    const el = ensureTooltipEl();
    el.classList.remove('show');
    el.textContent = text;
    // data-tooltip-wide: wider box for a long first line.
    el.classList.toggle('myscape-tooltip--wide', target.hasAttribute('data-tooltip-wide'));
    positionTooltip(target, el);
    // Commit the hidden state to a frame before adding 'show', or the
    // fade-in can collapse into an instant appearance.
    void el.offsetWidth;
    el.classList.add('show');
  }

  function hideTooltip() {
    clearTimeout(showTimer);
    currentTarget = null;
    if (tooltipEl) tooltipEl.classList.remove('show');
  }

  // For a button whose press moves or re-renders it (the Mindmaps fullscreen
  // toggle): the old tooltip would be left behind, so hide it and keep it off
  // while the pointer is still on the button.
  window.myscapeDismissTooltip = function (el) {
    suppressedTarget = el;
    hideTooltip();
  };

  document.addEventListener('mouseover', (e) => {
    if (suppressedTarget && !suppressedTarget.contains(e.target)) suppressedTarget = null;
    const target = e.target.closest ? e.target.closest('[data-tooltip]') : null;
    if (!target || target === currentTarget || target === suppressedTarget) return;
    currentTarget = target;
    clearTimeout(showTimer);
    showTimer = setTimeout(() => showTooltip(target), SHOW_DELAY);
  });

  document.addEventListener('mouseout', (e) => {
    const target = e.target.closest ? e.target.closest('[data-tooltip]') : null;
    if (!target || target !== currentTarget) return;
    if (e.relatedTarget && target.contains(e.relatedTarget)) return;
    hideTooltip();
  });

  window.addEventListener('scroll', hideTooltip, true);
  window.addEventListener('resize', hideTooltip);

  // Touch has no hover, so a tooltip-carrying link (Skills cells, Collection
  // Log tiles) takes two taps: first shows the tooltip, second navigates.
  // Buttons act on tap. (hover: none) keeps this off desktop.
  (function () {
    const noHover = window.matchMedia('(hover: none)');
    let armedLink = null;
    let armTimer = null;
    document.addEventListener('touchstart', (e) => {
      if (!currentTarget) return;
      if (e.target.closest && e.target.closest('[data-tooltip]') === currentTarget) return;
      armedLink = null;
      hideTooltip();
    }, { passive: true });
    function toggleDismisses(el) {
      var fn = window.myscapeTouchTooltipToggle;
      return typeof fn === 'function' && fn(el) === true;
    }
    document.addEventListener('click', (e) => {
      if (!noHover.matches) return;
      const tipTarget = e.target.closest ? e.target.closest('[data-tooltip]') : null;
      if (tipTarget && toggleDismisses(tipTarget)) {
        if (tipTarget === currentTarget && tooltipEl && tooltipEl.classList.contains('show')) {
          hideTooltip();
        } else {
          // Shown directly from the tap: the emulated mouseover doesn't
          // refire for an element the pointer is already on.
          clearTimeout(showTimer);
          currentTarget = tipTarget;
          showTooltip(tipTarget);
        }
        return;
      }
      const link = e.target.closest ? e.target.closest('a[data-tooltip]') : null;
      if (!link) { armedLink = null; return; }
      if (!tooltipAllowed(link)) return;
      if (armedLink === link) { armedLink = null; clearTimeout(armTimer); return; }
      e.preventDefault();
      armedLink = link;
      currentTarget = link;
      showTooltip(link);
      clearTimeout(armTimer);
      armTimer = setTimeout(() => { armedLink = null; hideTooltip(); }, 3000);
    }, true);
  })();
})();
