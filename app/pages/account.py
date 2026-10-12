"""The Account page."""
from html import escape

from app.pages.asset_loader import read_asset
from app.pages.player import PlayerView
from app.pages.shell import _shell


def render_account(player: PlayerView) -> str:
    """The header's Account link (see _nav_sides): log out, change email, change
    password, delete account (/api/auth/change-email, /change-password,
    /delete-account in app/routers/auth.py, which stay reachable
    pre-verification). `player` is not Optional since account_page in
    app/main.py redirects logged-out visitors to /login.
    """
    current_email = escape(player.email or "")
    body = f"""
    <div class="auth-shell account-shell">
      <div class="auth-card">
        <h2>ACCOUNT</h2>
        <p class="account-email">{current_email}</p>
        <button class="account-logout-link" id="logoutBtn" type="button">LOG OUT</button>

        <div class="account-section">
          <div class="auth-error" id="gameAccountsError"></div>
          <div class="game-accounts-list" id="gameAccountsList"></div>
          <button class="secondary" id="addGameAccountBtn" type="button">+ ADD CHARACTER</button>
        </div>

        <div class="account-section" id="friendsSection">
          <p class="account-section-title account-section-title--center">FRIENDS LIST</p>
          <p class="shared-links-empty" id="friendsHint" hidden></p>
          <div id="friendsBody">
            <form class="friends-add-form" id="friendsAddForm" autocomplete="off">
              <div class="friends-code-wrap" id="friendsCodeWrap" hidden>
                <span class="friends-code-label">My code</span>
                <button type="button" class="shared-link-code-btn" id="friendsCodeBtn" data-tooltip="Click to copy"></button>
                <span class="friends-add-divider" aria-hidden="true"></span>
              </div>
              <input type="text" id="friendsAddInput" maxlength="5" placeholder="Friend code" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Friend code" />
              <button class="secondary" type="submit" id="friendsAddBtn">SEND REQUEST</button>
            </form>
            <div class="auth-error" id="friendsError"></div>
            <div class="auth-success" id="friendsSuccess"></div>
            <div class="friends-requests" id="friendsRequests" hidden>
              <p class="friends-requests-title">Friend requests</p>
              <div id="friendsRequestsList"></div>
            </div>
            <div class="friends-table-wrap" id="friendsTableWrap" style="display:none;">
              <table class="friends-table">
                <thead>
                  <tr>
                    <th><button type="button" class="friend-sort-header" data-friend-sort-key="friend" data-tooltip="Sort by friend">Friend<span class="friend-sort-arrow"></span></button></th>
                    <th><button type="button" class="friend-sort-header" data-friend-sort-key="since" data-tooltip="Sort by date">Since<span class="friend-sort-arrow"></span></button></th>
                    <th>Removal</th>
                  </tr>
                </thead>
                <tbody id="friendsTableBody"></tbody>
              </table>
            </div>
            <p class="shared-links-empty" id="friendsEmpty" style="display:none;">No friends yet.</p>
          </div>
        </div>

        <div class="account-section">
          <p class="account-section-title account-section-title--center">SHARED LINKS</p>
          <div class="auth-error" id="sharedLinksError"></div>
          <div class="shared-links-table-wrap" id="sharedLinksTableWrap" style="display:none;">
            <table class="shared-links-table">
              <thead>
                <tr>
                  <th><button type="button" class="shared-link-sort-header" data-sort-key="character" data-tooltip="Sort by character">Character<span class="shared-link-sort-arrow"></span></button></th>
                  <th><button type="button" class="shared-link-sort-header" data-sort-key="app" data-tooltip="Sort by type">Type<span class="shared-link-sort-arrow"></span></button></th>
                  <th>Code</th>
                  <th><button type="button" class="shared-link-sort-header" data-sort-key="expiration" data-tooltip="Sort by expiration">Expiration<span class="shared-link-sort-arrow"></span></button></th>
                  <th><button type="button" class="shared-link-delete-all-header" id="sharedLinksDeleteAllBtn" data-tooltip="Delete all shared links">Deletion</button></th>
                </tr>
              </thead>
              <tbody id="sharedLinksTableBody"></tbody>
            </table>
          </div>
          <p class="shared-links-empty" id="sharedLinksEmpty" style="display:none;">No shared links yet.</p>
        </div>

        <div class="account-section">
          <div class="account-tab-row">
            <button class="secondary" type="button" id="emailToggleBtn">UPDATE EMAIL</button>
            <button class="secondary" type="button" id="passwordToggleBtn">UPDATE PASSWORD</button>
            <button class="danger" type="button" id="deleteToggleBtn">DELETE ACCOUNT</button>
          </div>

          <div class="account-collapse-body" id="emailBody" hidden>
            <div class="auth-error" id="emailError"></div>
            <div class="auth-success" id="emailSuccess"></div>
            <form id="emailForm">
              <div class="field">
                <label for="newEmail">New email</label>
                <input type="email" id="newEmail" name="newEmail" placeholder="you@example.com" required />
              </div>
              <div class="field">
                <label for="emailPassword">Password</label>
                <input type="password" id="emailPassword" name="emailPassword" placeholder="Your password" required />
              </div>
              <button class="primary" type="submit">UPDATE EMAIL</button>
            </form>
          </div>

          <div class="account-collapse-body" id="passwordBody" hidden>
            <div class="auth-error" id="passwordError"></div>
            <div class="auth-success" id="passwordSuccess"></div>
            <form id="passwordForm">
              <div class="field">
                <label for="currentPassword">Current password</label>
                <input type="password" id="currentPassword" name="currentPassword" placeholder="Current password" required />
              </div>
              <div class="field">
                <label for="newPassword">New password</label>
                <input type="password" id="newPassword" name="newPassword" placeholder="At least 8 characters" required minlength="8" />
              </div>
              <div class="field">
                <label for="confirmNewPassword">Confirm new password</label>
                <input type="password" id="confirmNewPassword" name="confirmNewPassword" placeholder="Re-enter your new password" required minlength="8" />
              </div>
              <button class="primary" type="submit">UPDATE PASSWORD</button>
            </form>
          </div>

          <div class="account-collapse-body" id="deleteBody" hidden>
            <p class="account-section-hint account-section-hint--center">This will <span class="account-hint-emphasis">PERMANENTLY</span> delete your myscape account and all data attached to it. You can create a new account afterward, but you <span class="account-hint-emphasis">CANNOT</span> undo this action.</p>
            <div class="auth-error" id="deleteError"></div>
            <form id="deleteForm">
              <div class="field">
                <label for="deletePassword">Password</label>
                <input type="password" id="deletePassword" name="deletePassword" placeholder="Your password" required />
              </div>
              <button class="danger danger--filled" type="submit" id="deleteSubmitBtn" data-armed="false">DELETE ACCOUNT</button>
            </form>
          </div>
        </div>
      </div>
    </div>
    """
    script = read_asset("account.js", indent=4)
    return _shell(title="Account — myscape", player=player, body=body, extra_script=script)
