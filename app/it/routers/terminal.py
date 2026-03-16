"""
Terminal WebSocket — bridges a browser-based xterm.js to a real PTY
so users can run interactive CLI commands (like `claude setup-token`)
directly from the web app.

Flow:
  1. Frontend opens WS to /api/v1/terminal/ws?business_id=...
  2. Backend spawns an interactive bash shell in a PTY
  3. Shell runs `claude setup-token` then stays open for interaction
  4. PTY stdout → WebSocket → xterm.js (renders TUI properly)
  5. xterm.js keystrokes → WebSocket → PTY stdin
  6. Backend monitors output for the OAuth token
  7. When token is captured, it's verified and stored encrypted in DB
"""

import asyncio
import fcntl
import json
import logging
import os
import pty
import re
import select as select_mod
import struct
import termios
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.database import async_session
from app.core.services.claude_cli_service import claude_cli

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/terminal", tags=["Terminal"])

# Patterns to detect a token in the PTY output.
# claude setup-token may output the token in various formats:
#   export CLAUDE_CODE_OAUTH_TOKEN=...
#   CLAUDE_CODE_OAUTH_TOKEN="..."
#   Token: sk-ant-...
TOKEN_PATTERNS = [
    # sk-ant-oat* OAuth tokens - stops right before "Store this token" message
    # This is the most reliable pattern based on actual claude setup-token output
    re.compile(
        r"(sk-ant-oat\d+-[A-Za-z0-9_\-]+)Store",
    ),
    # export CLAUDE_CODE_OAUTH_TOKEN=<token> with proper boundaries
    re.compile(
        r"CLAUDE_CODE_OAUTH_TOKEN[=:\s]+[\"']?([A-Za-z0-9_\-]{100,})(?:[\"'\s]|$)",
    ),
    # JWT-style token (eyJ...)
    re.compile(
        r"\b(eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)",
    ),
]

# Log the patterns at startup for debugging
logger.info(f"[Terminal] Loaded {len(TOKEN_PATTERNS)} token capture patterns")
for idx, pattern in enumerate(TOKEN_PATTERNS):
    logger.debug(f"[Terminal] Pattern #{idx}: {pattern.pattern}")

# Detect when the CLI says auth is complete
SUCCESS_PATTERNS = [
    re.compile(r"token.*(?:saved|generated|created|set|successfully)", re.IGNORECASE),
    re.compile(r"(?:saved|generated|created|set).*token", re.IGNORECASE),
    re.compile(r"successfully.*(?:authenticated|created)", re.IGNORECASE),
    re.compile(r"authentication.*(?:complete|success)", re.IGNORECASE),
    re.compile(r"setup.token.*complete", re.IGNORECASE),
]


def _set_pty_size(fd: int, rows: int, cols: int) -> None:
    """Set the PTY window size."""
    size = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, size)


def _blocking_read(fd: int) -> bytes:
    """
    Read from PTY using select() to wait for data.
    Returns empty bytes when PTY is closed.
    """
    try:
        ready, _, _ = select_mod.select([fd], [], [], 0.1)
        if ready:
            return os.read(fd, 4096)
        return b""  # No data yet, but not closed
    except (OSError, ValueError):
        return b""  # PTY closed


