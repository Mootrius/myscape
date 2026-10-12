(function () {
  // No tap tooltips on touch screens for the Account page; read by the
  // shared tooltip script in _shell.
  window.myscapeTouchTooltipFilter = function () { return false; };

  // Same trash icon as Goal Tracking's .gt-goal-delete (goalRowHtml); shared
  // by DEACTIVATE (Shared Links) and DELETE CHARACTER (Linked Accounts) via
  // trashDeleteBtnHtml.
  const TRASH_ICON_SVG = '<svg class="trash-delete-icon" width="15" height="15" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M2 4H14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M6 4V2.5C6 2.22386 6.22386 2 6.5 2H9.5C9.77614 2 10 2.22386 10 2.5V4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M3.5 4L4.1 13.2C4.13 13.66 4.51 14 4.97 14H11.03C11.49 14 11.87 13.66 11.9 13.2L12.5 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6.5 6.5V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M9.5 6.5V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>';

  function trashDeleteBtnHtml(confirmLabel) {
    return TRASH_ICON_SVG + '<span class="trash-delete-confirm">' + confirmLabel + '</span>';
  }

  // First click arms the button (shows the confirm label); a second click
  // runs `onConfirm`. A click elsewhere disarms it via the shared
  // outside-click listener below, like Goal Tracking's delete button.
  function wireTrashDeleteBtn(btn, onConfirm) {
    btn.addEventListener('click', () => {
      if (btn.classList.contains('trash-delete-btn--confirm')) {
        onConfirm();
        return;
      }
      document.querySelectorAll('.trash-delete-btn--confirm').forEach((b) => {
        if (b !== btn) b.classList.remove('trash-delete-btn--confirm');
      });
      disarmDeleteAllLinksHeader();
      btn.classList.add('trash-delete-btn--confirm');
    });
  }

  // Resets the DELETION header to its resting label/color whenever a
  // different destructive confirm is armed, so only one confirm shows at a
  // time.
  function disarmDeleteAllLinksHeader() {
    const btn = document.getElementById('sharedLinksDeleteAllBtn');
    if (!btn) return;
    btn.classList.remove('shared-link-delete-all-header--confirm');
    btn.textContent = 'Deletion';
  }

  document.addEventListener('click', (e) => {
    if (e.target.closest('.trash-delete-btn')) return;
    document.querySelectorAll('.trash-delete-btn--confirm').forEach((b) => {
      b.classList.remove('trash-delete-btn--confirm');
    });
    if (!e.target.closest('.shared-link-delete-all-header')) {
      disarmDeleteAllLinksHeader();
    }
  });

  // Update Email / Update Password / Delete Account share one row
  // (.account-tab-row) with accordion behavior: at most one
  // .account-collapse-body is visible; clicking the open tab closes it.
  const accountTabs = [
    ['emailToggleBtn', 'emailBody'],
    ['passwordToggleBtn', 'passwordBody'],
    ['deleteToggleBtn', 'deleteBody'],
  ];
  accountTabs.forEach(([toggleId, bodyId]) => {
    const toggleBtn = document.getElementById(toggleId);
    const body = document.getElementById(bodyId);
    toggleBtn.addEventListener('click', () => {
      const wasOpen = !body.hidden;
      accountTabs.forEach(([otherToggleId, otherBodyId]) => {
        document.getElementById(otherBodyId).hidden = true;
        document.getElementById(otherToggleId).classList.remove('active');
      });
      if (!wasOpen) {
        body.hidden = false;
        toggleBtn.classList.add('active');
      }
    });
  });

  const emailForm = document.getElementById('emailForm');
  emailForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById('emailError');
    const successEl = document.getElementById('emailSuccess');
    errorEl.classList.remove('show');
    successEl.classList.remove('show');
    const newEmail = document.getElementById('newEmail').value;
    const currentPassword = document.getElementById('emailPassword').value;
    const submitBtn = emailForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    try {
      const res = await fetch('/api/auth/change-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_email: newEmail, current_password: currentPassword }),
      });
      if (res.ok) {
        successEl.textContent = 'Email updated -- check your new inbox for a fresh verification link.';
        successEl.classList.add('show');
        emailForm.reset();
        return;
      }
      const data = await res.json().catch(() => ({}));
      errorEl.textContent = describeError(data, 'Could not update your email.');
      errorEl.classList.add('show');
    } catch (err) {
      errorEl.textContent = 'Something went wrong. Please try again.';
      errorEl.classList.add('show');
    } finally {
      submitBtn.disabled = false;
    }
  });

  const passwordForm = document.getElementById('passwordForm');
  passwordForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById('passwordError');
    const successEl = document.getElementById('passwordSuccess');
    errorEl.classList.remove('show');
    successEl.classList.remove('show');
    const currentPassword = document.getElementById('currentPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmNewPassword = document.getElementById('confirmNewPassword').value;
    if (newPassword !== confirmNewPassword) {
      errorEl.textContent = 'New passwords do not match.';
      errorEl.classList.add('show');
      return;
    }
    const submitBtn = passwordForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (res.ok) {
        successEl.textContent = 'Password updated. Every other signed-in session has been logged out.';
        successEl.classList.add('show');
        passwordForm.reset();
        return;
      }
      const data = await res.json().catch(() => ({}));
      errorEl.textContent = describeError(data, 'Could not update your password.');
      errorEl.classList.add('show');
    } catch (err) {
      errorEl.textContent = 'Something went wrong. Please try again.';
      errorEl.classList.add('show');
    } finally {
      submitBtn.disabled = false;
    }
  });

  const deleteForm = document.getElementById('deleteForm');
  const deleteSubmitBtn = document.getElementById('deleteSubmitBtn');
  const deletePasswordInput = document.getElementById('deletePassword');

  // Editing the password disarms the confirm step so a stale "ARE YOU SURE?"
  // can't delete on the next click.
  deletePasswordInput.addEventListener('input', () => {
    if (deleteSubmitBtn.dataset.armed === 'true') {
      deleteSubmitBtn.dataset.armed = 'false';
      deleteSubmitBtn.textContent = 'DELETE ACCOUNT';
    }
  });

  deleteForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById('deleteError');
    errorEl.classList.remove('show');

    if (deleteSubmitBtn.dataset.armed !== 'true') {
      // First press only arms the confirm step (the password field is
      // required, so it can't be empty).
      deleteSubmitBtn.dataset.armed = 'true';
      deleteSubmitBtn.textContent = 'ARE YOU SURE?';
      return;
    }

    // Second press deletes. The server still checks the password
    // (/api/auth/delete-account).
    const currentPassword = deletePasswordInput.value;
    deleteSubmitBtn.disabled = true;
    try {
      const res = await fetch('/api/auth/delete-account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword }),
      });
      if (res.ok) {
        window.location.href = '/';
        return;
      }
      const data = await res.json().catch(() => ({}));
      errorEl.textContent = describeError(data, 'Could not delete your account.');
      errorEl.classList.add('show');
      // Back to the first step so a failed attempt doesn't leave it armed.
      deleteSubmitBtn.dataset.armed = 'false';
      deleteSubmitBtn.textContent = 'DELETE ACCOUNT';
    } catch (err) {
      errorEl.textContent = 'Something went wrong. Please try again.';
      errorEl.classList.add('show');
      deleteSubmitBtn.dataset.armed = 'false';
      deleteSubmitBtn.textContent = 'DELETE ACCOUNT';
    } finally {
      deleteSubmitBtn.disabled = false;
    }
  });

  // Linked Accounts list (step 7 of docs/multi-account-scoping.md): fetched
  // on load rather than server-rendered, as with other JS-populated lists,
  // since switch/remove/add change it. Pending friend-request counts per
  // character (GET /api/friends/notifications) drive the badge on each card.
  let friendNotif = { total: 0, byCharacter: {} };
  const gameAccountsList = document.getElementById('gameAccountsList');
  const gameAccountsError = document.getElementById('gameAccountsError');
  const addGameAccountBtn = document.getElementById('addGameAccountBtn');

  function renderGameAccountRow(gameAccount) {
    const row = document.createElement('div');
    row.className = 'game-account-row';

    const nameEl = document.createElement('span');
    nameEl.className = 'game-account-name' + (gameAccount.linked ? '' : ' game-account-name--unlinked');
    nameEl.textContent = gameAccount.linked ? gameAccount.runescape_name : 'Not yet linked';
    row.appendChild(nameEl);

    if (gameAccount.active) {
      const badge = document.createElement('span');
      badge.className = 'game-account-active-badge';
      badge.textContent = 'ACTIVE';
      nameEl.appendChild(badge);
    }

    // A friend request waiting on this character; SWITCH to it to see the
    // sender in the Friends section.
    const pendingFriendRequests = (friendNotif.byCharacter || {})[gameAccount.id] || 0;
    if (pendingFriendRequests > 0) {
      const friendBadge = document.createElement('span');
      friendBadge.className = 'friend-badge game-account-friend-badge';
      friendBadge.textContent = String(pendingFriendRequests);
      friendBadge.setAttribute(
        'data-tooltip',
        pendingFriendRequests === 1 ? 'New friend request' : pendingFriendRequests + ' new friend requests'
      );
      nameEl.appendChild(friendBadge);
    }

    const actions = document.createElement('div');
    actions.className = 'game-account-actions';

    if (!gameAccount.active) {
      const switchBtn = document.createElement('button');
      switchBtn.type = 'button';
      switchBtn.className = 'secondary';
      switchBtn.textContent = 'SWITCH';
      switchBtn.addEventListener('click', async () => {
        gameAccountsError.classList.remove('show');
        switchBtn.disabled = true;
        try {
          const res = await fetch(`/api/link/game-accounts/${gameAccount.id}/activate`, { method: 'POST' });
          if (res.ok) {
            await loadGameAccounts();
            return;
          }
          const data = await res.json().catch(() => ({}));
          gameAccountsError.textContent = describeError(data, 'Could not switch accounts.');
          gameAccountsError.classList.add('show');
        } catch (err) {
          gameAccountsError.textContent = 'Something went wrong. Please try again.';
          gameAccountsError.classList.add('show');
        } finally {
          switchBtn.disabled = false;
        }
      });
      actions.appendChild(switchBtn);
    }

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'trash-delete-btn';
    removeBtn.setAttribute('aria-label', 'Delete character');
    removeBtn.setAttribute('data-tooltip', 'Delete character');
    removeBtn.innerHTML = trashDeleteBtnHtml('ARE YOU SURE?');
    // Same two-step, click-away-to-cancel confirm as the Shared Links
    // DEACTIVATE button.
    wireTrashDeleteBtn(removeBtn, async () => {
      gameAccountsError.classList.remove('show');
      removeBtn.disabled = true;
      try {
        const res = await fetch(`/api/link/game-accounts/${gameAccount.id}`, { method: 'DELETE' });
        if (res.ok) {
          await loadGameAccounts();
          return;
        }
        const data = await res.json().catch(() => ({}));
        gameAccountsError.textContent = describeError(data, 'Could not remove this account.');
        gameAccountsError.classList.add('show');
        removeBtn.classList.remove('trash-delete-btn--confirm');
      } catch (err) {
        gameAccountsError.textContent = 'Something went wrong. Please try again.';
        gameAccountsError.classList.add('show');
        removeBtn.classList.remove('trash-delete-btn--confirm');
      } finally {
        removeBtn.disabled = false;
      }
    });
    actions.appendChild(removeBtn);

    row.appendChild(actions);
    return row;
  }

  async function loadGameAccounts() {
    gameAccountsError.classList.remove('show');
    try {
      const [res, notifRes] = await Promise.all([
        fetch('/api/link/game-accounts'),
        fetch('/api/friends/notifications').catch(() => null),
      ]);
      if (!res.ok) {
        gameAccountsError.textContent = 'Could not load your linked accounts.';
        gameAccountsError.classList.add('show');
        return;
      }
      if (notifRes && notifRes.ok) {
        friendNotif = await notifRes.json().catch(() => friendNotif);
      }
      const gameAccounts = await res.json();
      gameAccountsList.innerHTML = '';
      gameAccounts.forEach((gameAccount) => gameAccountsList.appendChild(renderGameAccountRow(gameAccount)));
      // The active character may have changed (SWITCH/delete), so Friends
      // follows it.
      loadFriends();
    } catch (err) {
      gameAccountsError.textContent = 'Something went wrong. Please try again.';
      gameAccountsError.classList.add('show');
    }
  }

  addGameAccountBtn.addEventListener('click', async () => {
    gameAccountsError.classList.remove('show');
    addGameAccountBtn.disabled = true;
    try {
      const res = await fetch('/api/link/game-accounts', { method: 'POST' });
      if (res.ok) {
        // Reload (not just a re-fetch): the new slot becomes the session's
        // active GameAccount and the header's link banner (_link_banner in
        // app/pages/) needs a fresh load to show its GENERATE CODE button.
        window.location.reload();
        return;
      }
      const data = await res.json().catch(() => ({}));
      gameAccountsError.textContent = describeError(data, 'Could not add another account.');
      gameAccountsError.classList.add('show');
    } catch (err) {
      gameAccountsError.textContent = 'Something went wrong. Please try again.';
      gameAccountsError.classList.add('show');
    } finally {
      addGameAccountBtn.disabled = false;
    }
  });

  // Shared Links: one row per valid share link from this Account's
  // GameAccounts (GET /api/account/shared-links; DELETE
  // /api/account/shared-links/<id>, see app/routers/account.py). Fetched on
  // load. sharedLinksData holds the last fetch; headers re-sort it in place,
  // like Storages Viewer's state.items/renderTable.
  const sharedLinksTableWrap = document.getElementById('sharedLinksTableWrap');
  const sharedLinksTableBody = document.getElementById('sharedLinksTableBody');
  const sharedLinksEmpty = document.getElementById('sharedLinksEmpty');
  const sharedLinksError = document.getElementById('sharedLinksError');
  let sharedLinksData = [];
  // Starts sorted by EXPIRATION, newest first, which matches the server
  // order (created_at desc); a sort stays active from then on.
  let sharedLinksSortKey = 'expiration';
  let sharedLinksSortDir = 'desc';

  // YYYY-MM-DD in the viewer's local timezone (server sends UTC), built from
  // getFullYear/getMonth/getDate so the format doesn't vary by locale. A
  // timestamp without a zone suffix is treated as UTC. Shared by the Shared
  // Links EXPIRATION column and the Friends SINCE column.
  function fmtLocalDate(iso) {
    if (!iso) return '—';
    const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso);
    const d = new Date(hasZone ? iso : iso + 'Z');
    if (isNaN(d.getTime())) return '—';
    const pad = (n) => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function fmtExpiration(iso) {
    return fmtLocalDate(iso);
  }

  // No 'code' case: the Code column isn't sortable (plain text).
  function sharedLinkSortValue(link, key) {
    if (key === 'character') return (link.character_name || 'Unknown character').toLowerCase();
    if (key === 'app') return link.content_type_label.toLowerCase();
    if (key === 'expiration') return new Date(link.expires_at).getTime();
    return '';
  }

  function renderSharedLinkRow(link) {
    const row = document.createElement('tr');

    const characterCell = document.createElement('td');
    characterCell.textContent = link.character_name || 'Unknown character';
    row.appendChild(characterCell);

    const appCell = document.createElement('td');
    appCell.textContent = link.content_type_label;
    row.appendChild(appCell);

    const codeCell = document.createElement('td');
    const codeBtn = document.createElement('button');
    codeBtn.type = 'button';
    codeBtn.className = 'shared-link-code-btn';
    codeBtn.textContent = link.code;
    codeBtn.setAttribute('data-tooltip', 'Click to copy');
    // Copies the full https://myscape.io/s/<code> URL (link.url, built
    // server-side, see SharedLinkSummary in app/schemas.py), not just the
    // code shown, then flashes "COPIED" like publicProfileLinkBtn and
    // lootShareLinkBtn. The button's fixed width (.shared-link-code-btn in
    // myscape.css) keeps it from resizing.
    codeBtn.addEventListener('click', async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(link.url);
        } else {
          const temp = document.createElement('textarea');
          temp.value = link.url;
          temp.style.position = 'fixed';
          temp.style.opacity = '0';
          document.body.appendChild(temp);
          temp.select();
          document.execCommand('copy');
          document.body.removeChild(temp);
        }
        codeBtn.textContent = 'COPIED';
        setTimeout(() => { codeBtn.textContent = link.code; }, 1200);
      } catch (err) {
        sharedLinksError.textContent = 'Could not copy the link -- please copy it manually.';
        sharedLinksError.classList.add('show');
      }
    });
    codeCell.appendChild(codeBtn);
    row.appendChild(codeCell);

    const expirationCell = document.createElement('td');
    expirationCell.textContent = fmtExpiration(link.expires_at);
    row.appendChild(expirationCell);

    const actionCell = document.createElement('td');
    const deactivateBtn = document.createElement('button');
    deactivateBtn.type = 'button';
    deactivateBtn.className = 'trash-delete-btn';
    deactivateBtn.setAttribute('aria-label', 'Delete');
    deactivateBtn.setAttribute('data-tooltip', 'Delete');
    deactivateBtn.innerHTML = trashDeleteBtnHtml('SURE?');
    // Same two-step, click-away-to-cancel confirm as DELETE CHARACTER below.
    wireTrashDeleteBtn(deactivateBtn, async () => {
      sharedLinksError.classList.remove('show');
      deactivateBtn.disabled = true;
      try {
        const res = await fetch(`/api/account/shared-links/${link.id}`, { method: 'DELETE' });
        if (res.ok) {
          await loadSharedLinks();
          return;
        }
        const data = await res.json().catch(() => ({}));
        sharedLinksError.textContent = describeError(data, 'Could not deactivate this link.');
        sharedLinksError.classList.add('show');
        deactivateBtn.classList.remove('trash-delete-btn--confirm');
      } catch (err) {
        sharedLinksError.textContent = 'Something went wrong. Please try again.';
        sharedLinksError.classList.add('show');
        deactivateBtn.classList.remove('trash-delete-btn--confirm');
      } finally {
        deactivateBtn.disabled = false;
      }
    });
    actionCell.appendChild(deactivateBtn);
    row.appendChild(actionCell);

    return row;
  }

  function renderSharedLinksTable() {
    sharedLinksTableBody.innerHTML = '';
    if (sharedLinksData.length === 0) {
      sharedLinksTableWrap.style.display = 'none';
      sharedLinksEmpty.style.display = '';
      return;
    }
    sharedLinksEmpty.style.display = 'none';
    sharedLinksTableWrap.style.display = '';
    let rows = sharedLinksData;
    if (sharedLinksSortKey) {
      rows = rows.slice().sort((a, b) => {
        const av = sharedLinkSortValue(a, sharedLinksSortKey);
        const bv = sharedLinkSortValue(b, sharedLinksSortKey);
        if (av < bv) return sharedLinksSortDir === 'asc' ? -1 : 1;
        if (av > bv) return sharedLinksSortDir === 'asc' ? 1 : -1;
        return 0;
      });
    }
    rows.forEach((link) => sharedLinksTableBody.appendChild(renderSharedLinkRow(link)));
  }

  // DELETION header: a destructive bulk action, not a sort column. First
  // click arms it (red, "SURE?"), a second revokes all of the account's
  // share links. Click-away cancel goes through disarmDeleteAllLinksHeader
  // in the shared document click listener above.
  const sharedLinksDeleteAllBtn = document.getElementById('sharedLinksDeleteAllBtn');
  if (sharedLinksDeleteAllBtn) {
    sharedLinksDeleteAllBtn.addEventListener('click', async () => {
      if (!sharedLinksDeleteAllBtn.classList.contains('shared-link-delete-all-header--confirm')) {
        document.querySelectorAll('.trash-delete-btn--confirm').forEach((b) => {
          b.classList.remove('trash-delete-btn--confirm');
        });
        sharedLinksDeleteAllBtn.classList.add('shared-link-delete-all-header--confirm');
        sharedLinksDeleteAllBtn.textContent = 'SURE?';
        return;
      }
      sharedLinksError.classList.remove('show');
      sharedLinksDeleteAllBtn.disabled = true;
      try {
        const res = await fetch('/api/account/shared-links', { method: 'DELETE' });
        if (res.ok) {
          await loadSharedLinks();
          return;
        }
        const data = await res.json().catch(() => ({}));
        sharedLinksError.textContent = describeError(data, 'Could not delete your shared links.');
        sharedLinksError.classList.add('show');
      } catch (err) {
        sharedLinksError.textContent = 'Something went wrong. Please try again.';
        sharedLinksError.classList.add('show');
      } finally {
        sharedLinksDeleteAllBtn.disabled = false;
        disarmDeleteAllLinksHeader();
      }
    });
  }

  // Header clicks sort the fetched data in place (no re-fetch); clicking the
  // active column flips direction, like Storages Viewer's .pm-sort-header.
  // Deletion isn't sortable (see sharedLinksDeleteAllBtn above).
  const sharedLinkSortHeaders = document.querySelectorAll('.shared-link-sort-header');
  function updateSharedLinkSortHeaders() {
    sharedLinkSortHeaders.forEach((btn) => {
      const key = btn.getAttribute('data-sort-key');
      const arrow = btn.querySelector('.shared-link-sort-arrow');
      if (key === sharedLinksSortKey) {
        btn.classList.add('active');
        arrow.textContent = sharedLinksSortDir === 'asc' ? ' ↑' : ' ↓';
      } else {
        btn.classList.remove('active');
        arrow.textContent = '';
      }
    });
  }
  // A sort is always active. A newly clicked column starts EXPIRATION newest
  // first and others ascending; clicking the active column flips it.
  sharedLinkSortHeaders.forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-sort-key');
      if (key !== sharedLinksSortKey) {
        sharedLinksSortKey = key;
        sharedLinksSortDir = key === 'expiration' ? 'desc' : 'asc';
      } else {
        sharedLinksSortDir = sharedLinksSortDir === 'asc' ? 'desc' : 'asc';
      }
      updateSharedLinkSortHeaders();
      renderSharedLinksTable();
    });
  });

  async function loadSharedLinks() {
    sharedLinksError.classList.remove('show');
    try {
      const res = await fetch('/api/account/shared-links');
      if (!res.ok) {
        sharedLinksError.textContent = 'Could not load your shared links.';
        sharedLinksError.classList.add('show');
        return;
      }
      sharedLinksData = await res.json();
      renderSharedLinksTable();
    } catch (err) {
      sharedLinksError.textContent = 'Something went wrong. Please try again.';
      sharedLinksError.classList.add('show');
    }
  }


  // Friends follows the session's ACTIVE character (GET /api/friends is
  // scoped server-side), so loadGameAccounts calls loadFriends at its end
  // (initial load, SWITCH, delete).
  const friendsHint = document.getElementById('friendsHint');
  const friendsBody = document.getElementById('friendsBody');
  const friendsCodeWrap = document.getElementById('friendsCodeWrap');
  const friendsCodeBtn = document.getElementById('friendsCodeBtn');
  const friendsAddForm = document.getElementById('friendsAddForm');
  const friendsAddInput = document.getElementById('friendsAddInput');
  const friendsAddBtn = document.getElementById('friendsAddBtn');
  const friendsError = document.getElementById('friendsError');
  const friendsSuccess = document.getElementById('friendsSuccess');
  const friendsRequests = document.getElementById('friendsRequests');
  const friendsRequestsList = document.getElementById('friendsRequestsList');
  const friendsTableWrap = document.getElementById('friendsTableWrap');
  const friendsTableBody = document.getElementById('friendsTableBody');
  const friendsEmpty = document.getElementById('friendsEmpty');
  let friendsCode = '';
  // Friends as last fetched (server order A-Z) plus the FRIEND/SINCE header
  // sort, same always-sorted cycle as Shared Links.
  let friendsData = [];
  // Starts sorted by SINCE, newest first.
  let friendsSortKey = 'since';
  let friendsSortDir = 'desc';

  // Circle with a dash (not a trash can); keeps .trash-delete-icon (same
  // shape as TRASH_ICON_SVG) to reuse the arm-then-confirm machinery.
  const REMOVE_FRIEND_ICON_SVG = '<svg class="trash-delete-icon" width="15" height="15" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><circle cx="8" cy="8" r="6.3" stroke="currentColor" stroke-width="1.4"/><path d="M5 8H11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';

  function clearFriendsMessages() {
    friendsError.classList.remove('show');
    friendsSuccess.classList.remove('show');
  }
  function showFriendsError(message) {
    friendsSuccess.classList.remove('show');
    friendsError.textContent = message;
    friendsError.classList.add('show');
  }
  function showFriendsSuccess(message) {
    friendsError.classList.remove('show');
    friendsSuccess.textContent = message;
    friendsSuccess.classList.add('show');
  }
  function refreshHeaderFriendBadge() {
    if (window.myscapePollFriendNotifications) window.myscapePollFriendNotifications();
  }

  async function copyFriendText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const temp = document.createElement('textarea');
      temp.value = text;
      temp.style.position = 'fixed';
      temp.style.opacity = '0';
      document.body.appendChild(temp);
      temp.select();
      document.execCommand('copy');
      document.body.removeChild(temp);
    }
  }

  friendsCodeBtn.addEventListener('click', async () => {
    try {
      await copyFriendText(friendsCode);
      friendsCodeBtn.textContent = 'COPIED';
      setTimeout(() => { friendsCodeBtn.textContent = friendsCode; }, 1200);
    } catch (err) {
      showFriendsError('Could not copy your code -- please copy it manually.');
    }
  });

  function renderFriendRequestRow(request) {
    const row = document.createElement('div');
    row.className = 'friend-request-row';

    const nameEl = document.createElement('span');
    nameEl.className = 'friend-request-name';
    nameEl.textContent = request.name;
    row.appendChild(nameEl);

    const actions = document.createElement('div');
    actions.className = 'friend-request-actions';

    async function respond(method, url, failMessage, btn) {
      clearFriendsMessages();
      btn.disabled = true;
      try {
        const res = await fetch(url, { method: method });
        if (res.ok) {
          await loadFriends();
          refreshHeaderFriendBadge();
          return;
        }
        const data = await res.json().catch(() => ({}));
        showFriendsError(describeError(data, failMessage));
      } catch (err) {
        showFriendsError('Something went wrong. Please try again.');
      } finally {
        btn.disabled = false;
      }
    }

    const acceptBtn = document.createElement('button');
    acceptBtn.type = 'button';
    acceptBtn.className = 'secondary';
    acceptBtn.textContent = 'ACCEPT';
    acceptBtn.addEventListener('click', () => {
      respond('POST', `/api/friends/requests/${request.id}/accept`, 'Could not accept this request.', acceptBtn);
    });
    actions.appendChild(acceptBtn);

    const declineBtn = document.createElement('button');
    declineBtn.type = 'button';
    declineBtn.className = 'secondary friend-decline-btn';
    declineBtn.textContent = 'DECLINE';
    declineBtn.addEventListener('click', () => {
      respond('DELETE', `/api/friends/requests/${request.id}`, 'Could not decline this request.', declineBtn);
    });
    actions.appendChild(declineBtn);

    row.appendChild(actions);
    return row;
  }

  function renderFriendRow(friend) {
    const row = document.createElement('tr');

    const nameCell = document.createElement('td');
    if (friend.code) {
      const link = document.createElement('a');
      link.className = 'friend-name-link';
      link.href = '/c/' + encodeURIComponent(friend.code);
      link.textContent = friend.name;
      link.setAttribute('data-tooltip', 'Visit profile');
      nameCell.appendChild(link);
    } else {
      nameCell.textContent = friend.name;
    }
    row.appendChild(nameCell);

    const sinceCell = document.createElement('td');
    sinceCell.textContent = fmtLocalDate(friend.since);
    row.appendChild(sinceCell);

    const removeCell = document.createElement('td');
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'trash-delete-btn friend-remove-btn';
    removeBtn.setAttribute('aria-label', 'Remove friend');
    removeBtn.setAttribute('data-tooltip', 'Remove friend');
    removeBtn.innerHTML = REMOVE_FRIEND_ICON_SVG + '<span class="trash-delete-confirm">SURE?</span>';
    wireTrashDeleteBtn(removeBtn, async () => {
      clearFriendsMessages();
      removeBtn.disabled = true;
      try {
        const res = await fetch(`/api/friends/${friend.id}`, { method: 'DELETE' });
        if (res.ok) {
          await loadFriends();
          return;
        }
        const data = await res.json().catch(() => ({}));
        showFriendsError(describeError(data, 'Could not remove this friend.'));
        removeBtn.classList.remove('trash-delete-btn--confirm');
      } catch (err) {
        showFriendsError('Something went wrong. Please try again.');
        removeBtn.classList.remove('trash-delete-btn--confirm');
      } finally {
        removeBtn.disabled = false;
      }
    });
    removeCell.appendChild(removeBtn);
    row.appendChild(removeCell);

    return row;
  }

  function renderFriendsTable() {
    friendsTableBody.innerHTML = '';
    if (friendsData.length === 0) {
      friendsTableWrap.style.display = 'none';
      friendsEmpty.style.display = '';
      return;
    }
    friendsEmpty.style.display = 'none';
    friendsTableWrap.style.display = '';
    let rows = friendsData;
    if (friendsSortKey) {
      rows = rows.slice().sort((a, b) => {
        const av = friendsSortKey === 'since' ? (a.since || '') : a.name.toLowerCase();
        const bv = friendsSortKey === 'since' ? (b.since || '') : b.name.toLowerCase();
        if (av < bv) return friendsSortDir === 'asc' ? -1 : 1;
        if (av > bv) return friendsSortDir === 'asc' ? 1 : -1;
        return 0;
      });
    }
    rows.forEach((friend) => friendsTableBody.appendChild(renderFriendRow(friend)));
  }

  const friendSortHeaders = document.querySelectorAll('.friend-sort-header');
  function updateFriendSortHeaders() {
    friendSortHeaders.forEach((btn) => {
      const arrow = btn.querySelector('.friend-sort-arrow');
      if (btn.getAttribute('data-friend-sort-key') === friendsSortKey) {
        btn.classList.add('active');
        arrow.textContent = friendsSortDir === 'asc' ? ' ↑' : ' ↓';
      } else {
        btn.classList.remove('active');
        arrow.textContent = '';
      }
    });
  }
  friendSortHeaders.forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-friend-sort-key');
      // Same always-sorted behavior as Shared Links: SINCE starts newest
      // first, FRIEND A-Z; the active column flips.
      if (key !== friendsSortKey) {
        friendsSortKey = key;
        friendsSortDir = key === 'since' ? 'desc' : 'asc';
      } else {
        friendsSortDir = friendsSortDir === 'asc' ? 'desc' : 'asc';
      }
      updateFriendSortHeaders();
      renderFriendsTable();
    });
  });

  // Show the default sort in the headers immediately.
  updateFriendSortHeaders();

  function showFriendsHint(message) {
    friendsHint.textContent = message;
    friendsHint.hidden = false;
    friendsBody.hidden = true;
    friendsCodeWrap.hidden = true;
  }

  async function loadFriends() {
    clearFriendsMessages();
    try {
      const res = await fetch('/api/friends');
      if (res.status === 403) {
        showFriendsHint('Verify your email to use friends.');
        return;
      }
      if (res.status === 409) {
        showFriendsHint('Add a character to use friends.');
        return;
      }
      if (!res.ok) {
        showFriendsError('Could not load your friends.');
        return;
      }
      const data = await res.json();
      if (data.linked === false) {
        showFriendsHint('Link this character to use friends.');
        return;
      }
      friendsHint.hidden = true;
      friendsBody.hidden = false;
      friendsCode = data.code || '';
      friendsCodeBtn.textContent = friendsCode;
      friendsCodeWrap.hidden = !friendsCode;

      friendsRequestsList.innerHTML = '';
      data.incoming.forEach((request) => friendsRequestsList.appendChild(renderFriendRequestRow(request)));
      friendsRequests.hidden = data.incoming.length === 0;

      friendsData = data.friends;
      renderFriendsTable();
    } catch (err) {
      showFriendsError('Something went wrong. Please try again.');
    }
  }

  friendsAddForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearFriendsMessages();
    const code = friendsAddInput.value.trim();
    if (!code) return;
    friendsAddBtn.disabled = true;
    try {
      const res = await fetch('/api/friends/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        friendsAddInput.value = '';
        showFriendsSuccess(
          data.status === 'accepted'
            ? `You and ${data.name} are now friends.`
            : 'If there is a character with that code, a friend request has been sent.'
        );
        if (data.status === 'accepted') {
          await loadFriends();
          showFriendsSuccess(`You and ${data.name} are now friends.`);
          refreshHeaderFriendBadge();
        }
        return;
      }
      showFriendsError(describeError(data, 'Could not send that request.'));
    } catch (err) {
      showFriendsError('Something went wrong. Please try again.');
    } finally {
      friendsAddBtn.disabled = false;
    }
  });

  // The header poll (see _shell) broadcasts each result. When per-character
  // counts change, rebuild the card badges and the Friends section
  // (loadGameAccounts reloads it).
  window.addEventListener('myscape:friend-notifications', (e) => {
    const next = e.detail || { total: 0, byCharacter: {} };
    const changed = JSON.stringify(friendNotif.byCharacter) !== JSON.stringify(next.byCharacter);
    friendNotif = next;
    if (changed) loadGameAccounts();
  });

  // The friend code field only takes focus on a click or tab into it; any
  // other focus (browser, restored page, stray label click) is bounced off.
  let friendsInputIntent = false;
  document.addEventListener('pointerdown', (e) => {
    friendsInputIntent = e.target === friendsAddInput;
  }, true);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') friendsInputIntent = true;
  }, true);
  friendsAddInput.addEventListener('focus', () => {
    if (!friendsInputIntent) friendsAddInput.blur();
  });
  friendsAddInput.addEventListener('blur', () => { friendsInputIntent = false; });
  if (document.activeElement === friendsAddInput) friendsAddInput.blur();

  // Show the default sort in the headers immediately.
  updateSharedLinkSortHeaders();

  loadGameAccounts();
  loadSharedLinks();
})();
