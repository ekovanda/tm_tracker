/**
 * Trackmania Bingo Tracker - Frontend Application Logic & Timer Engine
 *
 * Provides:
 * 1. Client-side timer countdown engine with local timestamp calculation
 * 2. API synchronization with FastAPI backend (/api/*)
 * 3. Interactive controls: auth unlock gate, pre-session setup, board shuffle,
 *    game lifecycle (start, stop, reset, poll), and player timer actions.
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.TMBingo = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // --- Formatting Helpers ---

  /**
   * Format seconds to MM:SS or HH:MM:SS.
   * @param {number} totalSeconds
   * @returns {string}
   */
  function formatTime(totalSeconds) {
    const s = Math.max(0, Math.floor(totalSeconds));
    const hours = Math.floor(s / 3600);
    const minutes = Math.floor((s % 3600) / 60);
    const seconds = s % 60;
    const pad = (n) => String(n).padStart(2, '0');

    if (hours > 0) {
      return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    }
    return `${pad(minutes)}:${pad(seconds)}`;
  }

  /**
   * Format milliseconds to MM:SS.mmm track time.
   * @param {number|null} ms
   * @returns {string}
   */
  function formatTrackTime(ms) {
    if (ms === null || ms === undefined || isNaN(ms)) return '--:--.---';
    const totalMs = Math.max(0, Math.floor(ms));
    const minutes = Math.floor(totalMs / 60000);
    const seconds = Math.floor((totalMs % 60000) / 1000);
    const millis = totalMs % 1000;
    const pad = (n, len = 2) => String(n).padStart(len, '0');
    return `${pad(minutes)}:${pad(seconds)}.${pad(millis, 3)}`;
  }

  // --- Timer Calculation Logic ---

  /**
   * Compute the client-side calculated state for a player timer.
   * @param {object} timer
   * @param {number} [nowMs]
   * @returns {object} { status, remainingSeconds, progressFraction, formatted }
   */
  function calculateTimerState(timer, nowMs) {
    const currentNow = typeof nowMs === 'number' ? nowMs : Date.now();
    const duration = (timer && typeof timer.duration_seconds === 'number') ? timer.duration_seconds : 600;
    const rawStatus = (timer && timer.status) ? timer.status.toLowerCase() : 'ready';

    if (rawStatus === 'active' && timer.started_at) {
      const startTime = new Date(timer.started_at).getTime();
      const elapsedSeconds = Math.max(0, (currentNow - startTime) / 1000);
      const remainingSeconds = Math.max(0, duration - elapsedSeconds);

      if (remainingSeconds <= 0) {
        return {
          status: 'expired',
          remainingSeconds: 0,
          progressFraction: 0,
          formatted: '00:00',
        };
      }

      const fraction = duration > 0 ? Math.max(0, Math.min(1, remainingSeconds / duration)) : 0;
      return {
        status: 'active',
        remainingSeconds: remainingSeconds,
        progressFraction: fraction,
        formatted: formatTime(remainingSeconds),
      };
    }

    if (rawStatus === 'stopped') {
      const remainingSeconds = Math.max(0, (typeof timer.remaining_seconds === 'number') ? timer.remaining_seconds : 0);
      const fraction = duration > 0 ? Math.max(0, Math.min(1, remainingSeconds / duration)) : 0;
      return {
        status: 'stopped',
        remainingSeconds: remainingSeconds,
        progressFraction: fraction,
        formatted: formatTime(remainingSeconds),
      };
    }

    if (rawStatus === 'expired') {
      return {
        status: 'expired',
        remainingSeconds: 0,
        progressFraction: 0,
        formatted: '00:00',
      };
    }

    return {
      status: 'ready',
      remainingSeconds: duration,
      progressFraction: 1,
      formatted: formatTime(duration),
    };
  }

  /**
   * Compute client-side countdowns for the overall session and grace period.
   * @param {object} session
   * @param {number} [nowMs]
   * @returns {object} { gameRemaining, formattedGame, graceActive, graceRemaining, formattedGrace }
   */
  function calculateSessionTime(session, nowMs) {
    const currentNow = typeof nowMs === 'number' ? nowMs : Date.now();

    if (!session || !session.started_at) {
      return {
        gameRemaining: 0,
        formattedGame: '00:00:00',
        graceActive: false,
        graceRemaining: 0,
        formattedGrace: '00:00',
      };
    }

    const startTime = new Date(session.started_at).getTime();
    const elapsedSeconds = Math.max(0, (currentNow - startTime) / 1000);

    const gameDuration = (session.settings && session.settings.game_duration_seconds)
      || session.game_duration_seconds
      || 18000;

    const graceDuration = (session.settings && session.settings.grace_period_seconds)
      || session.grace_period_seconds
      || 1800;

    const gameRemaining = Math.max(0, gameDuration - elapsedSeconds);
    const graceRemaining = Math.max(0, graceDuration - elapsedSeconds);
    const graceActive = graceRemaining > 0;

    return {
      gameRemaining: gameRemaining,
      formattedGame: formatTime(gameRemaining),
      graceActive: graceActive,
      graceRemaining: graceRemaining,
      formattedGrace: formatTime(graceRemaining),
    };
  }

  // --- Timer Engine ---

  class TimerEngine {
    constructor() {
      this.timers = new Map();
      this.session = null;
      this.intervalId = null;
      this.tickListeners = new Set();
    }

    setTimers(timersList) {
      if (!Array.isArray(timersList)) return;
      for (const t of timersList) {
        if (t && t.player && t.player.account_id) {
          this.timers.set(t.player.account_id, t);
        }
      }
      this.render();
    }

    setTimer(accountId, timerData) {
      if (!accountId || !timerData) return;
      this.timers.set(accountId, timerData);
      this.render();
    }

    setSession(session) {
      this.session = session;
      this.render();
    }

    onTick(listener) {
      if (typeof listener === 'function') {
        this.tickListeners.add(listener);
      }
    }

    start() {
      if (this.intervalId !== null) return;
      this.render();
      this.intervalId = setInterval(() => {
        this.render();
      }, 250);
    }

    stop() {
      if (this.intervalId !== null) {
        clearInterval(this.intervalId);
        this.intervalId = null;
      }
    }

    render() {
      const nowMs = Date.now();

      for (const [accountId, rawTimer] of this.timers.entries()) {
        const computed = calculateTimerState(rawTimer, nowMs);
        this.updatePlayerCard(accountId, computed);
      }

      if (this.session && this.session.status === 'active') {
        const computedSession = calculateSessionTime(this.session, nowMs);
        this.updateSessionBar(computedSession);
      }

      for (const listener of this.tickListeners) {
        try {
          listener(nowMs);
        } catch (err) {
          console.error('Error in tick listener:', err);
        }
      }
    }

    updatePlayerCard(accountId, computed) {
      if (typeof document === 'undefined') return;

      const card = document.querySelector(`.player-card[data-player-id="${accountId}"]`);
      if (!card) return;

      const display = card.querySelector('.timer-display');
      if (display) {
        display.textContent = computed.formatted;
      }

      const progressFill = card.querySelector('.progress-bar-fill');
      if (progressFill) {
        const pct = (computed.progressFraction * 100).toFixed(1);
        progressFill.style.width = `${pct}%`;
      }

      const progressContainer = card.querySelector('.progress-bar-container');
      if (progressContainer) {
        const pct = Math.round(computed.progressFraction * 100);
        progressContainer.setAttribute('aria-valuenow', String(pct));
      }

      const badge = card.querySelector('.timer-badge');
      if (badge) {
        badge.className = `timer-badge timer-${computed.status}`;
        badge.textContent = computed.status.charAt(0).toUpperCase() + computed.status.slice(1);
      }
    }

    updateSessionBar(computed) {
      if (typeof document === 'undefined') return;

      const gameClock = document.getElementById('game-remaining-clock');
      if (gameClock) {
        gameClock.textContent = computed.formattedGame;
      }

      const graceBadge = document.getElementById('grace-status-badge');
      if (graceBadge) {
        if (computed.graceActive) {
          graceBadge.className = 'badge badge-warning';
          graceBadge.textContent = `Active (${computed.formattedGrace})`;
        } else {
          graceBadge.className = 'badge badge-subtle';
          graceBadge.textContent = 'Ended';
        }
      }
    }
  }

  // --- API Client ---

  async function apiRequest(url, options = {}) {
    const token = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('tm_bingo_token') : null;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (response.status === 401) {
        if (typeof sessionStorage !== 'undefined') {
          sessionStorage.removeItem('tm_bingo_token');
          sessionStorage.removeItem('tm_bingo_auth');
        }
        if (typeof window !== 'undefined' && window.appController) {
          window.appController.lockApp();
        }
      }

      if (!response.ok) {
        let errMessage = `Request failed: ${response.statusText}`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) {
            errMessage = errData.detail;
          }
        } catch (_) {}
        const error = new Error(errMessage);
        error.status = response.status;
        throw error;
      }

      return await response.json();
    } catch (err) {
      console.warn(`API call error on ${url}:`, err.message);
      throw err;
    }
  }

  // --- Application State Controller ---

  class AppController {
    constructor(timerEngine) {
      this.timerEngine = timerEngine;
      this.isAuthenticated = false;
      this.campaigns = [];
      this.gameState = null;
      this.pollInterval = null;
    }

    init() {
      this.bindEvents();

      // Check existing session auth and token
      const savedAuth = sessionStorage.getItem('tm_bingo_auth');
      const savedToken = sessionStorage.getItem('tm_bingo_token');
      if (savedAuth === 'true' && savedToken) {
        this.unlockApp();
      } else {
        this.showAuthGate();
      }
    }

    showAuthGate() {
      this.isAuthenticated = false;
      const gate = document.getElementById('password-gate');
      if (gate) gate.removeAttribute('hidden');
    }

    unlockApp() {
      this.isAuthenticated = true;
      sessionStorage.setItem('tm_bingo_auth', 'true');
      const gate = document.getElementById('password-gate');
      if (gate) gate.setAttribute('hidden', 'true');

      this.timerEngine.start();
      this.loadCampaigns();
      this.syncState();
      this.startPolling();
    }

    lockApp() {
      this.isAuthenticated = false;
      sessionStorage.removeItem('tm_bingo_auth');
      sessionStorage.removeItem('tm_bingo_token');
      this.stopPolling();
      this.showAuthGate();
    }

    startPolling() {
      this.stopPolling();
      this.pollInterval = setInterval(() => {
        if (this.isAuthenticated) {
          this.syncState();
        }
      }, 5000);
    }

    stopPolling() {
      if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
      }
    }

    showNotification(message, type = 'info') {
      const banner = document.getElementById('notification-banner');
      if (!banner) return;
      banner.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
      setTimeout(() => {
        banner.innerHTML = '';
      }, 5000);
    }

    async loadCampaigns() {
      try {
        const campaigns = await apiRequest('/api/campaigns');
        this.campaigns = campaigns || [];
        this.renderCampaignSelect();
      } catch (err) {
        if (err.status === 401) {
          this.lockApp();
        } else {
          this.showNotification(`Failed to load campaigns: ${err.message}`, 'danger');
        }
      }
    }

    renderCampaignSelect() {
      const select = document.getElementById('campaign-select');
      if (!select) return;

      const currentValue = select.value;
      select.innerHTML = '';

      if (this.campaigns.length === 0) {
        select.innerHTML = '<option value="" disabled selected>No campaigns available</option>';
        return;
      }

      for (const camp of this.campaigns) {
        const opt = document.createElement('option');
        opt.value = camp.campaign_id;
        opt.textContent = camp.name;
        select.appendChild(opt);
      }

      if (currentValue && this.campaigns.some((c) => c.campaign_id === currentValue)) {
        select.value = currentValue;
      } else if (this.gameState && this.gameState.pending && this.gameState.pending.campaign_id) {
        select.value = this.gameState.pending.campaign_id;
      }
    }

    async syncState() {
      try {
        const [game, timers] = await Promise.all([
          apiRequest('/api/game'),
          apiRequest('/api/timers'),
        ]);

        this.gameState = game;
        this.timerEngine.setTimers(timers);

        if (game.session) {
          this.timerEngine.setSession(game.session);
        }

        this.renderGameState();
      } catch (err) {
        if (err.status === 401) {
          this.lockApp();
        }
      }
    }

    renderGameState() {
      if (!this.gameState) return;

      const preSessionPanel = document.getElementById('pre-session-panel');
      const activeBar = document.getElementById('active-session-bar');
      const isPending = this.gameState.status === 'pending';

      if (isPending) {
        if (preSessionPanel) preSessionPanel.removeAttribute('hidden');
        if (activeBar) activeBar.setAttribute('hidden', 'true');

        // Sync pending settings to inputs if not currently focused
        const pending = this.gameState.pending;
        if (pending && pending.settings) {
          const seedInput = document.getElementById('board-seed-input');
          if (seedInput && document.activeElement !== seedInput) {
            seedInput.value = pending.settings.board_seed;
          }

          const campSelect = document.getElementById('campaign-select');
          if (campSelect && pending.campaign_id && document.activeElement !== campSelect) {
            campSelect.value = pending.campaign_id;
          }

          const gameDurationInput = document.getElementById('game-duration-input');
          if (
            gameDurationInput &&
            pending.settings.game_duration_seconds != null &&
            document.activeElement !== gameDurationInput
          ) {
            const hours = pending.settings.game_duration_seconds / 3600;
            gameDurationInput.value = Number.isInteger(hours) ? hours : hours.toFixed(1);
          }

          const graceInput = document.getElementById('grace-period-input');
          if (
            graceInput &&
            pending.settings.grace_period_seconds != null &&
            document.activeElement !== graceInput
          ) {
            graceInput.value = Math.round(pending.settings.grace_period_seconds / 60);
          }

          const timerInput = document.getElementById('timer-duration-input');
          if (
            timerInput &&
            pending.settings.manual_timer_duration_seconds != null &&
            document.activeElement !== timerInput
          ) {
            timerInput.value = Math.round(pending.settings.manual_timer_duration_seconds / 60);
          }
        }

        if (pending && pending.board) {
          this.renderBoard(pending.board);
        }
      } else {
        if (preSessionPanel) preSessionPanel.setAttribute('hidden', 'true');
        if (activeBar) activeBar.removeAttribute('hidden');

        const session = this.gameState.session;
        if (session) {
          const statusBadge = document.getElementById('game-status-badge');
          if (statusBadge) {
            statusBadge.textContent = session.status.toUpperCase();
            statusBadge.className = `badge badge-${session.status === 'active' ? 'success' : 'warning'}`;
          }

          const campName = document.getElementById('active-campaign-name');
          if (campName) {
            const camp = this.campaigns.find((c) => c.campaign_id === session.campaign_id);
            campName.textContent = camp ? camp.name : session.campaign_id;
          }

          this.renderBoard(session.board);
          this.renderMedals(session.rank_points, session.medal_counts);
          this.renderRecords(session.records);
        }
      }
    }

    renderBoard(board) {
      if (!Array.isArray(board) || board.length === 0) return;

      const cells = document.querySelectorAll('.bingo-grid .track-cell');
      let flatIndex = 0;

      for (let r = 0; r < board.length; r++) {
        for (let c = 0; c < board[r].length; c++) {
          const cellData = board[r][c];
          const cellEl = cells[flatIndex];
          flatIndex++;
          if (!cellEl || !cellData) continue;

          // Series class
          const series = cellData.track ? cellData.track.series : 0;
          cellEl.className = `track-cell series-${series}`;

          // Header
          const seriesBadge = cellEl.querySelector('.series-badge');
          if (seriesBadge && cellData.track) {
            seriesBadge.textContent = String(cellData.track.track_number).padStart(2, '0');
          }

          const trackName = cellEl.querySelector('.track-name');
          if (trackName && cellData.track) {
            trackName.textContent = cellData.track.name || `Track ${cellData.track.track_number}`;
          }

          // Owner & Time
          const ownerPill = cellEl.querySelector('.owner-pill');
          if (ownerPill) {
            if (cellData.owner && cellData.owner.alias) {
              const aliasLower = cellData.owner.alias.toLowerCase();
              ownerPill.className = `owner-pill owner-${aliasLower}`;
              ownerPill.textContent = cellData.owner.alias;
            } else {
              ownerPill.className = 'owner-pill owner-neutral';
              ownerPill.textContent = 'Unclaimed';
            }
          }

          const cellTime = cellEl.querySelector('.cell-time');
          if (cellTime) {
            cellTime.textContent = formatTrackTime(cellData.winning_time);
          }

          const cellMargin = cellEl.querySelector('.cell-margin');
          if (cellMargin) {
            cellMargin.textContent = cellData.margin !== null ? `+${(cellData.margin / 1000).toFixed(3)}s` : '+0.000s';
          }

          // Top 3 Rankings
          const rankRows = cellEl.querySelectorAll('.cell-rankings .ranking-row');
          const rankings = cellData.rankings || [];
          for (let i = 0; i < 3; i++) {
            const row = rankRows[i];
            if (!row) continue;
            const rData = rankings[i];
            const nameEl = row.querySelector('.rank-name');
            const timeEl = row.querySelector('.rank-time');
            if (rData) {
              if (nameEl) nameEl.textContent = rData.player ? rData.player.alias : '—';
              if (timeEl) timeEl.textContent = formatTrackTime(rData.time);
            } else {
              if (nameEl) nameEl.textContent = '—';
              if (timeEl) timeEl.textContent = '--:--.---';
            }
          }
        }
      }
    }

    renderMedals(rankPoints, medalCounts) {
      if (!medalCounts) return;

      for (const [accountId, counts] of Object.entries(medalCounts)) {
        const card = document.querySelector(`.player-card[data-player-id="${accountId}"]`);
        if (!card) continue;

        const goldEl = card.querySelector('.gold-count');
        const silverEl = card.querySelector('.silver-count');
        const bronzeEl = card.querySelector('.bronze-count');
        const ptsEl = card.querySelector('.points-count');

        if (goldEl) goldEl.textContent = counts.gold ?? 0;
        if (silverEl) silverEl.textContent = counts.silver ?? 0;
        if (bronzeEl) bronzeEl.textContent = counts.bronze ?? 0;

        if (ptsEl && rankPoints && rankPoints[accountId] !== undefined) {
          ptsEl.textContent = rankPoints[accountId];
        }
      }
    }

    renderRecords(records) {
      const feed = document.getElementById('record-feed');
      const countBadge = document.getElementById('record-count');
      if (!feed) return;

      if (!Array.isArray(records) || records.length === 0) {
        feed.innerHTML = `
          <div class="record-empty">
            <span class="empty-icon"><span class="emoji">⏱️</span></span>
            <p>No personal bests recorded yet.</p>
            <p class="empty-hint">New records will appear here live during the challenge.</p>
          </div>
        `;
        if (countBadge) countBadge.textContent = '0 Records';
        return;
      }

      if (countBadge) {
        countBadge.textContent = `${records.length} Record${records.length === 1 ? '' : 's'}`;
      }

      // Sort newest first
      const sorted = [...records].reverse();
      feed.innerHTML = '';

      for (const r of sorted) {
        const item = document.createElement('div');
        item.className = 'record-item';

        const observedTime = r.observed_at ? new Date(r.observed_at).toLocaleTimeString() : '';
        const playerAlias = r.player ? r.player.alias : 'Unknown';
        const playerLower = playerAlias.toLowerCase();
        const trackNum = r.track ? String(r.track.track_number).padStart(2, '0') : '--';
        const formattedTime = formatTrackTime(r.time);

        item.innerHTML = `
          <div class="record-item-meta">
            <span class="record-time-badge font-mono">${observedTime}</span>
            <span class="badge badge-subtle">Trk ${trackNum}</span>
            <span class="record-player-badge record-player-${playerLower}">${playerAlias}</span>
          </div>
          <div class="record-score font-mono">${formattedTime}</div>
        `;
        feed.appendChild(item);
      }
    }

    async handleConfigChange() {
      if (!this.isAuthenticated || !this.gameState || this.gameState.status !== 'pending') return;

      const campSelect = document.getElementById('campaign-select');
      const seedInput = document.getElementById('board-seed-input');
      const gameDurationInput = document.getElementById('game-duration-input');
      const graceInput = document.getElementById('grace-period-input');
      const timerInput = document.getElementById('timer-duration-input');

      const payload = {};
      if (campSelect && campSelect.value) {
        payload.campaign_id = campSelect.value;
      }
      if (seedInput && seedInput.value) {
        const parsed = parseInt(seedInput.value, 10);
        if (!isNaN(parsed)) payload.board_seed = parsed;
      }
      if (gameDurationInput && gameDurationInput.value) {
        const parsed = parseFloat(gameDurationInput.value);
        if (!isNaN(parsed) && parsed > 0) payload.game_duration_seconds = Math.round(parsed * 3600);
      }
      if (graceInput && graceInput.value) {
        const parsed = parseInt(graceInput.value, 10);
        if (!isNaN(parsed) && parsed >= 0) payload.grace_period_seconds = Math.round(parsed * 60);
      }
      if (timerInput && timerInput.value) {
        const parsed = parseInt(timerInput.value, 10);
        if (!isNaN(parsed) && parsed > 0) payload.manual_timer_duration_seconds = Math.round(parsed * 60);
      }

      if (Object.keys(payload).length === 0) return;

      try {
        const updated = await apiRequest('/api/game/configure', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        if (updated) {
          this.gameState = updated;
          this.renderGameState();
        }
      } catch (err) {
        if (err.status === 401) {
          this.lockApp();
        } else {
          this.showNotification(`Configuration sync failed: ${err.message}`, 'warning');
        }
      }
    }

    bindEvents() {
      // 1. Password submit
      const passwordForm = document.getElementById('password-form');
      if (passwordForm) {
        passwordForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          const passInput = document.getElementById('password-input');
          const errDiv = document.getElementById('password-error');
          if (!passInput) return;

          try {
            const authData = await apiRequest('/api/auth/verify', {
              method: 'POST',
              body: JSON.stringify({ password: passInput.value }),
            });
            if (authData && authData.token) {
              sessionStorage.setItem('tm_bingo_token', authData.token);
            }
            if (errDiv) errDiv.setAttribute('hidden', 'true');
            this.unlockApp();
          } catch (err) {
            if (errDiv) {
              errDiv.textContent = err.message || 'Incorrect password.';
              errDiv.removeAttribute('hidden');
            }
          }
        });
      }

      // 2. Lock button
      const lockBtn = document.getElementById('btn-lock');
      if (lockBtn) {
        lockBtn.addEventListener('click', () => this.lockApp());
      }

      // Setup inputs live configuration sync
      const configInputs = [
        'campaign-select',
        'board-seed-input',
        'game-duration-input',
        'grace-period-input',
        'timer-duration-input',
      ];
      for (const id of configInputs) {
        const el = document.getElementById(id);
        if (el) {
          el.addEventListener('change', () => this.handleConfigChange());
        }
      }

      // 3. Shuffle Board
      const shuffleBtn = document.getElementById('btn-shuffle');
      if (shuffleBtn) {
        shuffleBtn.addEventListener('click', async () => {
          const newSeed = Math.floor(Math.random() * 900000) + 100000;
          const seedInput = document.getElementById('board-seed-input');
          if (seedInput) seedInput.value = newSeed;

          try {
            const updated = await apiRequest('/api/game/configure', {
              method: 'POST',
              body: JSON.stringify({ board_seed: newSeed }),
            });
            if (updated) {
              this.gameState = updated;
              this.renderGameState();
            } else {
              this.syncState();
            }
          } catch (err) {
            this.showNotification(`Shuffle failed: ${err.message}`, 'danger');
          }
        });
      }

      // 4. Start Game
      const startBtn = document.getElementById('btn-start-game');
      if (startBtn) {
        startBtn.addEventListener('click', async () => {
          const campSelect = document.getElementById('campaign-select');
          const seedInput = document.getElementById('board-seed-input');
          const gameDurationInput = document.getElementById('game-duration-input');
          const graceInput = document.getElementById('grace-period-input');
          const timerInput = document.getElementById('timer-duration-input');

          const campaignId = campSelect ? campSelect.value : '';
          if (!campaignId) {
            this.showNotification('Please select a campaign before starting.', 'warning');
            return;
          }

          const payload = {
            campaign_id: campaignId,
            board_seed: seedInput ? parseInt(seedInput.value, 10) : 12345,
            game_duration_seconds: gameDurationInput ? Math.round(parseFloat(gameDurationInput.value) * 3600) : 18000,
            grace_period_seconds: graceInput ? Math.round(parseInt(graceInput.value, 10) * 60) : 1800,
            manual_timer_duration_seconds: timerInput ? Math.round(parseInt(timerInput.value, 10) * 60) : 600,
          };

          try {
            startBtn.disabled = true;
            await apiRequest('/api/game/start', {
              method: 'POST',
              body: JSON.stringify(payload),
            });
            this.showNotification('Bingo game started!', 'success');
            await this.syncState();
          } catch (err) {
            this.showNotification(`Failed to start game: ${err.message}`, 'danger');
          } finally {
            startBtn.disabled = false;
          }
        });
      }

      // 5. Stop Game
      const stopBtn = document.getElementById('btn-stop-game');
      if (stopBtn) {
        stopBtn.addEventListener('click', async () => {
          if (!confirm('Are you sure you want to stop the game session?')) return;
          try {
            await apiRequest('/api/game/stop', { method: 'POST' });
            this.showNotification('Game stopped.', 'warning');
            this.syncState();
          } catch (err) {
            this.showNotification(`Failed to stop game: ${err.message}`, 'danger');
          }
        });
      }

      // 6. Reset Game
      const resetBtn = document.getElementById('btn-reset-game');
      if (resetBtn) {
        resetBtn.addEventListener('click', async () => {
          if (!confirm('Are you sure you want to reset the session back to pending configuration?')) return;
          try {
            await apiRequest('/api/game/reset', { method: 'POST' });
            this.showNotification('Game reset to pending setup.', 'info');
            this.syncState();
          } catch (err) {
            this.showNotification(`Failed to reset game: ${err.message}`, 'danger');
          }
        });
      }

      // 7. Refresh Leaderboard
      const refreshBtn = document.getElementById('btn-refresh');
      if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
          try {
            refreshBtn.disabled = true;
            await apiRequest('/api/game/poll', { method: 'POST' });
            this.showNotification('Leaderboards refreshed.', 'success');
            await this.syncState();
          } catch (err) {
            this.showNotification(`Refresh failed: ${err.message}`, 'danger');
          } finally {
            refreshBtn.disabled = false;
          }
        });
      }

      // 8. Timer Action Buttons
      const timersContainer = document.getElementById('player-timers');
      if (timersContainer) {
        timersContainer.addEventListener('click', async (e) => {
          const btn = e.target.closest('button[data-action]');
          if (!btn) return;

          const accountId = btn.getAttribute('data-account');
          const action = btn.getAttribute('data-action');
          if (!accountId || !action) return;

          try {
            btn.disabled = true;
            const updatedTimer = await apiRequest(`/api/timers/${accountId}/action`, {
              method: 'POST',
              body: JSON.stringify({ action }),
            });
            this.timerEngine.setTimer(accountId, updatedTimer);
          } catch (err) {
            this.showNotification(`Timer ${action} failed: ${err.message}`, 'danger');
          } finally {
            btn.disabled = false;
          }
        });
      }
    }
  }

  // Create singleton engine and controller
  const engine = new TimerEngine();
  const controller = new AppController(engine);
  if (typeof window !== 'undefined') {
    window.appController = controller;
  }

  // Auto-init on DOMContentLoaded in browser
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => controller.init());
    } else {
      controller.init();
    }
  }

  return {
    formatTime,
    formatTrackTime,
    calculateTimerState,
    calculateSessionTime,
    TimerEngine,
    AppController,
    engine,
    controller,
  };
});
