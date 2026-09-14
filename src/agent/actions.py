"""
Actions — executes one LLM decision on the live browser page.

Key design: values are stored as {{param_name}} templates in the artifact,
not as resolved values. This is what makes artifacts reusable — you record
once and replay with any member_id, not just the one from discovery.
"""
import re
from playwright.async_api import Page
from src.artifact.schema import ActionStep, LocatorStrategy
from src.safety.guardrails import assert_safe, classify_risk

def substitute_params(template: str, params: dict) -> str:
    """Replace {{member_id}} with actual values at execution time."""
    return re.sub(
        r"\{\{(\w+)\}\}",
        lambda m: str(params.get(m.group(1), m.group(0))),
        template or "",
    )

def _parse_locator(locator_str: str) -> LocatorStrategy:
    """Build a LocatorStrategy from the LLM's 'prefix:value' string."""
    fallbacks = []
    if locator_str.startswith("name:"):
        attr = locator_str[5:]
        fallbacks = [f"xpath=//*[@name='{attr}']"]
    return LocatorStrategy(
        primary=locator_str,
        fallbacks=fallbacks,
        description=f"Located by: {locator_str}",
    )

def _playwright_locator(page: Page, locator_str: str):
    """Turn a prefixed locator string into a Playwright locator object."""
    if locator_str.startswith("css:"):   return page.locator(locator_str[4:])
    if locator_str.startswith("xpath:"): return page.locator(f"xpath={locator_str[6:]}")
    if locator_str.startswith("text:"):  return page.get_by_text(locator_str[5:], exact=False)
    if locator_str.startswith("name:"):  return page.locator(f"[name='{locator_str[5:]}']")
    return page.locator(locator_str)

async def execute_discovery_action(page: Page, decision: dict, params: dict) -> ActionStep:
    """Execute the LLM's decision, return a recorded ActionStep for the artifact."""
    action      = decision["action"]
    raw_value   = decision.get("value", "") or ""
    locator_str = decision.get("locator", "") or ""
    reason      = decision.get("reason", "")
    checkpoint  = decision.get("checkpoint")

    assert_safe(action, page.url, raw_value)
    risk = classify_risk(action, raw_value)
    resolved_value = substitute_params(raw_value, params)

    if action == "navigate":
        await page.goto(resolved_value, timeout=10_000)
    elif action == "click":
        el = _playwright_locator(page, locator_str)
        await el.wait_for(state="visible", timeout=5_000)
        await el.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
    elif action == "type":
        el = _playwright_locator(page, locator_str)
        await el.wait_for(state="visible", timeout=5_000)
        await el.fill(resolved_value)
    elif action == "read":
        el = _playwright_locator(page, locator_str)
        await el.wait_for(state="visible", timeout=5_000)
    elif action == "wait":
        await page.wait_for_timeout(2_000)

    return ActionStep(
        action=action,
        locator=_parse_locator(locator_str) if locator_str else None,
        value=raw_value,        # keep {{template}} form — NOT the resolved value
        checkpoint=checkpoint,
        risk=risk,
        on_error="retry" if risk == "safe" else "escalate",
        description=reason,
    )