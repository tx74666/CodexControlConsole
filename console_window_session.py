from __future__ import annotations

import re
import threading


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class ConsoleWindowSessionService:
    def __init__(
        self,
        shutdown_callback,
        *,
        close_delay_seconds=4.0,
    ):
        if not callable(shutdown_callback):
            raise ValueError("A shutdown callback is required")
        self.shutdown_callback = shutdown_callback
        self.close_delay_seconds = max(0.01, float(close_delay_seconds))
        self._sessions = set()
        self._lock = threading.RLock()
        self._shutdown_timer = None
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

    def _schedule_shutdown_locked(self):
        if self._stopped or self._shutdown_requested or self._sessions or self._shutdown_timer:
            return
        self._shutdown_timer = self._new_timer(self.close_delay_seconds, self._shutdown_if_idle)
        self._shutdown_timer.start()

    def _shutdown_if_idle(self):
        with self._lock:
            self._shutdown_timer = None
            if self._stopped:
                return
            if self._sessions:
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
            if action in {"open", "heartbeat"}:
                self._sessions.add(session_id)
                self._ever_opened = True
                self._shutdown_requested = False
                self._cancel_shutdown_locked()
            else:
                self._sessions.discard(session_id)
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
