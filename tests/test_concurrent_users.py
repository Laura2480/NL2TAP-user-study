"""
Test di concorrenza -- apre N finestre browser in griglia contro l'app Streamlit.

Prerequisiti:
  1. L'app Streamlit deve essere in esecuzione:
       streamlit run src/evaluation/Home.py
  2. Playwright installato:
       pip install playwright && playwright install chromium

Uso:
  python tests/test_concurrent_users.py              # 10 utenti, griglia visibile
  python tests/test_concurrent_users.py --users 5    # 5 utenti
  python tests/test_concurrent_users.py --headless   # senza finestre
  python tests/test_concurrent_users.py --port 8502  # porta custom
  python tests/test_concurrent_users.py --start 4001 # range debug
"""

import argparse
import asyncio
import math
import time
from dataclasses import dataclass
from typing import List, Optional

from playwright.async_api import async_playwright, Browser, Page, BrowserContext


# -- Defaults ---------------------------------------------------------
DEFAULT_URL = "http://localhost:8501"
ACCESS_CODE = "STUDY2026"
SCREEN_W, SCREEN_H = 1920, 1080


@dataclass
class UserResult:
    user_id: str
    ok: bool = False
    phase: str = "init"
    elapsed: float = 0.0
    error: str = ""
    intent_sent: bool = False


# -- Helpers ----------------------------------------------------------

def _grid_layout(total: int, screen_w: int = SCREEN_W, screen_h: int = SCREEN_H):
    """Calcola cols/rows/cell size per disporre N finestre a griglia."""
    cols = math.ceil(math.sqrt(total))
    rows = math.ceil(total / cols)
    cell_w = screen_w // cols
    cell_h = screen_h // rows
    return cols, rows, cell_w, cell_h


def _grid_rect(index: int, total: int, screen_w: int = SCREEN_W, screen_h: int = SCREEN_H):
    """Restituisce (x, y, w, h) per la cella index-esima della griglia."""
    cols, rows, cell_w, cell_h = _grid_layout(total, screen_w, screen_h)
    col = index % cols
    row = index // cols
    return col * cell_w, row * cell_h, cell_w, cell_h


