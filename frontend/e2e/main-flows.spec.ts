import { expect, test, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

// One fresh install, used the way a new group would: set up the admin, upload photos, review,
// browse plates, delete one and get it back. Steps run in order and share the signed-in page.

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));
const PLATE_PHOTO = fixture('plate-gr8ful.jpg'); // a TX plate reading GR8FUL, with GPS and time
const NO_PLATE_PHOTO = fixture('no-plate.jpg'); // noise with GPS and time; OCR finds no plate

test.describe.configure({ mode: 'serial' });

let page: Page;

test.beforeAll(async ({ browser }) => {
	page = await browser.newPage();
});

test.afterAll(async () => {
	await page?.close();
});

async function upload(file: string) {
	await page.goto('/upload');
	await page.locator('input[type=file]').setInputFiles(file);
}

test('first visit sets up the admin account', async () => {
	await page.goto('/');
	await expect(page).toHaveURL(/\/login/);
	await expect(page.getByRole('heading', { name: 'Set up Platedex' })).toBeVisible();
	await page.getByLabel('Username').fill('alex');
	await page.getByLabel('Password').fill('password123');
	await page.getByRole('button', { name: 'Create admin account' }).click();

	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByText('No photos yet')).toBeVisible();
});

test('an uploaded photo is read by the worker', async () => {
	await upload(PLATE_PHOTO);
	await expect(page.getByText(/Read GR8FUL/)).toBeVisible({ timeout: 45_000 });

	await page.goto('/');
	await expect(page.locator('main').getByText('GR8FUL').first()).toBeVisible();
});

test('a photo without a readable plate is identified in Review', async () => {
	await upload(NO_PLATE_PHOTO);
	await expect(page.getByText('OCR found no plate')).toBeVisible({ timeout: 45_000 });

	await page.goto('/review');
	await page.getByRole('tab', { name: /Identify/ }).click();
	await page.getByRole('button', { name: 'Type plate' }).click();
	await page.getByPlaceholder('7A?123').fill('luvu2');
	await page.getByRole('button', { name: 'Save plate' }).click();
	await expect(page.getByText('All caught up')).toBeVisible();
});

test('plates list, search and plate page', async () => {
	await page.goto('/plates');
	await expect(page.getByText('2 plates · 2 sightings')).toBeVisible();
	await expect(page.getByRole('link', { name: /LUVU2/ })).toBeVisible();

	await page.getByLabel('Search plates').fill('GR8*');
	await expect(page.getByRole('link', { name: /LUVU2/ })).toBeHidden();
	await page.getByRole('link', { name: /GR8FUL/ }).first().click();

	await expect(page).toHaveURL(/\/plates\/\d+$/);
	await expect(page.getByText('first logged by alex')).toBeVisible();
	await expect(page.getByText('Oct 9, 2026').first()).toBeVisible();
});

test('a deleted plate comes back when its photo is uploaded again', async () => {
	await page.getByRole('button', { name: 'Delete' }).click();
	await page.getByRole('button', { name: 'Delete plate' }).click();
	await expect(page).toHaveURL(/\/plates$/);
	await expect(page.getByText('0 plates · 0 sightings')).toBeVisible(); // the GR8* search is still on
	await page.getByRole('button', { name: 'Clear search' }).click();
	await expect(page.getByText('1 plate · 1 sighting')).toBeVisible();

	await page.goto('/upload');
	await page.getByRole('button', { name: 'Clear finished' }).click();
	await page.locator('input[type=file]').setInputFiles(PLATE_PHOTO);
	await expect(page.getByText(/Read GR8FUL/)).toBeVisible({ timeout: 45_000 });

	await page.goto('/plates');
	await expect(page.getByText('2 plates · 2 sightings')).toBeVisible();
});

test('sign out and back in', async () => {
	await page.getByRole('button', { name: 'Sign out' }).click();
	await expect(page).toHaveURL(/\/login/);
	await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
	await page.getByLabel('Username').fill('alex');
	await page.getByLabel('Password').fill('wrong-password');
	await page.getByRole('button', { name: 'Sign in' }).click();
	await expect(page.getByRole('alert')).toBeVisible();

	await page.getByLabel('Password').fill('password123');
	await page.getByRole('button', { name: 'Sign in' }).click();
	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByText(/2 photos/)).toBeVisible();
});
