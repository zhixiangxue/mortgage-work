"""Connector service: manages the linc IM gateway lifecycle.

Bridges mortgage-work's connector settings (settings.yaml ``connectors:``
section) with linc's gateway daemon.  The gateway runs in a background thread
with its own asyncio event loop; all message operations are submitted to that
loop from the bridge thread via ``asyncio.run_coroutine_threadsafe``.

Architecture::

    app.py (main thread)
      │
      ├── connector_service.start()
      │     └── daemon thread
      │           └── asyncio event loop
      │                 ├── LincGateway (WebSocket connections to IM platforms)
      │                 └── SqliteStore (.linc/linc.db)
      │
      └── Api bridge (worker threads)
            └── asyncio.run_coroutine_threadsafe(coro, gateway_loop)
                  └── Client SDK → SQLite WAL reads/writes

The gateway is only started when at least one connector is configured.
Stopping is idempotent — safe to call from atexit or on config changes.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any

from connector_settings import get_all_connector_configs
from model_settings import SETTINGS_DIR

log = logging.getLogger(__name__)

# Where linc stores its SQLite DB and lock files.
# Lives at ~/MortgageWork/.linc/ — alongside other app data, not nested
# under settings/ (which is reserved for YAML config files).
LINC_DATA_DIR = SETTINGS_DIR.parent / ".linc"

# Platforms we support (must match connector_settings.PLATFORM_ORDER)
SUPPORTED_PLATFORMS = ("slack", "feishu", "dingtalk", "wecom")

class ConnectorService:
    """Manages the linc gateway lifecycle and message operations."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._gateway: Any = None  # LincGateway instance
        self._client: Any = None   # linc.Client instance (for message ops)
        self._running = False
        self._error: str | None = None

    def start(self) -> bool:
        """Start the gateway if connectors are configured.

        Returns True if the gateway was started (or is already running).
        Returns False if no connectors are configured or startup failed.
        """
        if self._running:
            return True

        configs = get_all_connector_configs()
        if not configs:
            log.info("connector service: no connectors configured, skipping gateway")
            return False

        # Filter to supported platforms only
        adapters = {k: v for k, v in configs.items() if k in SUPPORTED_PLATFORMS}
        if not adapters:
            log.info("connector service: no supported platforms configured")
            return False

        log.info("connector service: starting gateway for %s", list(adapters))

        # Gateway runs in a daemon thread with its own event loop
        self._thread = threading.Thread(
            target=self._run_gateway,
            args=(adapters,),
            daemon=True,
            name="linc-gateway",
        )
        self._thread.start()

        # Wait briefly for the loop to be ready
        deadline = time.monotonic() + 10.0
        while self._loop is None and time.monotonic() < deadline:
            time.sleep(0.1)

        if self._loop is None:
            log.error("connector service: gateway thread failed to start")
            self._running = False
            return False

        self._running = True
        log.info("connector service: gateway started (data_dir=%s)", LINC_DATA_DIR)
        return True

    def stop(self) -> None:
        """Stop the gateway gracefully. Idempotent."""
        if not self._running and self._loop is None:
            return

        log.info("connector service: stopping gateway")
        self._running = False

        # Submit stop to the gateway's event loop
        if self._gateway is not None and self._loop is not None and self._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._gateway.stop(), self._loop
                )
                future.result(timeout=10.0)
            except Exception:
                log.exception("connector service: gateway stop failed")

        # Stop the event loop
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        self._loop = None
        self._gateway = None
        self._client = None
        log.info("connector service: gateway stopped")

    def restart(self) -> bool:
        """Stop and restart the gateway with current connector configs.

        Called after a connector is saved or removed so the new config takes
        effect without requiring an app restart.
        """
        log.info("connector service: restarting gateway")
        self.stop()
        return self.start()

    @property
    def is_running(self) -> bool:
        return self._running and self._loop is not None and self._loop.is_running()

    def get_status(self) -> dict:
        """Return gateway status and per-platform connection state."""
        status = {
            "running": self.is_running,
            "data_dir": str(LINC_DATA_DIR),
            "error": self._error,
            "platforms": {},
        }

        if self._gateway is not None:
            for name in SUPPORTED_PLATFORMS:
                adapter = self._gateway.adapters.get(name)
                status["platforms"][name] = {
                    "connected": adapter is not None,
                }
        else:
            for name in SUPPORTED_PLATFORMS:
                status["platforms"][name] = {"connected": False}

        return status

    # ── Message operations ───────────────────────────────────────────────────

    def get_history(
        self,
        platform: str,
        conv_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch chat history from linc's SQLite store.

        Returns a list of message dicts suitable for the frontend.
        """
        if not self.is_running:
            return []

        coro = self._fetch_history(platform, conv_id, limit)
        return self._submit(coro) or []

    def list_conversations(self, platform: str) -> list[dict]:
        """List known conversations for a platform, most recent first."""
        if not self.is_running:
            return []

        coro = self._list_conversations(platform)
        return self._submit(coro) or []

    def poll_unread(self) -> list[dict]:
        """Pull unread messages from all platforms.

        Returns a list of message dicts, each with a ``platform`` key.
        """
        if not self.is_running:
            return []

        coro = self._pull_unread()
        return self._submit(coro) or []

    def send_message(self, platform: str, conv_id: str, text: str) -> bool:
        """Enqueue an outbound message for the gateway to deliver.

        Returns True if the message was enqueued successfully.
        """
        if not self.is_running:
            return False

        coro = self._send(platform, conv_id, text)
        return self._submit(coro) or False

    # ── Internal: gateway thread ─────────────────────────────────────────────

    def _run_gateway(self, adapters: dict[str, dict[str, str]]) -> None:
        """Entry point for the gateway daemon thread."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._start_gateway(adapters))
            # Keep the loop running until stop() is called
            self._loop.run_forever()
        except Exception:
            log.exception("connector service: gateway thread crashed")
            self._error = "gateway thread crashed"
            self._running = False
        finally:
            # Clean up the loop
            try:
                # Cancel all remaining tasks
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.close()
            except Exception:
                pass

    async def _start_gateway(self, adapters: dict[str, dict[str, str]]) -> None:
        """Initialize and start the linc gateway."""
        try:
            from linc.core.config import LincConfig
            from linc.gateway import LincGateway

            # Ensure data directory exists
            LINC_DATA_DIR.mkdir(parents=True, exist_ok=True)

            # Build linc config programmatically
            config = LincConfig.model_validate({
                "data_dir": str(LINC_DATA_DIR),
                "poll_interval_ms": 100,
                "adapters": adapters,
            })

            # Create and start the gateway
            self._gateway = LincGateway(config)
            await self._gateway.start()

            log.info("connector service: linc gateway started with %d adapter(s)",
                     len(self._gateway.adapters))

        except ImportError as e:
            log.error("connector service: linc not installed: %s", e)
            self._error = f"linc not installed: {e}"
            raise
        except Exception as e:
            log.exception("connector service: gateway start failed")
            self._error = f"gateway start failed: {e}"
            raise

    # ── Internal: message operations ─────────────────────────────────────────

    async def _fetch_history(
        self,
        platform: str,
        conv_id: str | None,
        limit: int,
    ) -> list[dict]:
        """Async: fetch history from the gateway's store."""
        try:
            store = self._gateway.store
            if store is None:
                return []
            messages = await store.history(
                platform=platform,
                conv_id=conv_id,
                limit=limit,
            )
            return [self._format_message(m) for m in messages]
        except Exception:
            log.exception("connector service: history fetch failed")
            return []

    async def _list_conversations(self, platform: str) -> list[dict]:
        """Async: list conversations from the gateway's store."""
        try:
            store = self._gateway.store
            if store is None:
                return []
            return await store.list_conversations(platform=platform)
        except Exception:
            log.exception("connector service: list conversations failed")
            return []

    async def _pull_unread(self) -> list[dict]:
        """Async: pull unread messages from all platforms."""
        try:
            store = self._gateway.store
            if store is None:
                return []
            messages = await store.claim_unread()
            return [self._format_message(m) for m in messages]
        except Exception:
            log.exception("connector service: poll unread failed")
            return []

    async def _send(self, platform: str, conv_id: str, text: str) -> bool:
        """Async: enqueue an outbound message via the gateway's store."""
        try:
            from linc.core.models import Content, OutboundDraft

            store = self._gateway.store
            if store is None:
                return False
            draft = OutboundDraft(
                conv_id=conv_id,
                content=Content(text=text),
            )
            await store.enqueue_outbound(
                platform=platform,
                draft=draft,
                ts=time.time(),
            )
            return True
        except Exception:
            log.exception("connector service: send failed")
            return False

    # ── Internal: helpers ────────────────────────────────────────────────────

    def _submit(self, coro, timeout: float = 30.0) -> Any:
        """Submit an async coroutine to the gateway's event loop.

        Blocks until the result is ready or timeout expires.
        """
        if self._loop is None or not self._loop.is_running():
            return None
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result(timeout=timeout)
        except Exception:
            log.exception("connector service: coroutine submission failed")
            return None

    @staticmethod
    def _format_message(msg: Any) -> dict:
        """Format a linc message for the frontend."""
        from linc.core.models import InboundMessage, OutboundMessage

        result = {
            "id": getattr(msg, "id", 0),
            "platform": getattr(msg, "platform", ""),
            "conv_id": getattr(msg, "conv_id", ""),
            "ts": getattr(msg, "ts", 0),
            "text": "",
            "direction": "inbound",
            "sender_name": "",
            "sender_id": "",
            "attachments": [],
        }

        # Extract text and attachments from content
        content = getattr(msg, "content", None)
        if content is not None:
            result["text"] = getattr(content, "text", "") or ""
            for att in (getattr(content, "attachments", None) or []):
                is_img = getattr(att, "is_image", False)
                entry = {
                    "kind": getattr(att, "kind", "file"),
                    "name": getattr(att, "name", None) or "",
                    "path": getattr(att, "path", None) or "",
                    "url": getattr(att, "url", None) or "",
                    "mime": getattr(att, "mime", None) or "",
                    "is_image": is_img,
                }
                result["attachments"].append(entry)

        # Direction and sender info
        if isinstance(msg, OutboundMessage):
            result["direction"] = "outbound"
        elif isinstance(msg, InboundMessage):
            result["direction"] = "inbound"
            sender = getattr(msg, "sender", None)
            if sender is not None:
                result["sender_name"] = getattr(sender, "name", "") or ""
                result["sender_id"] = getattr(sender, "id", "") or ""

        return result


# Module-level singleton
_service = ConnectorService()


def start() -> bool:
    """Start the connector service. Returns True if gateway is running."""
    return _service.start()


def stop() -> None:
    """Stop the connector service."""
    _service.stop()


def restart() -> bool:
    """Restart the gateway with current connector configs."""
    return _service.restart()


def is_running() -> bool:
    """Check if the gateway is running."""
    return _service.is_running


def get_status() -> dict:
    """Get gateway and platform status."""
    return _service.get_status()


def get_history(platform: str, conv_id: str | None = None, limit: int = 50) -> list[dict]:
    """Fetch chat history for a platform/conversation."""
    return _service.get_history(platform, conv_id, limit)


def list_conversations(platform: str) -> list[dict]:
    """List known conversations for a platform."""
    return _service.list_conversations(platform)


def poll_unread() -> list[dict]:
    """Pull unread messages from all platforms."""
    return _service.poll_unread()


def send_message(platform: str, conv_id: str, text: str) -> bool:
    """Send a message through a platform."""
    return _service.send_message(platform, conv_id, text)


def read_attachment(path: str) -> bytes | None:
    """Read a local attachment file and return its bytes.

    Used by the frontend to display images that linc downloaded from IM
    platforms (Slack url_private etc.).
    """
    try:
        p = Path(path)
        # Safety: only allow reading from the .linc data directory
        linc_root = LINC_DATA_DIR.resolve()
        resolved = p.resolve()
        if not str(resolved).startswith(str(linc_root)):
            log.warning("connector service: attachment path outside .linc: %s", path)
            return None
        if not p.is_file():
            return None
        return p.read_bytes()
    except Exception:
        log.exception("connector service: read attachment failed")
        return None
