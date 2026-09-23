/**
 * Unit tests for client-side timer countdown logic in static/app.js
 */

const assert = require('assert');
const path = require('path');

const {
  formatTime,
  formatTrackTime,
  calculateTimerState,
  calculateSessionTime,
  TimerEngine,
  AppController,
} = require(path.join(__dirname, '..', 'static', 'app.js'));

console.log('Running client-side timer countdown tests...');

// 1. Test formatTime
assert.strictEqual(formatTime(0), '00:00');
assert.strictEqual(formatTime(5), '00:05');
assert.strictEqual(formatTime(59), '00:59');
assert.strictEqual(formatTime(60), '01:00');
assert.strictEqual(formatTime(600), '10:00');
assert.strictEqual(formatTime(654), '10:54');
assert.strictEqual(formatTime(3599), '59:59');
assert.strictEqual(formatTime(3600), '01:00:00');
assert.strictEqual(formatTime(18000), '05:00:00');
console.log('✓ formatTime tests passed');

// 1b. Test formatTrackTime
assert.strictEqual(formatTrackTime(null), '--:--.---');
assert.strictEqual(formatTrackTime(undefined), '--:--.---');
assert.strictEqual(formatTrackTime(0), '00:00.000');
assert.strictEqual(formatTrackTime(42315), '00:42.315');
assert.strictEqual(formatTrackTime(65432), '01:05.432');
console.log('✓ formatTrackTime tests passed');

// 2. Test calculateTimerState - Ready State
const readyTimer = {
  account_id: 'player-1',
  status: 'ready',
  started_at: null,
  duration_seconds: 600,
  remaining_seconds: 600,
};
const readyResult = calculateTimerState(readyTimer);
assert.strictEqual(readyResult.status, 'ready');
assert.strictEqual(readyResult.remainingSeconds, 600);
assert.strictEqual(readyResult.progressFraction, 1);
assert.strictEqual(readyResult.formatted, '10:00');
console.log('✓ calculateTimerState (ready) passed');

// 3. Test calculateTimerState - Active State (in progress)
const baseTime = 1774342800000; // fixed timestamp
const startTimeIso = new Date(baseTime).toISOString();
const activeTimer = {
  account_id: 'player-1',
  status: 'active',
  started_at: startTimeIso,
  duration_seconds: 600,
  remaining_seconds: 600,
};

// 100 seconds later
const timeAt100s = baseTime + 100 * 1000;
const activeResult1 = calculateTimerState(activeTimer, timeAt100s);
assert.strictEqual(activeResult1.status, 'active');
assert.strictEqual(Math.round(activeResult1.remainingSeconds), 500);
assert.strictEqual(activeResult1.formatted, '08:20');
assert(Math.abs(activeResult1.progressFraction - 500 / 600) < 0.001);
console.log('✓ calculateTimerState (active 100s) passed');

// 599 seconds later (1 second left)
const timeAt599s = baseTime + 599 * 1000;
const activeResult2 = calculateTimerState(activeTimer, timeAt599s);
assert.strictEqual(activeResult2.status, 'active');
assert.strictEqual(Math.round(activeResult2.remainingSeconds), 1);
assert.strictEqual(activeResult2.formatted, '00:01');
console.log('✓ calculateTimerState (active 599s) passed');

// 601 seconds later (expired)
const timeAt601s = baseTime + 601 * 1000;
const activeResult3 = calculateTimerState(activeTimer, timeAt601s);
assert.strictEqual(activeResult3.status, 'expired');
assert.strictEqual(activeResult3.remainingSeconds, 0);
assert.strictEqual(activeResult3.progressFraction, 0);
assert.strictEqual(activeResult3.formatted, '00:00');
console.log('✓ calculateTimerState (active -> expired) passed');

// 4. Test calculateTimerState - Stopped State
const stoppedTimer = {
  account_id: 'player-1',
  status: 'stopped',
  started_at: startTimeIso,
  duration_seconds: 600,
  remaining_seconds: 245.5,
};
const stoppedResult = calculateTimerState(stoppedTimer);
assert.strictEqual(stoppedResult.status, 'stopped');
assert.strictEqual(stoppedResult.remainingSeconds, 245.5);
assert.strictEqual(stoppedResult.formatted, '04:05');
assert(Math.abs(stoppedResult.progressFraction - 245.5 / 600) < 0.001);
console.log('✓ calculateTimerState (stopped) passed');

// 5. Test calculateTimerState - Expired State
const expiredTimer = {
  account_id: 'player-1',
  status: 'expired',
  started_at: startTimeIso,
  duration_seconds: 600,
  remaining_seconds: 0,
};
const expiredResult = calculateTimerState(expiredTimer);
assert.strictEqual(expiredResult.status, 'expired');
assert.strictEqual(expiredResult.remainingSeconds, 0);
assert.strictEqual(expiredResult.formatted, '00:00');
console.log('✓ calculateTimerState (expired) passed');

// 6. Test calculateSessionTime
const sessionStartTime = 1774342800000;
const activeSession = {
  started_at: new Date(sessionStartTime).toISOString(),
  settings: {
    game_duration_seconds: 18000, // 5 hours
    grace_period_seconds: 1800,   // 30 minutes
  },
};

// 10 minutes into game (grace period still active)
const at10Minutes = sessionStartTime + 10 * 60 * 1000;
const sessionResult1 = calculateSessionTime(activeSession, at10Minutes);
assert.strictEqual(sessionResult1.graceActive, true);
assert.strictEqual(Math.round(sessionResult1.graceRemaining), 20 * 60);
assert.strictEqual(sessionResult1.formattedGrace, '20:00');
assert.strictEqual(Math.round(sessionResult1.gameRemaining), 17400); // 4h 50m
assert.strictEqual(sessionResult1.formattedGame, '04:50:00');
console.log('✓ calculateSessionTime (within grace) passed');

// 45 minutes into game (grace period ended)
const at45Minutes = sessionStartTime + 45 * 60 * 1000;
const sessionResult2 = calculateSessionTime(activeSession, at45Minutes);
assert.strictEqual(sessionResult2.graceActive, false);
assert.strictEqual(sessionResult2.graceRemaining, 0);
assert.strictEqual(sessionResult2.formattedGrace, '00:00');
assert.strictEqual(Math.round(sessionResult2.gameRemaining), 18000 - 45 * 60);
assert.strictEqual(sessionResult2.formattedGame, '04:15:00');
console.log('✓ calculateSessionTime (past grace) passed');

// 7. Test TimerEngine basic operations in headless environment
const engine = new TimerEngine();
engine.setTimers([
  { player: { account_id: 'p1' }, status: 'ready', duration_seconds: 600 },
  { player: { account_id: 'p2' }, status: 'ready', duration_seconds: 600 },
]);
assert.strictEqual(engine.timers.size, 2);

let tickFired = false;
engine.onTick(() => { tickFired = true; });
engine.render();
assert.strictEqual(tickFired, true);
console.log('✓ TimerEngine tests passed');

console.log('All client-side timer countdown tests passed successfully!');
