"""
Observer — reads the current page state for Gemini to reason about.

We use the accessibility tree (not raw HTML) because:
- Works on legacy apps with no clean DOM or test IDs
- Semantic labels (roles, names) are better input for the LLM
- More stable than raw selectors across minor UI updates
- Same API concept works for desktop apps too
"""
from playwright.async_api import Page

async def get_page_state(page: Page) -> dict:
    url   = page.url
    title = await page.title()

    try:
        a11y = await page.accessibility.snapshot()
    except Exception:
        a11y = None

    # Body text — useful fallback for sparse legacy a11y trees
    try:
        body_text = await page.inner_text("body")
        body_text = "\n".join(l.strip() for l in body_text.splitlines() if l.strip())
    except Exception:
        body_text = ""

    # Interactive elements — tells the LLM exactly what it can act on
    try:
        interactive = await page.evaluate("""() => {
            const els = document.querySelectorAll('input,button,select,textarea,a[href]');
            return Array.from(els).slice(0, 30).map(el => ({
                tag:  el.tagName.toLowerCase(),
                type: el.type  || '',
                name: el.name  || '',
                id:   el.id    || '',
                text: (el.innerText || '').trim().slice(0, 60),
                href: el.href  || '',
            }));
        }""")
    except Exception:
        interactive = []

    return {
        "url": url,
        "title": title,
        "body_text": body_text[:3000],      # cap to keep prompts manageable
        "interactive_elements": interactive,
        "accessibility_tree": a11y,
    }