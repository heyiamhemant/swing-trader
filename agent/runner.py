"""
Runs Claude decisions through Cursor's agent subprocess.

This module writes the prompt to a file, invokes `cursor-agent` CLI,
and parses the JSON response. When Cursor CLI is unavailable, it falls
back to the Anthropic API if ANTHROPIC_API_KEY is set.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Preferred model for the Cursor agent
CURSOR_MODEL = "claude-4-opus"


def invoke_claude(prompt: str, use_cursor: bool = True) -> dict:
    """
    Send a prompt to Claude and get a parsed JSON response.

    Priority:
      1. Cursor CLI agent (if available)
      2. Anthropic API (if ANTHROPIC_API_KEY is set)
      3. Prompt-file fallback (writes prompt to file for manual use)
    """
    if use_cursor:
        result = _try_cursor_cli(prompt)
        if result is not None:
            return result

    result = _try_anthropic_api(prompt)
    if result is not None:
        return result

    return _fallback_save_prompt(prompt)


def _try_cursor_cli(prompt: str) -> dict | None:
    """Invoke Claude via Cursor's CLI agent mode."""
    try:
        prompt_file = PROJECT_ROOT / "data" / ".agent_prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        result = subprocess.run(
            [
                "cursor",
                "--agent",
                "--model", CURSOR_MODEL,
                "--prompt-file", str(prompt_file),
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PROJECT_ROOT),
        )

        if result.returncode == 0 and result.stdout.strip():
            return _parse_json_response(result.stdout)

    except FileNotFoundError:
        pass  # cursor CLI not in PATH
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    return None


def _try_anthropic_api(prompt: str) -> dict | None:
    """Fall back to direct Anthropic API call."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        return _parse_json_response(text)

    except ImportError:
        # anthropic package not installed — guide user
        print("[warn] anthropic package not installed. Run: pip install anthropic")
        return None
    except Exception as e:
        print(f"[warn] Anthropic API error: {e}")
        return None


def _fallback_save_prompt(prompt: str) -> dict:
    """
    When no API is available, save the prompt so the user can paste it
    into Claude manually and feed the response back.
    """
    prompt_path = PROJECT_ROOT / "data" / "pending_prompt.txt"
    response_path = PROJECT_ROOT / "data" / "claude_response.json"

    prompt_path.write_text(prompt, encoding="utf-8")

    import platform
    if platform.system() == "Darwin":
        copy_hint = f"    pbcopy < {prompt_path}"
    else:
        copy_hint = f"    xclip -sel clipboard < {prompt_path}"

    return {
        "status": "manual_required",
        "message": (
            f"No automated Claude access available.\n\n"
            f"1. Copy the prompt to clipboard:\n{copy_hint}\n\n"
            f"2. Paste it into claude.ai and get the JSON response\n\n"
            f"3. Save the response:\n    {response_path}\n\n"
            f"4. Re-run:\n    python main.py scan --from-response\n\n"
            f"Or set ANTHROPIC_API_KEY to automate this step."
        ),
        "prompt_path": str(prompt_path),
        "response_path": str(response_path),
    }


def load_manual_response() -> dict | None:
    """Load a manually-saved Claude response from disk."""
    response_path = PROJECT_ROOT / "data" / "claude_response.json"
    if not response_path.exists():
        return None

    text = response_path.read_text(encoding="utf-8")
    return _parse_json_response(text)


def _parse_json_response(text: str) -> dict:
    """
    Extract JSON from Claude's response. Claude sometimes wraps JSON in
    markdown code fences — handle that.
    """
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Find the JSON object boundaries
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return {
        "status": "parse_error",
        "raw_response": text[:2000],
        "message": "Could not parse JSON from Claude's response",
    }
