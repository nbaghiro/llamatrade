"""Webhooks router - Stripe webhook handling."""

import os

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter()

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


@router.post("/stripe")
async def handle_stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")

    # In production, verify signature using stripe library
    # try:
    #     event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    # except stripe.error.SignatureVerificationError:
    #     raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle different event types
    # if event["type"] == "customer.subscription.created":
    #     handle_subscription_created(event["data"]["object"])
    # elif event["type"] == "customer.subscription.updated":
    #     handle_subscription_updated(event["data"]["object"])
    # elif event["type"] == "invoice.paid":
    #     handle_invoice_paid(event["data"]["object"])
    # elif event["type"] == "invoice.payment_failed":
    #     handle_payment_failed(event["data"]["object"])

    return {"received": True}
