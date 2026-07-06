# ruff: noqa
import re
import os
import json
import logging
from pydantic import BaseModel, Field
from typing import Any, AsyncGenerator

import sys
from google.adk.agents import Agent, LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.workflow import Workflow, START
from google.adk.tools import AgentTool
from google.adk.models import Gemini
from google.genai import types

# MCP imports
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .config import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize LLM model from config
llm_model = Gemini(model=config.model)

# Setup MCP Toolset with robust path resolution
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[os.path.join(os.path.dirname(__file__), "mcp_server.py")],
        ),
    )
)

# Define sub-agents with MCP tools wired in
flight_agent = LlmAgent(
    name="flight_agent",
    model=llm_model,
    instruction="""You are a flight preferences specialist. Help coordinate flight options, preferences (cabin class, layovers, airlines), and retrieve sample flight details using the get_flight_deals tool. 
    Always ask or confirm details if something is missing. Be brief and concise.""",
    tools=[mcp_toolset],
    description="Handles flight preferences, layover options, cabin classes, and flight queries.",
)

hotel_agent = LlmAgent(
    name="hotel_agent",
    model=llm_model,
    instruction="""You are a hotel and lodging specialist. Help coordinate accommodation options, neighborhood vibes, budget, and amenities using the get_hotel_recommendations tool. 
    Always check preferences and suggest matches. Be brief and concise.""",
    tools=[mcp_toolset],
    description="Handles hotel searches, lodging options, neighborhood preferences, and accommodation queries.",
)

# Define orchestrator agent
orchestrator_agent = LlmAgent(
    name="orchestrator_agent",
    model=llm_model,
    instruction="""You are the main travel planning orchestrator for Loka. 
    Your goal is to coordinate with the flight_agent and hotel_agent to draft a comprehensive travel itinerary.
    Check the current context and state for any user preferences or feedback.
    If you need flight details, delegate to flight_agent.
    If you need hotel details, delegate to hotel_agent.
    When you have gathered enough information, draft a complete itinerary with flights and lodging.
    Be concise.""",
    tools=[AgentTool(flight_agent), AgentTool(hotel_agent)],
    description="The main orchestrator that coordinates with flight and hotel specialists to create a travel itinerary.",
)

# Workflow Function Nodes

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Checks the user input for PII, prompt injections, and domain restrictions."""
    # Extract text from input
    text = ""
    if isinstance(node_input, str):
        text = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        text = "".join(part.text for part in node_input.parts if part.text)
    
    scrubbed_text = text
    
    # 1. PII Scrubbing
    if config.pii_redaction_enabled:
        email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
        phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
        scrubbed_text = re.sub(email_pattern, "[EMAIL_REDACTED]", scrubbed_text)
        scrubbed_text = re.sub(phone_pattern, "[PHONE_REDACTED]", scrubbed_text)
        
    # 2. Prompt Injection Keyword Detection
    has_injection = False
    injection_keywords = ["ignore previous instructions", "override instruction", "system prompt", "ignore instructions"]
    if config.injection_detection_enabled:
        for keyword in injection_keywords:
            if keyword in scrubbed_text.lower():
                has_injection = True
                break
                
    # 3. Domain-specific rule (e.g. content safety check)
    blacklisted_topics = ["weapon", "bomb", "hacking", "exploit"]
    has_blocked_topic = any(topic in scrubbed_text.lower() for topic in blacklisted_topics)
    
    # 4. Structured JSON Audit Log
    log_payload = {
        "event": "security_scan",
        "pii_detected": scrubbed_text != text,
        "injection_detected": has_injection,
        "blocked_topic_detected": has_blocked_topic,
        "severity": "CRITICAL" if (has_injection or has_blocked_topic) else ("WARNING" if scrubbed_text != text else "INFO")
    }
    logger.info(f"AUDIT_LOG: {json.dumps(log_payload)}")
    
    if has_injection or has_blocked_topic:
        return Event(output="Security checkpoint violation.", route="security_event")
        
    return Event(output=scrubbed_text, route="pass")


async def approval_node(ctx: Context, node_input: Any) -> AsyncGenerator[Event, None]:
    """Asks for human-in-the-loop approval of the drafted itinerary, handles feedback."""
    draft_text = ""
    if isinstance(node_input, str):
        draft_text = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        draft_text = "".join(part.text for part in node_input.parts if part.text)
        
    # Save current draft to context state
    ctx.state["draft_itinerary"] = draft_text
    
    # If we are resuming, check the user's feedback response
    if ctx.resume_inputs and "approve_itinerary" in ctx.resume_inputs:
        user_response = ctx.resume_inputs["approve_itinerary"].strip()
        if user_response.lower() in ["yes", "approve", "y", "looks good"]:
            yield Event(output=draft_text, route="approve")
            return
        else:
            # Save feedback for orchestrator and route to revision
            ctx.state["feedback"] = user_response
            yield Event(output=f"User feedback for revision: {user_response}", route="revise")
            return
            
    # Yield RequestInput to pause execution for human-in-the-loop approval
    yield RequestInput(
        interrupt_id="approve_itinerary",
        message=f"Draft Itinerary:\n{draft_text}\n\nDo you approve this itinerary? (Reply 'yes' or describe the changes you want)."
    )


def final_output(node_input: str) -> str:
    """Formats and returns the final approved itinerary."""
    return f"🎉 Final Approved Itinerary:\n\n{node_input}"


def security_failure(node_input: str) -> str:
    """Returns a security failure notification."""
    return "🚨 Request blocked by Security Checkpoint: Security violation detected."


# Construct the ADK 2.0 Workflow Graph
workflow_agent = Workflow(
    name="loka_travel_workflow",
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {"pass": orchestrator_agent, "security_event": security_failure}),
        (orchestrator_agent, approval_node),
        (approval_node, {"revise": orchestrator_agent, "approve": final_output}),
    ],
    description="A multi-agent travel planner workflow with a security checkpoint and human-in-the-loop approval.",
)

# Instantiate the App
app = App(
    name="app",
    root_agent=workflow_agent,
    resumability_config=ResumabilityConfig(is_resumable=True)
)