def _print(text: str = ""):
    """Print safe for Windows cp1252 console."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


async def _position_window(page: Page, x: int, y: int, w: int, h: int):
    """Posiziona la finestra del browser usando il Chrome DevTools Protocol."""
    cdp = await page.context.new_cdp_session(page)
    # Ottieni windowId per il target corrente
    resp = await cdp.send("Browser.getWindowForTarget")
    window_id = resp["windowId"]
    # Imposta posizione e dimensione
    await cdp.send("Browser.setWindowBounds", {
        "windowId": window_id,
        "bounds": {
            "left": x, "top": y,
            "width": max(w, 400), "height": max(h, 300),
            "windowState": "normal",
        },
    })
    await cdp.detach()


async def _wait_for_streamlit(page: Page, timeout: float = 30_000):
    """Attende che Streamlit finisca il caricamento iniziale."""
    await page.wait_for_selector(
        '[data-testid="stAppViewContainer"]',
        state="visible",
        timeout=timeout,
    )
    await page.wait_for_timeout(1200)


async def _wait_for_rerun(page: Page, ms: int = 3000):
    """Wait for a Streamlit rerun cycle to settle."""
    await page.wait_for_timeout(ms)


async def _is_on_studio(page: Page) -> bool:
    """Check if the page has navigated to Studio (scenario nav visible)."""
    try:
        loc = page.locator('.sc-nav, textarea, [data-testid="stForm"]')
        await loc.first.wait_for(state="visible", timeout=3_000)
        return True
    except Exception:
        return False


# -- Single-user flow -------------------------------------------------

async def run_single_user(
    browser: Browser,
    index: int,
    user_num: int,
    base_url: str,
    total_users: int,
    send_intent: bool = True,
    stagger_ms: int = 0,
    headless: bool = False,
) -> UserResult:
    """Esegue il flusso completo per un singolo utente."""
    user_id = f"user_{user_num}"
    result = UserResult(user_id=user_id)
    t0 = time.monotonic()

    try:
        # Stagger start to reduce thundering herd on Streamlit
        if stagger_ms > 0:
            await asyncio.sleep(stagger_ms / 1000.0)

        # Grid cell for this user
        x, y, w, h = _grid_rect(index, total_users)

        # Create isolated context + page
        context = await browser.new_context(
            viewport={"width": max(w - 16, 400), "height": max(h - 80, 300)},
        )
        page = await context.new_page()

        # Position the window in the grid (only works in non-headless Chromium)
        if not headless:
            try:
                await _position_window(page, x, y, w, h)
            except Exception:
                pass  # CDP positioning may fail in some envs, not critical

        # -- Phase 1: navigate to Home --
        result.phase = "navigate"
        _print(f"  [{user_id}] navigating...")
        await page.goto(base_url, wait_until="domcontentloaded")
        await _wait_for_streamlit(page, timeout=45_000)

        # -- Phase 2: login --
        result.phase = "login"
        _print(f"  [{user_id}] logging in...")

        username_input = page.locator(
            'input[aria-label="Nome utente"], input[aria-label="Username"]'
        )
        await username_input.first.wait_for(state="visible", timeout=10_000)
        await username_input.first.fill(user_id)

        password_input = page.locator(
            'input[aria-label="Codice di accesso"], input[aria-label="Access code"]'
        )
        await password_input.first.fill(ACCESS_CODE)

        login_btn = page.locator(
            'button:has-text("Accedi"), button:has-text("Log in")'
        )
        await login_btn.first.click()
        await _wait_for_rerun(page, 4000)

        # -- Phase 3: start study or already on Studio --
        result.phase = "start_study"

        if await _is_on_studio(page):
            _print(f"  [{user_id}] already on Studio (returning user)")
        else:
            start_btn = page.locator(
                'button:has-text("Inizia lo studio"), '
                'button:has-text("Start the study"), '
                'button:has-text("Riprendi lo studio"), '
                'button:has-text("Resume the study")'
            )
            await start_btn.first.wait_for(state="visible", timeout=15_000)
            await start_btn.first.click()
            _print(f"  [{user_id}] clicked Start...")
            await _wait_for_rerun(page, 5000)

        # -- Phase 4: Studio page loaded --
        result.phase = "studio_loaded"
        _print(f"  [{user_id}] waiting for Studio...")

        await page.wait_for_selector(
            '.sc-nav, textarea, [data-testid="stForm"]',
            state="visible",
            timeout=20_000,
        )
        _print(f"  [{user_id}] Studio loaded OK")

        # -- Phase 5: (optional) send an intent --
        if send_intent:
            result.phase = "send_intent"

            text_area = page.locator('textarea').first
            await text_area.wait_for(state="visible", timeout=10_000)

            test_intent = (
                f"[TEST user {user_num}] When the temperature is below 10 degrees, "
                "send me a notification with the current temperature."
            )
            await text_area.fill(test_intent)
            await page.wait_for_timeout(500)

            send_btn = page.locator('button[type="submit"]').first
            await send_btn.click()
            _print(f"  [{user_id}] intent sent, waiting for response...")

            try:
                spinner = page.locator('[data-testid="stSpinner"], .stSpinner')
                try:
                    await spinner.first.wait_for(state="visible", timeout=5_000)
                    await spinner.first.wait_for(state="hidden", timeout=90_000)
                except Exception:
                    await page.wait_for_timeout(3000)
                result.intent_sent = True
            except Exception:
                result.intent_sent = False

        result.phase = "done"
        result.ok = True

    except Exception as e:
        err_msg = str(e).split("\n")[0][:120]
        result.error = f"[{result.phase}] {type(e).__name__}: {err_msg}"

    result.elapsed = time.monotonic() - t0
    return result


# -- Main orchestrator ------------------------------------------------

async def run_concurrent_test(
    n_users: int = 10,
    base_url: str = DEFAULT_URL,
    headless: bool = False,
    send_intent: bool = True,
    slow_mo: int = 0,
    stagger_ms: int = 500,
    start_id: int = 2001,
):
    """Lancia N utenti in parallelo e riporta i risultati."""
    end_id = start_id + n_users - 1
    cols, rows, cw, ch = _grid_layout(n_users)
    _print(f"\n{'='*60}")
    _print(f"  TEST CONCORRENZA -- {n_users} utenti simultanei")
    _print(f"  Range: user_{start_id} .. user_{end_id}")
    _print(f"  Griglia: {cols}x{rows}  (celle {cw}x{ch} px)")
    _print(f"  URL: {base_url}")
    _print(f"  Headless: {headless}  |  Stagger: {stagger_ms}ms")
    _print(f"  Send intent: {send_intent}")
    _print(f"{'='*60}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # Launch all users concurrently
        t_start = time.monotonic()
        tasks = [
            run_single_user(
                browser=browser,
                index=i,
                user_num=start_id + i,
                base_url=base_url,
                total_users=n_users,
                send_intent=send_intent,
                stagger_ms=i * stagger_ms,
                headless=headless,
            )
            for i in range(n_users)
        ]
        results: List[UserResult] = await asyncio.gather(*tasks)
        t_total = time.monotonic() - t_start

        # -- Report --
        _print(f"\n{'='*60}")
        _print(f"  RISULTATI")
        _print(f"{'='*60}\n")

        ok_count = sum(1 for r in results if r.ok)
        fail_count = n_users - ok_count

        for r in results:
            status = "OK" if r.ok else "FAIL"
            intent_tag = " [intent sent]" if r.intent_sent else ""
            err_tag = f" -- {r.error}" if r.error else ""
            _print(f"  {r.user_id:>12s}  {status:>4s}  {r.elapsed:6.1f}s  "
                   f"phase={r.phase}{intent_tag}{err_tag}")

        _print(f"\n  {'-'*50}")
        _print(f"  Successi: {ok_count}/{n_users}")
        _print(f"  Falliti:  {fail_count}/{n_users}")
        _print(f"  Tempo totale: {t_total:.1f}s")
        _print()

        # Lascia le finestre aperte per ispezione
        if not headless:
            _print("  Le finestre restano aperte. Premi INVIO per chiudere...")
            try:
                await asyncio.get_event_loop().run_in_executor(None, input)
            except EOFError:
                _print("  (stdin non interattivo, chiusura in 10s...)")
                await asyncio.sleep(10)

        await browser.close()

    return results


# -- CLI --------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Test di concorrenza multi-utente per NL2TAP"
    )
    parser.add_argument(
        "--users", "-n", type=int, default=10,
        help="Numero di utenti simultanei (default: 10)"
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8501,
        help="Porta Streamlit (default: 8501)"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Esegui senza finestre visibili"
    )
    parser.add_argument(
        "--no-intent", action="store_true",
        help="Non inviare intent (solo login + navigazione)"
    )
    parser.add_argument(
        "--slow-mo", type=int, default=0,
        help="Rallenta ogni azione di N ms (per debug)"
    )
    parser.add_argument(
        "--stagger", type=int, default=500,
        help="Ritardo tra avvio utenti in ms (default: 500)"
    )
    parser.add_argument(
        "--start", type=int, default=2001,
        help="ID primo utente, es. 2001 -> user_2001..user_2010 (default: 2001)"
    )

    args = parser.parse_args()
    base_url = f"http://localhost:{args.port}"

    asyncio.run(
        run_concurrent_test(
            n_users=args.users,
            base_url=base_url,
            headless=args.headless,
            send_intent=not args.no_intent,
            slow_mo=args.slow_mo,
            stagger_ms=args.stagger,
            start_id=args.start,
        )
    )


if __name__ == "__main__":
    main()
