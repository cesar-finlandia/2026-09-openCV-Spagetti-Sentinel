# E2E browser tests

Real browser (Chromium), real server, no mocks. The `appTest` fixture boots
`uvicorn app.api.main:app` per worker with `S3_BUCKET=` unset (local evidence
backend) unless `BASE_URL` is set, in which case no server is started.

## Run

```bash
npx playwright install chromium   # once per machine
npx playwright test -c e2e/playwright.config.ts        # full suite (14 scenarios)
npx playwright test -c e2e/playwright.config.ts uc14   # one scenario
BASE_URL=http://ec2-35-94-80-183.us-west-2.compute.amazonaws.com \
  npx playwright test -c e2e/playwright.config.ts smoke  # deployed smoke suite
```

Suite config: `workers: 1` (the app holds one active run at a time),
`retries: 0` (flake is a defect), 120 s per test. Artefacts land in
`e2e/artifacts/` (gitignored); evidence scratch in `.e2e-evidence/`
(gitignored, removed on teardown).
