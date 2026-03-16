import { useEffect, useRef, useState, useCallback } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "@xterm/addon-fit";
import { X, Terminal as TerminalIcon } from "lucide-react";

import "xterm/css/xterm.css";

interface ClaudeTerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  businessId: string;
  onAuthenticated?: () => void;
}

type Status = "connecting" | "running" | "success" | "error" | "closed";

export function ClaudeTerminalModal({
  isOpen,
  onClose,
  businessId,
  onAuthenticated,
}: ClaudeTerminalModalProps) {
  const terminalRef = useRef<HTMLDivElement>(null);
  const termInstance = useRef<Terminal | null>(null);
  const fitAddon = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<Status>("connecting");

  const cleanup = useCallback(() => {
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    }
    if (termInstance.current) {
      termInstance.current.dispose();
      termInstance.current = null;
    }
    fitAddon.current = null;
  }, []);

  useEffect(() => {
    if (!isOpen || !terminalRef.current) return;

    // Create terminal
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, monospace",
      theme: {
        background: "#1a1b26",
        foreground: "#a9b1d6",
        cursor: "#c0caf5",
        selectionBackground: "#33467c",
        black: "#15161e",
        red: "#f7768e",
        green: "#9ece6a",
        yellow: "#e0af68",
        blue: "#7aa2f7",
        magenta: "#bb9af7",
        cyan: "#7dcfff",
        white: "#a9b1d6",
        brightBlack: "#414868",
        brightRed: "#f7768e",
        brightGreen: "#9ece6a",
        brightYellow: "#e0af68",
        brightBlue: "#7aa2f7",
        brightMagenta: "#bb9af7",
        brightCyan: "#7dcfff",
        brightWhite: "#c0caf5",
      },
      rows: 24,
      cols: 80,
      scrollback: 1000,
      convertEol: true,
    });

    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(terminalRef.current);

    // Small delay to let DOM settle before fitting
    setTimeout(() => {
      try {
        fit.fit();
      } catch {
        // ignore
      }
    }, 100);

    termInstance.current = term;
    fitAddon.current = fit;

    // Connect WebSocket
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.hostname;
    const port = "8000";
    const wsUrl = `${protocol}//${host}:${port}/api/v1/terminal/ws?business_id=${businessId}&command=setup-token`;

    setStatus("connecting");

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setStatus("running");

      // Send initial resize
      const dims = fit.proposeDimensions();
      if (dims) {
        ws.send(JSON.stringify({
          type: "resize",
          rows: dims.rows,
          cols: dims.cols,
        }));
      }
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Binary terminal output
        const data = new Uint8Array(event.data);
        term.write(data);
      } else if (typeof event.data === "string") {
        // Could be JSON control message or text terminal output
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "token_captured") {
            setStatus("success");
            onAuthenticated?.();
          } else if (msg.type === "auth_complete") {
            // Silently note — success footer handles it
          } else if (msg.type === "error") {
            setStatus("error");
            term.writeln(`\r\n\x1b[31m✗ ${msg.message}\x1b[0m\r\n`);
          }
        } catch {
          // Plain text output
          term.write(event.data);
        }
      }
    };

    ws.onerror = () => {
      setStatus("error");
      term.writeln("\r\n\x1b[31m✗ WebSocket connection failed\x1b[0m\r\n");
    };

    ws.onclose = () => {
      if (status !== "success") {
        setStatus("closed");
      }
    };

    // Forward terminal input to WebSocket
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    // Handle resize
    const handleResize = () => {
      try {
        fit.fit();
        const dims = fit.proposeDimensions();
        if (dims && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: "resize",
            rows: dims.rows,
            cols: dims.cols,
          }));
        }
      } catch {
        // ignore
      }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    if (terminalRef.current) {
      resizeObserver.observe(terminalRef.current);
    }
    window.addEventListener("resize", handleResize);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleResize);
      cleanup();
    };
  }, [isOpen, businessId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative mx-4 flex h-[520px] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border bg-[#1a1b26] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 bg-[#1f2335] px-4 py-3">
          <div className="flex items-center gap-2">
            <TerminalIcon className="h-4 w-4 text-cyan-400" />
            <span className="text-sm font-medium text-white/90">
              Claude CLI Setup
            </span>
          </div>
          <button
            onClick={() => {
              cleanup();
              onClose();
            }}
            className="rounded p-1 text-white/50 transition-colors hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Terminal */}
        <div
          ref={terminalRef}
          className="flex-1 px-1 py-1"
          style={{ minHeight: 0 }}
        />

        {/* Footer — only shows on success or error */}
        {status === "success" && (
          <div className="flex items-center justify-between border-t border-white/10 bg-green-500/10 px-4 py-3">
            <span className="text-sm text-green-300">
              Claude connected successfully.
            </span>
            <button
              onClick={() => {
                cleanup();
                onClose();
              }}
              className="rounded-md bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-green-700"
            >
              Close
            </button>
          </div>
        )}
        {status === "error" && (
          <div className="flex items-center justify-between border-t border-white/10 bg-red-500/10 px-4 py-3">
            <span className="text-sm text-red-300">
              Connection failed. Try again.
            </span>
            <button
              onClick={() => {
                cleanup();
                onClose();
              }}
              className="rounded-md bg-white/10 px-4 py-1.5 text-sm font-medium text-white hover:bg-white/20"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
