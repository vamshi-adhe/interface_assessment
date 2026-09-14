"""
Discovery agent loop — Gemini in the decision seat.
Updated to use new google-genai package.
"""
import json
import os
import re
import uuid

from google import genai
from google.genai import types
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from src.agent.actions import execute_discovery_action
from src.agent.observer import get_page_state
from src.artifact.schema import (
    CapabilityArtifact, InputParam, SuccessCondition,
)
from src.escalation.handoff import EscalationSession
from src.logger import RunLogger
from src.safety.guardrails import assert_safe

load_dotenv()

# ---------------------------------------------------------------------------
# Gemini client setup (new google-genai package)
# ---------------------------------------------------------------------------

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """You are a browser automation agent for a banking back-office system.

At each step you receive the current page state and decide ONE action.

Respond ONLY with a JSON object — no markdown, no explanation:
{
  "action": "navigate|click|type|read|assert|wait|done|escalate",
  "locator": "how to find the element — omit for navigate/wait/done/escalate",
  "value": "URL to navigate, text to type, or text to assert",
  "reason": "one sentence: why this action moves toward the goal",
  "checkpoint": "CSS selector that must exist after this step (omit if unsure)"
}

Locator format — use the most STABLE option available:
  name:field_name   ->  input by its name attribute  (BEST for legacy apps)
  text:visible text ->  element by visible text
  css:selector      ->  CSS selector
  xpath://path      ->  XPath (last resort)

Rules:
- One action per response.
- When goal is fully achieved, use action "done".
- When stuck after multiple failed attempts, use action "escalate".
- NEVER use position-based selectors as primary.
"""

# ---------------------------------------------------------------------------
# Build artifact from recorded steps
# ---------------------------------------------------------------------------

def _build_artifact(run_id, goal, target_url, steps, final_url) -> CapabilityArtifact:
    # Find all {{param_name}} templates used across steps
    param_names = set()
    for step in steps:
        if step.value:
            param_names.update(re.findall(r"\{\{(\w+)\}\}", step.value))

    input_params = {
        name: InputParam(
            name=name,
            type="string",
            description=f"Value for '{name}'",
            required=True,
        )
        for name in param_names
    }

    path = final_url.split("localhost:5000")[-1] or "/"
    success_condition = SuccessCondition(type="url_contains", value=path)
    short_name = goal[:60].replace(" ", "_").lower()

    return CapabilityArtifact(
        artifact_id=run_id,
        version="1.0",
        name=short_name,
        description=goal,
        target_url=target_url,
        surface_type="legacy_web",
        input_params=input_params,
        output_schema={},
        steps=steps,
        success_condition=success_condition,
        status="draft",
    )

# ---------------------------------------------------------------------------
# Main discovery loop
# ---------------------------------------------------------------------------

async def run_discovery(goal: str, target_url: str, params: dict) -> CapabilityArtifact:
    run_id    = str(uuid.uuid4())[:12]
    logger    = RunLogger(run_id, mode="discovery")
    headless  = os.getenv("HEADLESS", "false").lower() == "true"
    max_steps = int(os.getenv("MAX_AGENT_STEPS", "20"))

    logger.info("discovery_start", goal=goal, url=target_url)
    recorded_steps = []
    history = []   # conversation history for multi-turn context

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page    = await browser.new_page()
        await page.goto(target_url, timeout=10_000)
        final_url = target_url

        for step_num in range(1, max_steps + 1):

            # 1. Observe current page
            state = await get_page_state(page)

            # 2. Build message for Gemini
            user_msg = (
                f"Goal: {goal}\n"
                f"Parameters: {json.dumps(params)}\n"
                f"Current page:\n{json.dumps(state, indent=2, default=str)}"
            )
            history.append({
                "role": "user",
                "parts": [{"text": user_msg}]
            })

            # 3. Ask Gemini — new google-genai API
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=history,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                    ),
                )
                decision = json.loads(response.text)
                history.append({
                    "role": "model",
                    "parts": [{"text": response.text}]
                })
            except Exception as e:
                logger.error("llm_error", error=str(e))
                break

            action = decision.get("action", "")
            reason = decision.get("reason", "")
            logger.step(step_num, action, reason)

            # 4. Handle terminal states
            if action == "done":
                final_url = page.url
                logger.success(url=final_url, steps=step_num)
                break

            if action == "escalate":
                shot = logger.screenshot_path(f"step_{step_num:02d}_escalate")
                await page.screenshot(path=shot)
                session = EscalationSession(run_id)
                session.raise_intervention(goal, f"step_{step_num}", reason, shot)
                session.wait_for_resume()
                final_url = page.url
                break

            # 5. Execute the action
            try:
                step = await execute_discovery_action(page, decision, params)
                recorded_steps.append(step)
            except PermissionError as e:
                logger.error("safety_block", error=str(e))
                break
            except Exception as e:
                logger.error("action_error", error=str(e), step=step_num)
                # Don't break — let Gemini see the page and try differently

            # 6. Screenshot as evidence
            await page.screenshot(path=logger.screenshot_path(f"step_{step_num:02d}"))

        else:
            logger.warn("max_steps_reached")
            final_url = page.url

        await browser.close()

    artifact = _build_artifact(run_id, goal, target_url, recorded_steps, final_url)
    logger.info("artifact_ready", steps=len(recorded_steps))
    return artifact