"""
Lightweight local HTTP server — the single interface for Swing Trader.

Serves the dashboard HTML and provides JSON API endpoints so every action
(scan, log entry, log exit, config, review) can be triggered from the browser.

No Flask. Uses only Python stdlib http.server.

Usage:
    python server.py              # starts on port 5050
    python server.py 8080         # starts on port 8080
"""

import json
import sys
import threading
import traceback
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

DATA_DIR = _THIS_DIR / "data"

_scan_lock = threading.Lock()
_scan_status = {"running": False, "message": ""}


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "":
            self._serve_dashboard()
        elif path == "/api/data":
            self._api_data()
        elif path == "/api/scan/status":
            self._json_response(_scan_status)
        elif path == "/api/prompt":
            self._api_prompt()
        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        try:
            if path == "/api/log-entry":
                self._api_log_entry(body)
            elif path == "/api/log-exit":
                self._api_log_exit(body)
            elif path == "/api/config":
                self._api_config(body)
            elif path == "/api/scan":
                self._api_scan(body)
            elif path == "/api/delete-trade":
                self._api_delete_trade(body)
            elif path == "/api/paste-response":
                self._api_paste_response(body)
            else:
                self._json_response({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            self._json_response({"error": str(e)}, 500)

    # ── Dashboard ──

    def _serve_dashboard(self):
        from dashboard_generator import generate_dashboard
        generate_dashboard()
        html_path = DATA_DIR / "dashboard.html"
        if html_path.exists():
            content = html_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self._json_response({"error": "dashboard not generated"}, 500)

    # ── API: full data reload ──

    def _api_data(self):
        from dashboard_generator import _read_trades, _read_json, _compute_stats
        from datetime import datetime

        trades = _read_trades()
        decision = _read_json("latest_decision.json")
        config = _read_json("config.json")
        if not config:
            config = {"capital": 1000, "max_positions": 10, "max_sector_exposure": 3, "brokerage_fee_pct": 0.25}
        stats = _compute_stats(trades, config)

        self._json_response({
            "config": config,
            "trades": trades,
            "decision": decision,
            "stats": stats,
            "generated_at": datetime.now().isoformat(),
        })

    # ── API: log entry ──

    def _api_log_entry(self, body: dict):
        from journal.tracker import log_entry

        required = ["ticker", "price", "shares", "stop", "target"]
        missing = [k for k in required if k not in body]
        if missing:
            self._json_response({"error": f"Missing fields: {missing}"}, 400)
            return

        trade_id = log_entry(
            ticker=body["ticker"].upper(),
            price=float(body["price"]),
            shares=float(body["shares"]),
            position_usd=float(body["price"]) * float(body["shares"]),
            stop_loss=float(body["stop"]),
            target=float(body["target"]),
            notes=body.get("notes", ""),
        )
        self._json_response({"ok": True, "trade_id": trade_id})

    # ── API: log exit ──

    def _api_log_exit(self, body: dict):
        from journal.tracker import log_exit

        if "ticker" not in body or "price" not in body:
            self._json_response({"error": "Missing ticker or price"}, 400)
            return

        result = log_exit(
            ticker=body["ticker"].upper(),
            price=float(body["price"]),
            reason=body.get("reason", "manual"),
            notes=body.get("notes", ""),
        )
        if result:
            self._json_response({"ok": True, **result})
        else:
            self._json_response({"error": f"No open position for {body['ticker']}"}, 404)

    # ── API: config ──

    def _api_config(self, body: dict):
        from config.loader import save_user_config
        save_user_config(body)
        self._json_response({"ok": True})

    # ── API: scan ──

    def _api_scan(self, body: dict):
        global _scan_status
        if _scan_status["running"]:
            self._json_response({"error": "Scan already running"}, 409)
            return

        from_response = body.get("from_response", False)
        t = threading.Thread(target=self._run_scan_bg, args=(from_response,), daemon=True)
        t.start()
        self._json_response({"ok": True, "message": "Scan started"})

    def _run_scan_bg(self, from_response: bool):
        global _scan_status
        _scan_status = {"running": True, "message": "Scan in progress..."}

        try:
            if from_response:
                from agent.runner import load_manual_response
                decision = load_manual_response()
                if not decision:
                    _scan_status = {"running": False, "message": "No response file found"}
                    return
            else:
                from agent.briefing import build_briefing, briefing_to_text
                from agent.prompts import build_scan_prompt
                from agent.runner import invoke_claude

                _scan_status["message"] = "Gathering market data..."
                briefing = build_briefing(
                    verbose=False,
                    progress_cb=lambda msg: _scan_status.update({"message": msg}),
                )
                _scan_status["message"] = "Sending to Claude..."
                briefing_text = briefing_to_text(briefing)
                prompt = build_scan_prompt(briefing_text)
                decision = invoke_claude(prompt)

            out_path = DATA_DIR / "latest_decision.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")

            status_msg = decision.get("message", "") if decision.get("status") == "manual_required" else "Scan complete"
            _scan_status = {"running": False, "message": status_msg, "status": decision.get("status", "ok")}

        except Exception as e:
            traceback.print_exc()
            _scan_status = {"running": False, "message": f"Error: {e}"}

    # ── API: delete trade ──

    def _api_delete_trade(self, body: dict):
        from journal.tracker import _read_all, _write_all

        trade_id = body.get("id")
        if trade_id is None:
            self._json_response({"error": "Missing trade id"}, 400)
            return

        rows = _read_all()
        new_rows = [r for r in rows if str(r["id"]) != str(trade_id)]
        if len(new_rows) == len(rows):
            self._json_response({"error": f"Trade {trade_id} not found"}, 404)
            return

        _write_all(new_rows)
        self._json_response({"ok": True})

    # ── API: prompt ──

    def _api_prompt(self):
        prompt_path = DATA_DIR / "pending_prompt.txt"
        if prompt_path.exists():
            text = prompt_path.read_text(encoding="utf-8")
            self._json_response({"prompt": text, "length": len(text)})
        else:
            self._json_response({"prompt": None})

    # ── API: paste Claude response ──

    def _api_paste_response(self, body: dict):
        response_text = body.get("response", "")
        if not response_text.strip():
            self._json_response({"error": "Empty response"}, 400)
            return

        from agent.runner import _parse_json_response
        decision = _parse_json_response(response_text)

        out_path = DATA_DIR / "latest_decision.json"
        out_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")

        resp_path = DATA_DIR / "claude_response.json"
        resp_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")

        self._json_response({"ok": True, "status": decision.get("status", "ok")})

    # ── Helpers ──

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        if "/api/scan/status" not in (args[0] if args else ""):
            super().log_message(format, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print(f"Swing Trader running at {url}")
    print("Press Ctrl+C to stop.\n")

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
