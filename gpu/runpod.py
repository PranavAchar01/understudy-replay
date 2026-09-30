"""Tiny RunPod GraphQL client. Key comes from the macOS Keychain (RUNPOD_API_KEY); never written to disk."""
import json, subprocess, sys, urllib.request
KEY = subprocess.run(["security", "find-generic-password", "-s", "RUNPOD_API_KEY", "-w"], capture_output=True, text=True).stdout.strip()
def gql(query, variables=None):
    req = urllib.request.Request("https://api.runpod.io/graphql", data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY, "User-Agent": "understudy"})
    with urllib.request.urlopen(req, timeout=60) as f:
        return json.load(f)
if __name__ == "__main__":
    print(json.dumps(gql(sys.argv[1])))
