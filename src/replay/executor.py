import os
import uuid

from playwright.async_api import async_playwright, Page

from src.artifact.schema import (
    ActionStep,
    CapabilityArtifact,
    LocatorStrategy,
    ReplayResult,
    SuccessCondition,
)
from src.agent.actions import substitute_params
from src.safety.guardrails import assert_safe
from src.logger import RunLogger


# ---------------------------------------------------------------------------
# Known business outcomes
# ---------------------------------------------------------------------------

BUSINESS_OUTCOMES = {
    "member_not_found": ["No member record found", "Member Not Found"],
    "permission_denied": ["Access Denied", "Unauthorized"],
    "session_expired":   ["Session expired", "Please log in again"],
}


async def _detect_business_outcome(page: Page):
    """Check if the current page shows a known business outcome."""
    try:
        body = await page.inner_text("body")
        body_lower = body.lower()

        for key, signals in BUSINESS_OUTCOMES.items():
            if any(s.lower() in body_lower for s in signals):
                return key

        # URL-based detection
        if "/lookup" in page.url and "not found" in body_lower:
            return "member_not_found"

    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Locator resolution with fallbacks
# ---------------------------------------------------------------------------

async def _resolve_with_fallbacks(page: Page, locator: LocatorStrategy, timeout: int = 5000):
    """Try primary locator first, then each fallback. Raises if nothing works."""
    strategies = [locator.primary] + locator.fallbacks

    for strategy in strategies:
        try:
            prefix, _, selector = strategy.partition(":")
            if prefix == "css":
                el = page.locator(selector)
            elif prefix == "xpath":
                el = page.locator(f"xpath={selector}")
            elif prefix == "text":
                el = page.get_by_text(selector, exact=False)
            elif prefix == "name":
                el = page.locator(f"[name='{selector}']")
            else:
                el = page.locator(strategy)

            await el.wait_for(state="visible", timeout=timeout)
            return el

        except Exception:
            continue

    raise RuntimeError(
        f"Could not locate element after trying {len(strategies)} strategies. "
        f"Description: {locator.description}"
    )


# ---------------------------------------------------------------------------
# Success condition check
# ---------------------------------------------------------------------------

async def _check_success(page: Page, condition: SuccessCondition) -> bool:
    try:
        if condition.type == "url_contains":
            return condition.value in page.url
        elif condition.type == "element_exists":
            return await page.locator(condition.value).count() > 0
        elif condition.type == "text_present":
            body = await page.inner_text("body")
            return condition.value.lower() in body.lower()
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# Single step execution
# ---------------------------------------------------------------------------

async def _execute_step(
    page: Page,
    step: ActionStep,
    params: dict,
    logger: RunLogger,
    step_num: int,
):
    assert_safe(step.action, page.url, step.value or "")
    value = substitute_params(step.value or "", params)

    try:
        if step.action == "navigate":
            await page.goto(value, timeout=10000)
            await page.wait_for_load_state("networkidle", timeout=5000)

        elif step.action == "click":
            el = await _resolve_with_fallbacks(page, step.locator)
            await el.click()
            # Wait for page to fully load after click (critical for form submissions)
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                await page.wait_for_timeout(2000)

        elif step.action == "type":
            el = await _resolve_with_fallbacks(page, step.locator)
            await el.fill(value)

        elif step.action == "read":
            el = await _resolve_with_fallbacks(page, step.locator)
            await el.wait_for(state="visible", timeout=5000)

        elif step.action == "assert":
            body = await page.inner_text("body")
            if value and value.lower() not in body.lower():
                raise AssertionError(f"Expected '{value}' not found on page.")

        elif step.action == "wait":
            await page.wait_for_timeout(2000)

        # Check for business outcomes AFTER page fully loads
        outcome = await _detect_business_outcome(page)
        if outcome:
            logger.info("business_outcome_detected", outcome=outcome, step=step_num)
            return outcome

        # Verify checkpoint — skip unsupported jQuery-style selectors
        if step.checkpoint:
            if ":contains(" in step.checkpoint:
                logger.warn(
                    "checkpoint_skipped",
                    reason="unsupported :contains() selector",
                    checkpoint=step.checkpoint,
                )
            else:
                try:
                    await page.wait_for_selector(step.checkpoint, timeout=5000)
                except Exception:
                    outcome = await _detect_business_outcome(page)
                    if outcome:
                        return outcome
                    raise RuntimeError(
                        f"Checkpoint '{step.checkpoint}' not found after step {step_num} ({step.action})"
                    )

    except (RuntimeError, AssertionError):
        raise

    except Exception as e:
        if step.on_error == "retry":
            logger.warn("retrying_step", step_num=step_num, error=str(e))
            await page.wait_for_timeout(2000)
            return await _execute_step(page, step, params, logger, step_num)
        raise RuntimeError(f"Step {step_num} ({step.action}) failed: {e}")

    return None


# ---------------------------------------------------------------------------
# Main replay entry point
# ---------------------------------------------------------------------------

async def replay_artifact(
    artifact: CapabilityArtifact,
    params: dict,
) -> ReplayResult:
    """Replay a saved artifact deterministically. No LLM involved."""
    run_id   = f"replay_{str(uuid.uuid4())[:8]}"
    logger   = RunLogger(run_id, mode="replay")
    headless = os.getenv("HEADLESS", "false").lower() == "true"

    logger.info(
        "replay_start",
        artifact_id=artifact.artifact_id,
        artifact_name=artifact.name,
        params=list(params.keys()),
    )

    result = ReplayResult(status="hard_failure")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page    = await browser.new_page()

        try:
            await page.goto(artifact.target_url, timeout=10000)

            for i, step in enumerate(artifact.steps, start=1):
                logger.step(i, step.action, step.description)

                try:
                    outcome = await _execute_step(page, step, params, logger, i)
                except RuntimeError as e:
                    shot = logger.screenshot_path(f"failure_step_{i:02d}")
                    await page.screenshot(path=shot)
                    result.failed_step_id  = step.step_id
                    result.error_detail    = str(e)
                    result.screenshot_path = shot
                    logger.error("hard_failure", step=i, error=str(e))
                    return result

                if outcome:
                    result.status           = "business_outcome"
                    result.business_outcome = outcome
                    return result

                await page.screenshot(path=logger.screenshot_path(f"step_{i:02d}"))

            # ---------------------------------------------------------------
            # All steps done — final business outcome check before success
            # ---------------------------------------------------------------
            final_outcome = await _detect_business_outcome(page)
            if final_outcome:
                result.status           = "business_outcome"
                result.business_outcome = final_outcome
                logger.info("business_outcome_at_end", outcome=final_outcome)
                return result

            # Verify overall success condition
            if not await _check_success(page, artifact.success_condition):
                result.error_detail = (
                    f"Success condition not met: "
                    f"{artifact.success_condition.type} = '{artifact.success_condition.value}'"
                )
                logger.error("success_condition_failed", detail=result.error_detail)
                return result

            result.status = "success"
            logger.success()

        except Exception as e:
            shot = logger.screenshot_path("unexpected_error")
            try:
                await page.screenshot(path=shot)
            except Exception:
                pass
            result.error_detail    = str(e)
            result.screenshot_path = shot
            logger.error("unexpected_error", error=str(e))

        finally:
            await browser.close()

    return result