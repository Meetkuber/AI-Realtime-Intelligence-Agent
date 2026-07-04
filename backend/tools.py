"""
tools.py — Customer Support Tool Layer (backed by SQLite)
============================================================
All tool functions now hit the real SQLite database (database.py).
Mock data is seeded on startup; refunds and tickets are persisted.
FakeStore product catalog is fetched from a real live API on first run.
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
import random

from .database import (
    db_get_order, db_create_refund, db_create_ticket,
    db_get_customer, db_record_metric,
)

# ─────────────────────────────────────────────────────────────
# Tool Functions
# ─────────────────────────────────────────────────────────────

def lookup_order(order_id: str) -> dict[str, Any]:
    """Look up an order by ID from SQLite database."""
    order = db_get_order(order_id.upper().strip())
    if not order:
        return {
            "success": False,
            "error": f"Order {order_id} not found. Please check the order ID and try again.",
        }
    return {"success": True, "order": order}


def trigger_refund(order_id: str, reason: str) -> dict[str, Any]:
    """Trigger a refund. Writes a real refund record to SQLite."""
    order = db_get_order(order_id.upper().strip())
    if not order:
        return {"success": False, "error": f"Order {order_id} not found."}

    if not order["refundable"]:
        return {
            "success": False,
            "error": (
                f"Order {order_id} cannot be refunded because it is currently '{order['status']}'. "
                "Refunds are only available for Delivered or Cancelled orders."
            ),
        }

    eta_days = 3 if order["status"] == "Delivered" else 5
    eta_date = (datetime.now() + timedelta(days=eta_days)).strftime("%B %d, %Y")
    refund_id = db_create_refund(order["id"], order["total"], reason, eta_date)

    return {
        "success": True,
        "refund_id": refund_id,
        "order_id": order["id"],
        "amount": order["total"],
        "reason": reason,
        "eta_date": eta_date,
        "eta_days": eta_days,
        "message": (
            f"Refund of ${order['total']:.2f} initiated (ID: {refund_id}). "
            f"Funds will appear in 3-5 business days by {eta_date}."
        ),
    }


def create_support_ticket(issue: str, priority: str = "normal") -> dict[str, Any]:
    """Create a real support ticket in SQLite."""
    valid_priorities = ["low", "normal", "high", "urgent"]
    priority = priority.lower() if priority else "normal"
    if priority not in valid_priorities:
        priority = "normal"

    sla_hours = {"low": 72, "normal": 24, "high": 8, "urgent": 2}[priority]
    ticket_id = db_create_ticket(issue, priority, sla_hours)

    return {
        "success": True,
        "ticket_id": ticket_id,
        "issue_summary": issue[:200],
        "priority": priority,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sla_hours": sla_hours,
        "message": (
            f"Support ticket {ticket_id} created with {priority} priority. "
            f"Our team will respond within {sla_hours} hours."
        ),
    }


def check_loyalty_points(customer_id: str) -> dict[str, Any]:
    """Check loyalty points from SQLite customers table."""
    customer = db_get_customer(customer_id.upper().strip())
    if not customer:
        return {"success": False, "error": f"Customer ID {customer_id} not found."}

    tier_benefits = {
        "Bronze":   "5% discount on orders",
        "Silver":   "10% discount + free standard shipping",
        "Gold":     "15% discount + free express shipping + priority support",
        "Platinum": "20% discount + free overnight shipping + dedicated agent",
    }

    return {
        "success": True,
        "customer_id": customer["id"],
        "name": customer["name"],
        "points": customer["points"],
        "tier": customer["tier"],
        "tier_benefit": tier_benefits.get(customer["tier"], "Standard benefits"),
        "points_expiry": customer["points_expiry"],
        "points_value_usd": round(customer["points"] * 0.01, 2),
    }


def escalate_to_human(reason: str) -> dict[str, Any]:
    """Escalate the conversation to a human agent."""
    queue_position = random.randint(1, 8)
    wait_minutes = queue_position * 3

    return {
        "success": True,
        "escalated": True,
        "reason": reason,
        "queue_position": queue_position,
        "estimated_wait_minutes": wait_minutes,
        "message": (
            f"I'm connecting you to a human agent now. "
            f"You are position #{queue_position} in the queue. "
            f"Estimated wait: {wait_minutes} minutes."
        ),
    }


# ─────────────────────────────────────────────────────────────
# Tool Registry
# ─────────────────────────────────────────────────────────────

TOOL_FUNCTIONS: dict[str, Any] = {
    "lookup_order": lookup_order,
    "trigger_refund": trigger_refund,
    "create_support_ticket": create_support_ticket,
    "check_loyalty_points": check_loyalty_points,
    "escalate_to_human": escalate_to_human,
}


def execute_tool(name: str, args: dict) -> dict:
    """Dispatch a tool call by name with given arguments."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"success": False, "error": f"Unknown tool: {name}"}
    try:
        result = fn(**args)
        db_record_metric("tool_call", name, None, result.get("success", True))
        return result
    except Exception as exc:
        db_record_metric("tool_call", name, None, False)
        return {"success": False, "error": f"Tool execution error: {exc}"}


# ─────────────────────────────────────────────────────────────
# Gemini Function Declarations
# ─────────────────────────────────────────────────────────────

GEMINI_TOOLS = [
    {
        "name": "lookup_order",
        "description": (
            "Look up a customer order by its order ID (e.g. ORD-1234). "
            "Returns order status, items, tracking info, and delivery date."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID, e.g. ORD-1234"}
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "trigger_refund",
        "description": (
            "Initiate a refund for a delivered or cancelled order. "
            "Returns a refund confirmation ID and estimated timeline. "
            "Writes a real refund record to the database."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID to refund"},
                "reason": {
                    "type": "string",
                    "description": "Reason: damaged, wrong_item, not_delivered, changed_mind, quality_issue",
                },
            },
            "required": ["order_id", "reason"],
        },
    },
    {
        "name": "create_support_ticket",
        "description": (
            "Create a support ticket for issues that require follow-up. "
            "Persists to database. Use when the problem cannot be resolved immediately."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "issue": {"type": "string", "description": "A clear description of the customer's issue"},
                "priority": {
                    "type": "string",
                    "description": "Priority level: low, normal, high, or urgent",
                    "enum": ["low", "normal", "high", "urgent"],
                },
            },
            "required": ["issue"],
        },
    },
    {
        "name": "check_loyalty_points",
        "description": (
            "Check a customer's NovaMart loyalty points balance, tier (Bronze/Silver/Gold/Platinum), "
            "and associated benefits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "The customer ID, e.g. CUST-001"}
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Transfer the conversation to a live human support agent. "
            "Use when the customer requests it, or the issue is too complex."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Reason for escalation"}
            },
            "required": ["reason"],
        },
    },
]
