(function () {
  var FAQ = __FAQ_JSON__;
  var input = document.getElementById('hsSearch');
  var clearBtn = document.getElementById('hsSearchClear');
  var statusEl = document.getElementById('hsStatus');
  var noteEl = document.getElementById('hsNote');
  var DISCORD = '<a href="https://discord.gg/myscape" target="_blank" rel="noopener noreferrer">Discord server</a>';
  var resultsEl = document.getElementById('hsResults');

  var STOP = {};
  ('a an and are as at be but by can could do does for from get got ' +
   'have how i if in into is it its me my of on or our so than that ' +
   'the their then there these they this to up us was we what when ' +
   'where which who why will with would you your ' +
   'here too also just really please very anymore into about').split(' ').forEach(function (w) { STOP[w] = true; });

  function words(s) {
    return String(s).toLowerCase().replace(/['\u2019]/g, '').match(/[a-z0-9~]+/g) || [];
  }
  function stem(w) {
    var n = w.length;
    if (n > 4 && w.slice(-3) === 'ies') return w.slice(0, -3) + 'y';
    if (n > 5 && w.slice(-3) === 'ing') return w.slice(0, -3);
    if (n > 4 && w.slice(-2) === 'ed') return w.slice(0, -2);
    if (n > 3 && w.slice(-1) === 's' && w.slice(-2) !== 'ss') return w.slice(0, -1);
    return w;
  }
  function stems(s) { return words(s).map(stem); }

  function near(a, b) {
    if (Math.abs(a.length - b.length) > 1) return false;
    var i = 0;
    while (i < a.length && i < b.length && a[i] === b[i]) i++;
    if (i === a.length || i === b.length) return Math.abs(a.length - b.length) <= 1;
    if (a.length === b.length) {
      if (a.slice(i + 1) === b.slice(i + 1)) return true;
      if (a[i] === b[i + 1] && a[i + 1] === b[i] && a.slice(i + 2) === b.slice(i + 2)) return true;
      return false;
    }
    return a.length > b.length ? a.slice(i + 1) === b.slice(i) : b.slice(i + 1) === a.slice(i);
  }

  // Score of a typed word against the best word in a list: 3 exact, 2
  // prefix, 1.5 one-typo, 0 none.
  function best(t, list) {
    var b = 0;
    for (var i = 0; i < list.length; i++) {
      var w = list[i];
      if (w === t) return 3;
      if (t.length >= 4 && w.length >= 4 && (w.indexOf(t) === 0 || t.indexOf(w) === 0)) b = Math.max(b, 2);
      else if (t.length >= 5 && w.length >= 5 && near(t, w)) b = Math.max(b, 1.5);
    }
    return b;
  }

  FAQ.forEach(function (f) {
    f.qStems = stems(f.question);
    f.aStems = stems(f.answer);
    f.tagPhrases = f.tags.map(function (t) { return words(t).filter(function (w) { return !STOP[w]; }).map(stem); });
    f.tagStems = [].concat.apply([], f.tagPhrases);
    f.qJoined = f.qStems.join(' ');
    f.aJoined = f.aStems.join(' ');
  });

  function search(query) {
    var raw = words(query);
    var tokens = raw.filter(function (w) { return !STOP[w]; }).map(stem);
    if (!tokens.length) tokens = raw.map(stem);
    tokens = tokens.filter(function (t, i) { return tokens.indexOf(t) === i; });
    if (!tokens.length) return { hits: [], partial: false };
    var phrase = tokens.join(' ');
    var scored = [];
    FAQ.forEach(function (f) {
      var matched = 0, score = 0;
      tokens.forEach(function (t) {
        var q = best(t, f.qStems), g = best(t, f.tagStems), a = best(t, f.aStems) * 0.5;
        var top = Math.max(q, g, a);
        if (top > 0) {
          matched++;
          score += top + ((q > 0) + (g > 0) + (a > 0) - 1) * 0.5;
        }
      });
      if (!matched) return;
      if (tokens.length > 1) {
        if (f.qJoined.indexOf(phrase) !== -1) score += 4;
        if (f.aJoined.indexOf(phrase) !== -1) score += 1.5;
      }
      f.tagPhrases.forEach(function (tp) {
        var tj = tp.join(' ');
        if (tj === phrase) score += 6;
        else if (tokens.length > 1 && tj.indexOf(phrase) !== -1) score += 3;
      });
      scored.push({ f: f, matched: matched, score: score });
    });
    var byScore = function (x, y) { return y.score - x.score || x.f.id - y.f.id; };
    var full = scored.filter(function (s) { return s.matched === tokens.length; }).sort(byScore);
    var partial = false;
    // Partial matches (at least half the typed words) are the fallback when
    // nothing matches every word, and trail a short list of full matches.
    if (tokens.length > 1 && full.length < 3) {
      var need = Math.ceil(tokens.length / 2);
      var rest = scored.filter(function (s) { return s.matched < tokens.length && s.matched >= need; }).sort(byScore);
      var top = full.length ? full[0].score : (rest.length ? rest[0].score : 0);
      rest = rest.filter(function (s) { return s.score >= top * 0.5; });
      partial = !full.length && rest.length > 0;
      full = full.concat(rest.slice(0, 5 - full.length));
    }
    return { hits: full.map(function (s) { return s.f; }), partial: partial };
  }

  function setStatus(html) { statusEl.innerHTML = html; statusEl.style.display = html ? '' : 'none'; }
  function setNote(html) { noteEl.innerHTML = html; noteEl.style.display = html ? '' : 'none'; }

  function showCards(list) {
    list.forEach(function (f) {
      var card = document.createElement('div');
      card.className = 'hs-result';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'hs-result-q';
      btn.setAttribute('aria-expanded', 'false');
      var icon = document.createElement('span');
      icon.className = 'hs-chevron';
      icon.setAttribute('aria-hidden', 'true');
      var q = document.createElement('span');
      q.className = 'hs-result-qtext';
      q.textContent = f.question;
      btn.appendChild(icon);
      btn.appendChild(q);
      var ans = document.createElement('div');
      ans.className = 'hs-result-answer';
      ans.hidden = true;
      ans.innerHTML = f.answerHtml;
      btn.addEventListener('click', function () {
        var open = ans.hidden;
        ans.hidden = !open;
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        card.classList.toggle('open', open);
        fitLanding();
      });
      card.appendChild(btn);
      card.appendChild(ans);
      resultsEl.appendChild(card);
    });
    fitLanding();
  }

  // On the landing page the panel is one scroll-snap screen, so only as many
  // rows as fit show (an opened row stays). Elsewhere all show.
  var landingPanel = document.querySelector('.landing-anchor--faq');
  function fitLanding() {
    if (!landingPanel) return;
    var cards = Array.prototype.slice.call(resultsEl.children);
    cards.forEach(function (c) { c.style.display = ''; });
    function overflows() {
      return landingPanel.getBoundingClientRect().height > window.innerHeight + 1;
    }
    for (var i = cards.length - 1; i > 0 && overflows(); i--) {
      if (!cards[i].classList.contains('open')) cards[i].style.display = 'none';
    }
  }
  window.addEventListener('resize', fitLanding);

  function render() {
    var q = input.value.trim();
    clearBtn.style.display = q ? '' : 'none';
    resultsEl.textContent = '';
    setStatus('');
    if (!q) {
      setNote('Search above via keyword or question, or visit our ' + DISCORD + '.');
      showCards(FAQ.filter(function (f) { return f.category === 'Getting Started'; }));
      return;
    }
    var res = search(q);
    if (!res.hits.length) {
      setNote('No matching results. Try again, or ask in our ' + DISCORD + '.');
      return;
    }
    setNote('Can\'t find an answer? Try asking in our ' + DISCORD + '.');
    setStatus(res.partial ? 'No exact matches \u2014 here are the closest ones.' : '');
    showCards(res.hits);
  }

  // Results appear after the visitor pauses typing; until then old results
  // are cleared and "Loading..." shows. Enter, Escape, Clear and an emptied
  // box skip the wait.
  var TYPING_PAUSE_MS = 1000;
  var typingTimer = null;
  function renderNow() {
    clearTimeout(typingTimer);
    typingTimer = null;
    render();
  }
  input.addEventListener('input', function () {
    clearTimeout(typingTimer);
    if (!input.value.trim()) { renderNow(); return; }
    resultsEl.textContent = '';
    setNote('');
    clearBtn.style.display = '';
    setStatus('Loading...');
    typingTimer = setTimeout(renderNow, TYPING_PAUSE_MS);
  });
  var HS_TOUCH = !!(window.matchMedia && window.matchMedia('(hover: none)').matches);
  if (HS_TOUCH) input.setAttribute('enterkeyhint', 'search');
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { input.value = ''; renderNow(); }
    else if (e.key === 'Enter') {
      renderNow();
      if (HS_TOUCH) input.blur();
    }
  });
  clearBtn.addEventListener('click', function () {
    input.value = ''; renderNow();
    if (HS_TOUCH) input.blur(); else input.focus();
  });
  render();
})();
