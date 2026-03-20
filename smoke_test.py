#!/usr/bin/env python3
"""
Smoke tests for the B2B AI automation platform at http://localhost:5173

Strategy:
- Register a fresh test user via the backend API to get a valid JWT.
- Inject the token into localStorage via add_init_script so the React app
  sees an authenticated session without going through Azure AD SSO.
- Run all smoke checks against the authenticated app.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from playwright.async_api import async_playwright, Page, ConsoleMessage
import urllib.request

BASE_URL = "http://localhost:5173"
API_URL  = "http://localhost:8000/api/v1"
SCREENSHOT_DIR = Path("/tmp/smoke_tests")
SCREENSHOT_DIR.mkdir(exist_ok=True)

console_errors: dict[str, list[str]] = {}


def api_register() -> tuple[str, str]:
    """Create a fresh test account and return (access_token, refresh_token)."""
    import random, string
    rnd = "".join(random.choices(string.ascii_lowercase, k=6))
    payload = json.dumps({
        "email": f"smoketest_{rnd}@test.internal",
        "password": "SmokeTest123",
        "full_name": "Smoke Test",
    }).encode()
    req = urllib.request.Request(
        f"{API_URL}/auth/register",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["access_token"], data["refresh_token"]


def make_console_handler(page_name: str):
    errors: list[str] = []
    console_errors[page_name] = errors
    def handler(msg: ConsoleMessage):
        if msg.type == "error":
            errors.append(msg.text)
    return handler


async def screenshot(page: Page, name: str) -> str:
    path = str(SCREENSHOT_DIR / f"{name}.png")
    await page.screenshot(path=path, full_page=True)
    return path


async def run_tests():
    results: list[dict] = []

    # ── Obtain auth tokens ───────────────────────────────────────────────────
    print("[AUTH] Registering smoke-test user via backend API...")
    try:
        access_token, refresh_token = api_register()
        print(f"       Access token: {access_token[:30]}…")
    except Exception as exc:
        print(f"       FAILED to register: {exc}")
        results.append({"test": "Backend auth setup", "error": str(exc), "pass": False})
        print_summary(results)
        return

    # localStorage injection script — runs before each page load
    inject_auth_js = f"""
    localStorage.setItem('auth-token', '{access_token}');
    localStorage.setItem('refresh-token', '{refresh_token}');
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        # Inject tokens on every new page/navigation before any scripts run
        await context.add_init_script(inject_auth_js)
        page = await context.new_page()

        # ── 1. Load check ────────────────────────────────────────────────────
        print("\n[1] Load check — navigating to http://localhost:5173 …")
        page.on("console", make_console_handler("home"))
        await page.goto(BASE_URL, wait_until="networkidle", timeout=20000)
        await screenshot(page, "01_home")
        title = await page.title()
        url   = page.url
        print(f"    Title: {title!r}")
        print(f"    URL:   {url}")
        page_loads = title != "" and "error" not in title.lower()
        results.append({"test": "Load check", "url": url, "title": title, "pass": page_loads})

        # ── 2. Login page ────────────────────────────────────────────────────
        print("\n[2] Login page — checking for Microsoft/Azure AD button...")
        # Navigate to /login directly to inspect the login UI
        login_page = await context.new_page()
        login_page.on("console", make_console_handler("login_direct"))
        await login_page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=15000)
        await screenshot(login_page, "02_login")

        body_text = await login_page.inner_text("body")
        lower = body_text.lower()
        ms_btn = await login_page.query_selector(
            "button:has-text('Microsoft'), "
            "a:has-text('Microsoft'), "
            "button:has-text('Sign in with Microsoft'), "
            "[aria-label*='Microsoft' i], "
            "[class*='microsoft' i], "
            "[class*='azure' i]"
        )
        has_ms_text = "microsoft" in lower or "azure" in lower or "sign in" in lower or "continue with microsoft" in lower

        if ms_btn:
            btn_text = (await ms_btn.inner_text()).strip()
            print(f"    Microsoft button found: YES  — text: {btn_text!r}")
        else:
            print(f"    Microsoft button found: NO  (text-based check: {has_ms_text})")

        results.append({
            "test": "Microsoft/Azure AD login button",
            "button_element_found": ms_btn is not None,
            "ms_text_present": has_ms_text,
            "pass": ms_btn is not None or has_ms_text,
        })
        await login_page.close()

        # ── 3. Navigation — main tabs ─────────────────────────────────────────
        tabs = [
            ("marketing",   "/marketing"),
            ("sales",       "/sales"),
            ("operations",  "/operations"),
            ("finance",     "/finance"),
            ("admin",       "/admin"),
            ("connections", "/connections"),
        ]

        print("\n[3] Tab navigation...")
        for tab_name, path in tabs:
            print(f"\n    Tab: {tab_name}  →  {path}")
            page.on("console", make_console_handler(tab_name))
            try:
                await page.goto(f"{BASE_URL}{path}", wait_until="networkidle", timeout=20000)
                await screenshot(page, f"03_{tab_name}")
                tab_url     = page.url
                tab_content = await page.inner_text("body")
                error_visible = any(
                    kw in tab_content.lower()
                    for kw in ["500 internal", "error occurred", "something went wrong",
                               "cannot get", "unexpected error"]
                )
                redirected_to_login = "login" in tab_url
                print(f"      URL:            {tab_url}")
                print(f"      Visible error:  {error_visible}")
                print(f"      Login redirect: {redirected_to_login}")
                results.append({
                    "test": f"Tab: {tab_name}",
                    "url":  tab_url,
                    "visible_error":    error_visible,
                    "login_redirect":   redirected_to_login,
                    "pass": not error_visible and not redirected_to_login,
                })
            except Exception as exc:
                print(f"      ERROR: {exc}")
                results.append({"test": f"Tab: {tab_name}", "error": str(exc), "pass": False})

        # ── 4. Connections page — platform list ───────────────────────────────
        print("\n[4] Connections page — platform list check...")
        await page.goto(f"{BASE_URL}/connections", wait_until="networkidle", timeout=20000)
        await screenshot(page, "04_connections_detail")
        conn_text = (await page.inner_text("body")).lower()

        expected_conn = [
            ("Google Business", "google business"),
            ("Google Ads",      "google ads"),
            ("Meta (FB + IG)",  "meta"),
            ("Bing Ads",        "bing ads"),
            ("LinkedIn",        "linkedin"),
        ]
        dead_conn = [
            ("Twitter",    "twitter"),
            ("TikTok",     "tiktok"),
            ("Pinterest",  "pinterest"),
            ("Snapchat",   "snapchat"),
            ("Reddit",     "reddit"),
            ("ngrok",      "ngrok"),
            ("Claude CLI", "claude cli"),
        ]

        conn_results = []
        for name, keyword in expected_conn:
            found  = keyword in conn_text
            status = "FOUND   " if found else "MISSING"
            print(f"    [{status}] {name}  (expected)")
            conn_results.append({"platform": name, "expected": True,  "found": found, "pass": found})

        for name, keyword in dead_conn:
            found  = keyword in conn_text
            status = "PRESENT (BAD)" if found else "absent  (OK) "
            print(f"    [{status}] {name}  (should NOT appear)")
            conn_results.append({"platform": name, "expected": False, "found": found, "pass": not found})

        all_conn_pass = all(r["pass"] for r in conn_results)
        results.append({"test": "Connections — platform list", "details": conn_results, "pass": all_conn_pass})

        # ── 5. Marketing page — platform list ────────────────────────────────
        print("\n[5] Marketing page — platform list check...")
        await page.goto(f"{BASE_URL}/marketing", wait_until="networkidle", timeout=20000)
        await screenshot(page, "05_marketing_detail")
        mkt_text = (await page.inner_text("body")).lower()

        expected_mkt = [
            ("Google Ads", "google ads"),
            ("Bing Ads",   "bing ads"),
            ("Meta",       "meta"),
            ("LinkedIn",   "linkedin"),
        ]
        banned_mkt = [
            ("YouTube",        "youtube"),
            ("Analytics",      "google analytics"),
            ("Search Console", "search console"),
            ("Yelp",           "yelp"),
        ]

        mkt_results = []
        for name, keyword in expected_mkt:
            found  = keyword in mkt_text
            status = "FOUND   " if found else "MISSING"
            print(f"    [{status}] {name}  (expected)")
            mkt_results.append({"platform": name, "expected": True,  "found": found, "pass": found})

        for name, keyword in banned_mkt:
            found  = keyword in mkt_text
            status = "PRESENT (BAD)" if found else "absent  (OK) "
            print(f"    [{status}] {name}  (should NOT appear)")
            mkt_results.append({"platform": name, "expected": False, "found": found, "pass": not found})

        all_mkt_pass = all(r["pass"] for r in mkt_results)
        results.append({"test": "Marketing — platform list", "details": mkt_results, "pass": all_mkt_pass})

        # ── 6. Admin page — no WhatsApp ───────────────────────────────────────
        print("\n[6] Admin page — WhatsApp section check...")
        await page.goto(f"{BASE_URL}/admin", wait_until="networkidle", timeout=20000)
        await screenshot(page, "06_admin_detail")
        admin_text = (await page.inner_text("body")).lower()
        has_whatsapp   = "whatsapp" in admin_text
        has_page_error = any(kw in admin_text for kw in ["500 internal", "error occurred", "something went wrong"])
        print(f"    WhatsApp section present: {has_whatsapp}")
        print(f"    Page render error:        {has_page_error}")
        results.append({
            "test": "Admin — no WhatsApp section",
            "whatsapp_present": has_whatsapp,
            "page_error":       has_page_error,
            "pass": not has_whatsapp and not has_page_error,
        })

        # ── 7. Console errors ─────────────────────────────────────────────────
        print("\n[7] Console errors across all pages:")
        any_errors = False
        error_detail = {}
        for pg_name, errs in console_errors.items():
            if errs:
                any_errors = True
                error_detail[pg_name] = errs
                print(f"    [{pg_name}]")
                for e in errs:
                    print(f"      - {e[:200]}")
        if not any_errors:
            print("    No JavaScript console errors detected.")
        results.append({
            "test": "Console errors",
            "errors": error_detail,
            "pass": not any_errors,
        })

        await browser.close()

    print_summary(results)
    with open("/tmp/smoke_tests/report.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nScreenshots : /tmp/smoke_tests/*.png")
    print(f"JSON report : /tmp/smoke_tests/report.json")


def print_summary(results: list[dict]):
    passed = failed = skipped = 0
    print("\n" + "=" * 62)
    print("SMOKE TEST SUMMARY")
    print("=" * 62)
    for r in results:
        status = r.get("pass")
        if status is True:
            icon = "PASS"; passed += 1
        elif status is False:
            icon = "FAIL"; failed += 1
        else:
            icon = "SKIP"; skipped += 1
        print(f"  [{icon}]  {r['test']}")
    print("-" * 62)
    print(f"  {passed} passed  |  {failed} failed  |  {skipped} skipped")
    print("=" * 62)


if __name__ == "__main__":
    asyncio.run(run_tests())
