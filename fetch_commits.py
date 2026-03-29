#!/usr/bin/env python3
import requests
import json
import random

# List of OWASP repos
repos = [
    "OWASP/OWASP-Top-10",
    "OWASP/ASVS",
    "OWASP/wstg",
    "OWASP/CheatSheetSeries",
    "OWASP/owasp-masvs",
    "OWASP/owasp-mstg",
    "OWASP/owasp-api-security",
    "OWASP/owasp-testing-guide-v4",
    "OWASP/owasp-testing-guide-v5",
    "OWASP/owasp-zap",
    "OWASP/owasp-mstg",
    "OWASP/owasp-api-security",
    "OWASP/owasp-testing-guide-v4",
    "OWASP/owasp-testing-guide-v5",
    "OWASP/owasp-zap",
    "OWASP/owasp-mstg",
    "OWASP/owasp-api-security",
    "OWASP/owasp-testing-guide-v4",
    "OWASP/owasp-testing-guide-v5",
    "OWASP/owasp-zap"
]

commits = []

for repo in repos:
    try:
        url = f"https://api.github.com/repos/{repo}/commits?per_page=10"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for commit in data:
                message = commit['commit']['message']
                commits.append(message)
                if len(commits) >= 100:
                    break
        if len(commits) >= 100:
            break
    except:
        pass

# Save to file
with open('commits.json', 'w') as f:
    json.dump(commits[:100], f, indent=2)

print(f"Collected {len(commits[:100])} commits")
