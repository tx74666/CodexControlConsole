from __future__ import annotations

import re
import threading
import time


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class ConsoleWindowSessionService:
    def __init__(
        self,
        shutdown_callback,
        *,
        close_delay_seconds=4.0,
        stale_after_seconds=180.0,
        sweep_interval_seconds=30.0,
    ):
        if not callable(shutdown_callback):
            raise ValueError("A shutdown callback is required")
        self.shutdown_callback = shutdown_callback
        self.close_delay_seconds = max(0.01, float(close_delay_seconds))
        self.stale_after_seconds = max(self.close_delay_seconds, float(stale_after_seconds))
        self.sweep_interval_seconds = max(0.01, float(sweep_interval_seconds))
        self._sessions = {}
        self._lock = threading.RLock()
        self._shutdown_timer = None
        self._sweep_timer = None
        self._ever_opened = False
        self._stopped = False
        self._shutdown_requested = False

    def _new_timer(self, delay, callback):
        timer = threading.Timer(delay, callback)
        timer.daemon = True
        return timer

    def _cancel_shutdown_locked(self):
        timer = self._shutdown_timer
        self._shutdown_timer = None
        if timer:
            timer.cancel()

    def _schedule_sweep_locked(self):
        if self._stopped or self._sweep_timer or not self._sessions:
            return
        self._sweep_timer = self._new_timer(self.sweep_interval_seconds, self._sweep)
        self._sweep_timer.start()

    def _schedule_shutdown_locked(self):
        if self._stopped or self._shutdown_requested or self._sessions or self._shutdown_timer:
            return
        self._shutdown_timer = self._new_timer(self.close_delay_seconds, self._shutdown_if_idle)
        self._shutdown_timer.start()

    def _prune_stale_locked(self, now):
        cutoff = now - self.stale_after_seconds
        stale = [session_id for session_id, last_seen in self._sessions.items() if last_seen < cutoff]
        for session_id in stale:
            self._sessions.pop(session_id, None)

    def _sweep(self):
        with self._lock:
            self._sweep_timer = None
            if self._stopped:
                return
            self._prune_stale_locked(time.monotonic())
            if self._sessions:
                self._schedule_sweep_locked()
            elif self._ever_opened:
                self._schedule_shutdown_locked()

    def _shutdown_if_idle(self):
        with self._lock:
            self._shutdown_timer = None
            if self._stopped:
                return
            self._prune_stale_locked(time.monotonic())
            if self._sessions:
                self._schedule_sweep_locked()
                return
            self._shutdown_requested = True
        self.shutdown_callback()

    def update(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Window session payload must be an object")
        action = str(payload.get("action") or "").strip().lower()
        session_id = str(payload.get("sessionId") or "").strip()
        if action not in {"open", "heartbeat", "close"}:
            raise ValueError("Window session action is invalid")
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("Window session ID is invalid")

        with self._lock:
            if self._stopped:
                return {"ok": True, "activeSessions": 0, "stopped": True}
            self._prune_stale_locked(time.monotonic())
            if action in {"open", "heartbeat"}:
                self._sessions[session_id] = time.monotonic()
                self._ever_opened = True
                self._shutdown_requested = False
                self._cancel_shutdown_locked()
                self._schedule_sweep_locked()
            else:
                self._sessions.pop(session_id, None)
                if self._ever_opened and not self._sessions:
                    self._schedule_shutdown_locked()
            return {
                "ok": True,
                "activeSessions": len(self._sessions),
                "closing": bool(self._shutdown_timer),
            }

    def stop(self):
        with self._lock:
            self._stopped = True
            self._sessions.clear()
            self._cancel_shutdown_locked()
            timer = self._sweep_timer
            self._sweep_timer = None
            if timer:
                timer.cancel()
