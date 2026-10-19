"""Tiny RunPod GraphQL client. The key is RUNPOD_API_KEY: environment, then .env in the repo root, then the macOS Keychain.
It is never written to disk by this code."""
import json, os, subprocess, sys, urllib.request
from pathlib import Path


def _load_dotenv():
    """Put the repo's .env entries into os.environ (without overriding what is already set)."""
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            n, sep, val = line.strip().partition("=")
            n = n.removeprefix("export ").strip()
            if sep and n and not n.startswith("#") and val.strip():
                os.environ.setdefault(n, os.path.expanduser(val.strip().strip("'\"")))


def _key():
    _load_dotenv()
    v = os.environ.get("RUNPOD_API_KEY", "")
    if not v and sys.platform == "darwin":
        v = subprocess.run(["security", "find-generic-password", "-s", "RUNPOD_API_KEY", "-w"], capture_output=True, text=True).stdout.strip()
    if not v:
        sys.exit("RUNPOD_API_KEY is not set: copy .env.example to .env and fill it in (see the README, Training)")
    return v


KEY = _key()
def gql(query, variables=None):
    req = urllib.request.Request("https://api.runpod.io/graphql", data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY, "User-Agent": "understudy"})
    with urllib.request.urlopen(req, timeout=60) as f:
        return json.load(f)
if __name__ == "__main__":
    print(json.dumps(gql(sys.argv[1])))
