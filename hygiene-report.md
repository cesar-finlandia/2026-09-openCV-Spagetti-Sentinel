# Hygiene report

### Secret scan — flagged (1 hit(s))

- `.env.example`:1 — pattern `credential_filename` — `.env...REDACTED`

Remediation is manual: `git rm --cached <file>`, add to `.gitignore`, rotate the key, then commit. This scanner is flag-only.

### Commit distribution — clean (31% in one 1h bucket)

13 total commits; largest bucket `2026-09-11T14:00Z` holds 4 (31%, threshold 80%).

## Warnings

- warn: hygiene config unreadable at C:\Users\cesar\Documents\CursorAI-projects\hackathon-entries\2026-09-openCV\src\provenance\config\hygiene.json: [Errno 2] No such file or directory: 'C:\\Users\\cesar\\Documents\\CursorAI-projects\\hackathon-entries\\2026-09-openCV\\contracts\\hygiene-config.schema.json' — using safe defaults (GOV-RES-02)

Overall: **flagged**
