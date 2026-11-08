import { defineConfig, devices } from '@playwright/test';

const port = Number(process.env.E2E_PORT || 4173);

// End-to-end tests against the real API and worker. Run `npm run test:e2e` (builds the web app first).
// The tests share one fresh database and run in order, like a new install being used for the first time.
export default defineConfig({
	testDir: './e2e',
	fullyParallel: false,
	workers: 1,
	forbidOnly: !!process.env.CI,
	retries: 0,
	reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
	timeout: 60_000,
	expect: { timeout: 20_000 },
	use: {
		baseURL: `http://127.0.0.1:${port}`,
		trace: 'retain-on-failure'
	},
	projects: [{ name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 900 } } }],
	webServer: {
		command: 'sh e2e/serve.sh',
		url: `http://127.0.0.1:${port}/api/health`,
		reuseExistingServer: false,
		timeout: 120_000,
		env: { E2E_PORT: String(port) }
	}
});
