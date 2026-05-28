import os
import subprocess
import requests
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration — edit these to customize behavior
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a ship log writer for a software project.
Given a list of git commits, write a concise, human-readable summary in the
style of a captain's log. Focus on what changed and why it matters.
Keep it to 3-5 sentences. Use plain prose — no markdown headers or bullet lists."""

GEMINI_MODEL = "gemini-2.0-flash"  # swap for gemini-2.5-flash, gemini-2.5-pro, etc.

# ---------------------------------------------------------------------------

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def get_commit_logs(before_sha: str, after_sha: str) -> str:
    """Return formatted commit messages between two SHAs."""
    zero_sha = "0" * 40
    if before_sha == zero_sha:
        # First push to this branch — show last 10 commits
        cmd = ["git", "log", after_sha, "-10", "--pretty=format:%h - %s (%an)"]
    else:
        cmd = [
            "git", "log",
            f"{before_sha}..{after_sha}",
            "--pretty=format:%h - %s (%an)",
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    logs = result.stdout.strip()
    return logs if logs else "No commits found."


def call_gemini(
    commit_logs: str,
    push_date: str,
    pusher_name: str,
    repo_name: str,
    branch: str,
) -> str:
    """Send commit logs to the Gemini API and return the generated summary."""
    api_key = os.environ["GEMINI_API_KEY"]

    user_message = (
        f"Repository: {repo_name}\n"
        f"Branch: {branch}\n"
        f"Date: {push_date}\n"
        f"Pushed by: {pusher_name}\n\n"
        f"Commits:\n{commit_logs}\n\n"
        "Write a ship log entry for this push."
    )

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {"parts": [{"text": user_message}]}
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 512,
        },
    }

    response = requests.post(
        f"{GEMINI_API_URL}?key={api_key}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def prepend_to_ship_log(entry: str, push_date: str, after_sha: str) -> None:
    """Prepend a formatted entry to the top of ship-log.md."""
    ship_log_path = "ship-log.md"
    short_sha = after_sha[:7]

    new_entry = (
        f"## {push_date} — `{short_sha}`\n\n"
        f"{entry}\n\n"
        f"---\n\n"
    )

    if os.path.exists(ship_log_path):
        with open(ship_log_path, "r", encoding="utf-8") as f:
            existing = f.read()
    else:
        existing = "# Ship Log\n\n"

    # Insert after the top-level heading if present, otherwise prepend
    if existing.startswith("# Ship Log"):
        split_at = existing.find("\n\n") + 2
        new_content = existing[:split_at] + new_entry + existing[split_at:]
    else:
        new_content = "# Ship Log\n\n" + new_entry + existing

    with open(ship_log_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def main() -> None:
    before_sha = os.environ["BEFORE_SHA"]
    after_sha = os.environ["AFTER_SHA"]
    push_date = os.environ.get(
        "PUSH_DATE",
        datetime.now(timezone.utc).isoformat(),
    )
    pusher_name = os.environ.get("PUSHER_NAME", "unknown")
    repo_name = os.environ.get("REPO_NAME", "unknown")
    branch = os.environ.get("BRANCH", "main")

    print(f"Extracting commits: {before_sha[:7]}..{after_sha[:7]}")
    commit_logs = get_commit_logs(before_sha, after_sha)
    print(f"Commits found:\n{commit_logs}\n")

    print("Calling Gemini API...")
    summary = call_gemini(commit_logs, push_date, pusher_name, repo_name, branch)
    print(f"Summary:\n{summary}\n")

    print("Updating ship-log.md...")
    prepend_to_ship_log(summary, push_date, after_sha)
    print("Done.")


if __name__ == "__main__":
    main()