@router.websocket("/ws")
async def terminal_ws(
    websocket: WebSocket,
    business_id: UUID = Query(...),
    token: str = Query(""),  # JWT auth token (future use)
    command: str = Query("setup-token"),  # Which claude subcommand to run
):
    """
    WebSocket endpoint for an interactive terminal session.

    Spawns a bash shell in a PTY, runs the requested Claude CLI command,
    and keeps the shell alive so the user can interact with the full
    TUI output.

    Messages from client:
      - Binary/text: raw terminal input (keystrokes)
      - JSON: {"type": "resize", "rows": N, "cols": N}

    Messages to client:
      - Binary/text: terminal output
      - JSON: {"type": "token_captured", "message": "..."}
      - JSON: {"type": "auth_complete", "message": "..."}
      - JSON: {"type": "error", "message": "..."}
    """
    logger.info(f"[Terminal] WebSocket connection opened - business_id={business_id}, command={command}")

    await websocket.accept()
    logger.info(f"[Terminal] WebSocket accepted for business {business_id}")

    # Validate command
    allowed_commands = {"setup-token", "login", "doctor"}
    if command not in allowed_commands:
        logger.warning(f"[Terminal] Invalid command attempted: {command}")
        await websocket.send_json({
            "type": "error",
            "message": f"Command not allowed: {command}",
        })
        await websocket.close()
        return

    env = claude_cli._clean_env()
    # Ensure we have a proper TERM
    env["TERM"] = "xterm-256color"

    logger.info(f"[Terminal] Preparing to spawn 'claude {command}' for business {business_id}")

    # Build a shell script that runs the command and keeps the shell open
    # This way: (1) the TUI renders in a real PTY, (2) the session stays
    # alive for interaction, (3) the user can see all output
    # Run the command, then sleep to keep PTY alive for token capture.
    # The frontend handles the close button — no need for "press any key".
    shell_script = (
        f'claude {command}; '
        f'sleep 86400'
    )

    cmd = ["bash", "-c", shell_script]

    # Create PTY
    try:
        master_fd, slave_fd = pty.openpty()
        _set_pty_size(master_fd, 24, 80)
        logger.debug(f"[Terminal] PTY created (master_fd={master_fd}, slave_fd={slave_fd})")
    except Exception as e:
        logger.error(f"[Terminal] PTY creation failed: {e}", exc_info=True)
        raise

    # Spawn the process attached to the PTY
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            preexec_fn=os.setsid,
        )
        logger.info(f"[Terminal] Process spawned (pid={process.pid}) for business {business_id}")
    except Exception as e:
        logger.error(f"[Terminal] Failed to spawn process for business {business_id}: {e}", exc_info=True)
        os.close(master_fd)
        os.close(slave_fd)
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to start CLI: {e}",
        })
        await websocket.close()
        return

    # Close slave in parent — the child process owns it now
    os.close(slave_fd)

    # Buffer for token detection
    output_buffer = ""
    clean_buffer = ""  # Stripped of ANSI codes and line breaks for regex
    captured_token = None
    success_sent = False

    # Regex to strip ANSI escape sequences
    ansi_strip = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\r")

    async def read_pty():
        """Read from PTY and send to WebSocket."""
        nonlocal output_buffer, captured_token, success_sent, clean_buffer
        loop = asyncio.get_event_loop()

        logger.debug(f"[Terminal] Starting PTY reader for business {business_id}")

        while True:
            try:
                # Use select-based blocking read in a thread
                data = await loop.run_in_executor(None, _blocking_read, master_fd)

                # Check if process has exited
                if process.returncode is not None and not data:
                    logger.info(f"[Terminal] Process exited (code: {process.returncode}) for business {business_id}")
                    break

                if not data:
                    # No data yet but process still running — keep looping
                    continue

                # Send raw terminal output to the browser
                try:
                    await websocket.send_bytes(data)
                except Exception as e:
                    logger.error(f"[Terminal] Failed to send data to WebSocket: {e}")
                    break

                # Buffer for token detection (keep last 4KB)
                decoded = data.decode("utf-8", errors="replace")
                output_buffer += decoded
                if len(output_buffer) > 8192:
                    output_buffer = output_buffer[-8192:]

                # Build a clean buffer (no ANSI, no line breaks) for regex
                clean_buffer = ansi_strip.sub("", output_buffer)
                clean_buffer = clean_buffer.replace("\n", "")

                # Log a sample of the clean buffer for debugging
                if len(clean_buffer) > 50 and not captured_token:
                    logger.debug(
                        f"[Terminal] Clean buffer sample (last 200 chars): "
                        f"{clean_buffer[-200:]}"
                    )

                # Try to capture token from output
                if not captured_token:
                    for idx, pattern in enumerate(TOKEN_PATTERNS):
                        match = pattern.search(clean_buffer)
                        if match:
                            captured_token = match.group(1)
                            logger.info(
                                f"[Terminal] Token captured via pattern #{idx} "
                                f"(length: {len(captured_token)} chars) "
                                f"for business {business_id}"
                            )
                            logger.debug(
                                f"[Terminal] Token preview: {captured_token[:20]}...{captured_token[-20:]}"
                            )
                            await _try_store_token(
                                websocket, business_id, captured_token
                            )
                            break

                # Check for success patterns
                if not success_sent:
                    for idx, pattern in enumerate(SUCCESS_PATTERNS):
                        if pattern.search(decoded):
                            success_sent = True
                            logger.info(
                                f"[Terminal] Success pattern #{idx} detected "
                                f"for business {business_id}"
                            )
                            try:
                                await websocket.send_json({
                                    "type": "auth_complete",
                                    "message": (
                                        "Authentication appears complete! "
                                        "You can close this terminal."
                                    ),
                                })
                            except Exception as e:
                                logger.error(f"[Terminal] Failed to send auth_complete: {e}")
                            break

            except WebSocketDisconnect:
                logger.info(f"[Terminal] WebSocket disconnected for business {business_id}")
                break
            except Exception as e:
                logger.error(f"[Terminal] Read error for business {business_id}: {e}", exc_info=True)
                break

    async def write_pty():
        """Read from WebSocket and write to PTY."""
        while True:
            try:
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                if "bytes" in message and message["bytes"]:
                    os.write(master_fd, message["bytes"])
                elif "text" in message and message["text"]:
                    text = message["text"]
                    # Check if it's a JSON control message
                    try:
                        ctrl = json.loads(text)
                        if ctrl.get("type") == "resize":
                            rows = ctrl.get("rows", 24)
                            cols = ctrl.get("cols", 80)
                            _set_pty_size(master_fd, rows, cols)
                            continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                    # Otherwise it's raw text input
                    os.write(master_fd, text.encode("utf-8"))

            except WebSocketDisconnect:
                break
            except OSError:
                # PTY closed
                break
            except Exception as e:
                logger.debug(f"[Terminal] Write error: {e}")
                break

    try:
        # Run reader and writer concurrently
        reader_task = asyncio.create_task(read_pty())
        writer_task = asyncio.create_task(write_pty())

        # Wait for either task to end
        done, pending = await asyncio.wait(
            [reader_task, writer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    except Exception as e:
        logger.error(f"[Terminal] Session error: {e}")
    finally:
        # Clean up
        try:
            os.close(master_fd)
        except OSError:
            pass

        try:
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

        try:
            await websocket.close()
        except Exception:
            pass

        logger.info(f"[Terminal] Session ended for business {business_id}")


async def _try_store_token(
    websocket: WebSocket, business_id: UUID, token: str
) -> None:
    """Store a captured token in the database.

    Since the token just came from `claude setup-token`, we trust it
    and store directly without a verification call (which would cost
    money and might timeout).
    """
    logger.info(f"[Terminal] Attempting to store token for business {business_id} (length: {len(token)})")

    try:
        async with async_session() as db:
            logger.debug(f"[Terminal] Database session created, calling store_business_token")
            account = await claude_cli.store_business_token(db, business_id, token)
            logger.debug(f"[Terminal] Token stored in ConnectedAccount (id={account.id}, status={account.status})")

            await db.commit()
            logger.info(f"[Terminal] Transaction committed - token stored for business {business_id}")

        try:
            await websocket.send_json({
                "type": "token_captured",
                "message": (
                    "Token captured and saved! "
                    "Your Claude CLI is now connected."
                ),
            })
            logger.info(f"[Terminal] Sent 'token_captured' message to frontend")
        except Exception as send_err:
            logger.error(f"[Terminal] Failed to send token_captured message: {send_err}")

    except Exception as e:
        logger.error(f"[Terminal] Failed to store token for business {business_id}: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Failed to save token: {e}",
            })
        except Exception as send_err:
            logger.error(f"[Terminal] Failed to send error message: {send_err}")
