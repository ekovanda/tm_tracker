/**
 * Trackmania Bingo Tracker - Client-Side Timer & Countdown Engine
 *
 * Decouples the 1-second UI countdown tick from server network traffic.
 * Calculates remaining durations locally using `Date.now()` vs server timestamps (`started_at`).
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.TMBingo = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  /**
   * Format a duration in seconds to MM:SS or HH:MM:SS.
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
   * Compute the client-side calculated state for a player timer.
   * @param {object} timer - { account_id, status, started_at, duration_seconds, remaining_seconds }
   * @param {number} [nowMs] - Current timestamp in ms (defaults to Date.now())
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

    // Default: 'ready'
    return {
      status: 'ready',
      remainingSeconds: duration,
      progressFraction: 1,
      formatted: formatTime(duration),
    };
  }

  /**
   * Compute client-side countdowns for the overall session and grace period.
   * @param {object} session - Session state object with started_at, settings, or duration fields
   * @param {number} [nowMs] - Current timestamp in ms
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

  /**
   * TimerEngine manages local timer state and drives the DOM tick updates.
   */
  class TimerEngine {
    constructor() {
      this.timers = new Map(); // account_id -> timerData
      this.session = null;
      this.intervalId = null;
      this.tickListeners = new Set();
    }

    /**
     * Set or update timer data from server API response.
     * @param {Array<object>} timersList
     */
    setTimers(timersList) {
      if (!Array.isArray(timersList)) return;
      for (const t of timersList) {
        if (t && t.player && t.player.account_id) {
          this.timers.set(t.player.account_id, t);
        }
      }
      this.render();
    }

    /**
     * Update a single player's timer data.
     * @param {string} accountId
     * @param {object} timerData
     */
    setTimer(accountId, timerData) {
      if (!accountId || !timerData) return;
      this.timers.set(accountId, timerData);
      this.render();
    }

    /**
     * Set or update active session data from server API response.
     * @param {object} session
     */
    setSession(session) {
      this.session = session;
      this.render();
    }

    /**
     * Register a callback listener invoked on each tick.
     * @param {Function} listener
     */
    onTick(listener) {
      if (typeof listener === 'function') {
        this.tickListeners.add(listener);
      }
    }

    /**
     * Start the client-side tick loop (ticks every 250ms for responsiveness).
     */
    start() {
      if (this.intervalId !== null) return;
      this.render();
      this.intervalId = setInterval(() => {
        this.render();
      }, 250);
    }

    /**
     * Stop the tick loop.
     */
    stop() {
      if (this.intervalId !== null) {
        clearInterval(this.intervalId);
        this.intervalId = null;
      }
    }

    /**
     * Calculate all current states and update the DOM elements.
     */
    render() {
      const nowMs = Date.now();

      // Render player timers
      for (const [accountId, rawTimer] of this.timers.entries()) {
        const computed = calculateTimerState(rawTimer, nowMs);
        this.updatePlayerCard(accountId, computed);
      }

      // Render session & grace period countdowns
      if (this.session && this.session.status === 'active') {
        const computedSession = calculateSessionTime(this.session, nowMs);
        this.updateSessionBar(computedSession);
      }

      // Notify external tick listeners
      for (const listener of this.tickListeners) {
        try {
          listener(nowMs);
        } catch (err) {
          console.error('Error in tick listener:', err);
        }
      }
    }

    /**
     * Update DOM for a single player timer card.
     * @param {string} accountId
     * @param {object} computed - Result from calculateTimerState
     */
    updatePlayerCard(accountId, computed) {
      if (typeof document === 'undefined') return;

      const card = document.querySelector(`.player-card[data-player-id="${accountId}"]`);
      if (!card) return;

      // Timer display text (MM:SS)
      const display = card.querySelector('.timer-display');
      if (display) {
        display.textContent = computed.formatted;
      }

      // Progress bar fill
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

      // Status pill badge
      const badge = card.querySelector('.timer-badge');
      if (badge) {
        badge.className = `timer-badge timer-${computed.status}`;
        badge.textContent = computed.status.charAt(0).toUpperCase() + computed.status.slice(1);
      }
    }

    /**
     * Update DOM for the session status bar.
     * @param {object} computed - Result from calculateSessionTime
     */
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

  // Create shared default engine instance
  const engine = new TimerEngine();

  // Auto-start in browser environment once DOM is ready
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => engine.start());
    } else {
      engine.start();
    }
  }

  return {
    formatTime,
    calculateTimerState,
    calculateSessionTime,
    TimerEngine,
    engine,
  };
});
