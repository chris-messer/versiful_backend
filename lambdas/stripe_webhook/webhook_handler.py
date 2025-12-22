"""
Stripe Webhook Handler Lambda
Processes Stripe webhook events for subscription management
"""
import json
import os
import sys
import boto3
import stripe
import logging
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

# Add Lambda layer path for shared code
sys.path.append('/opt/python')

# Import secrets helper
try:
    from secrets_helper import get_secret, get_secrets
except ImportError:
    # Fallback for local testing
    from lambdas.shared.secrets_helper import get_secret, get_secrets

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Stripe with key from Secrets Manager
stripe.api_key = get_secret('stripe_secret_key')

# DynamoDB setup
dynamodb = boto3.resource("dynamodb")
env = os.environ.get("ENVIRONMENT", "dev")
project_name = os.environ.get("PROJECT_NAME", "versiful")
table_name = f"{env}-{project_name}-users"
table = dynamodb.Table(table_name)


def handler(event, context):
    """Handle Stripe webhook events"""
    logger.info("Received webhook event")
    
    payload = event.get("body", "")
    sig_header = event.get("headers", {}).get("stripe-signature") or \
                event.get("headers", {}).get("Stripe-Signature")
    
    if not sig_header:
        logger.error("No Stripe signature header found")
        return {"statusCode": 400, "body": "No signature header"}
    
    # Get webhook secret from Secrets Manager
    # Note: This will be set manually after webhook endpoint is created
    secrets = get_secrets()
    endpoint_secret = secrets.get("stripe_webhook_secret")
    
    if not endpoint_secret:
        logger.error("Stripe webhook secret not configured in Secrets Manager")
        return {"statusCode": 500, "body": "Webhook secret not configured"}
    
    try:
        # Verify webhook signature
        webhook_event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return {"statusCode": 400, "body": "Invalid payload"}
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return {"statusCode": 400, "body": "Invalid signature"}
    
    event_type = webhook_event["type"]
    data = webhook_event["data"]["object"]
    
    logger.info(f"Processing webhook event: {event_type}")
    
    # Route to appropriate handler
    try:
        if event_type == "checkout.session.completed":
            handle_checkout_completed(data)
        elif event_type == "customer.subscription.created":
            handle_subscription_created(data)
        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            handle_subscription_deleted(data)
        elif event_type == "invoice.payment_succeeded":
            handle_payment_succeeded(data)
        elif event_type == "invoice.payment_failed":
            handle_payment_failed(data)
        else:
            logger.info(f"Unhandled event type: {event_type}")
        
        return {"statusCode": 200, "body": "Success"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # Return 500 so Stripe retries
        return {"statusCode": 500, "body": f"Processing failed: {str(e)}"}


def handle_checkout_completed(session):
    """User completed checkout - subscription is being set up"""
    customer_id = session["customer"]
    subscription_id = session.get("subscription")
    user_id = session.get("metadata", {}).get("userId")
    
    if not user_id:
        logger.error("No userId in checkout session metadata")
        return
    
    logger.info(f"Checkout completed for user {user_id}, subscription {subscription_id}")
    
    # Get subscription details
    subscription = stripe.Subscription.retrieve(subscription_id)
    plan_interval = subscription["items"]["data"][0]["price"]["recurring"]["interval"]
    plan = "monthly" if plan_interval == "month" else "annual"
    
    table.update_item(
        Key={"userId": user_id},
        UpdateExpression="""
            SET stripeCustomerId = :cid,
                stripeSubscriptionId = :sid,
                isSubscribed = :sub,
                plan = :plan,
                plan_monthly_cap = :cap,
                subscriptionStatus = :status,
                currentPeriodEnd = :period_end,
                cancelAtPeriodEnd = :cancel,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":cid": customer_id,
            ":sid": subscription_id,
            ":sub": True,
            ":plan": plan,
            ":cap": -1,  # Unlimited for paid plans
            ":status": subscription["status"],
            ":period_end": int(subscription["current_period_end"]),
            ":cancel": subscription.get("cancel_at_period_end", False),
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
    
    logger.info(f"Updated user {user_id} with subscription {plan}")


def handle_subscription_created(subscription):
    """Subscription was created (usually same as checkout.completed)"""
    logger.info(f"Subscription created: {subscription['id']}")
    # Usually handled by checkout.session.completed
    # But we can update here too for safety


def handle_subscription_updated(subscription):
    """Subscription was modified (plan change, cancellation scheduled, etc)"""
    customer_id = subscription["customer"]
    
    logger.info(f"Subscription updated for customer {customer_id}")
    
    # Find user by customer ID
    response = table.scan(
        FilterExpression=Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response.get("Items"):
        logger.warning(f"No user found for customer {customer_id}")
        return
    
    user = response["Items"][0]
    plan_interval = subscription["items"]["data"][0]["price"]["recurring"]["interval"]
    plan = "monthly" if plan_interval == "month" else "annual"
    
    # Update subscription details
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET subscriptionStatus = :status,
                plan = :plan,
                plan_monthly_cap = :cap,
                currentPeriodEnd = :period_end,
                cancelAtPeriodEnd = :cancel,
                isSubscribed = :sub,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":status": subscription["status"],
            ":plan": plan,
            ":cap": -1,  # Unlimited for paid plans
            ":period_end": int(subscription["current_period_end"]),
            ":cancel": subscription.get("cancel_at_period_end", False),
            ":sub": subscription["status"] in ["active", "trialing"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
    
    logger.info(f"Updated subscription for user {user['userId']}: {subscription['status']}")


def handle_subscription_deleted(subscription):
    """Subscription was canceled and has now ended"""
    customer_id = subscription["customer"]
    
    logger.info(f"Subscription deleted for customer {customer_id}")
    
    response = table.scan(
        FilterExpression=Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response.get("Items"):
        logger.warning(f"No user found for customer {customer_id}")
        return
    
    user = response["Items"][0]
    
    # Mark user as unsubscribed, revert to free plan with message cap
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET isSubscribed = :sub,
                plan = :plan,
                plan_monthly_cap = :cap,
                subscriptionStatus = :status,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":sub": False,
            ":plan": "free",
            ":cap": 5,  # Revert to free tier limit (5 messages/month)
            ":status": "canceled",
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
    
    logger.info(f"Reverted user {user['userId']} to free plan")


def handle_payment_failed(invoice):
    """Payment failed - mark subscription at risk"""
    customer_id = invoice["customer"]
    subscription_id = invoice.get("subscription")
    
    if not subscription_id:
        logger.info("Payment failed for non-subscription invoice")
        return
    
    logger.warning(f"Payment failed for customer {customer_id}")
    
    response = table.scan(
        FilterExpression=Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response.get("Items"):
        logger.warning(f"No user found for customer {customer_id}")
        return
    
    user = response["Items"][0]
    
    # Get current subscription status
    subscription = stripe.Subscription.retrieve(subscription_id)
    
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET subscriptionStatus = :status,
                isSubscribed = :sub,
                plan_monthly_cap = :cap,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":status": subscription["status"],  # Will be "past_due" or "unpaid"
            ":sub": subscription["status"] == "past_due",  # Still subscribed if past_due
            ":cap": -1 if subscription["status"] == "past_due" else 5,  # Keep unlimited if past_due
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
    
    logger.warning(f"Marked user {user['userId']} subscription as {subscription['status']}")


def handle_payment_succeeded(invoice):
    """Payment succeeded - renewal confirmed"""
    customer_id = invoice["customer"]
    subscription_id = invoice.get("subscription")
    
    if not subscription_id:
        logger.info("Payment succeeded for non-subscription invoice")
        return
    
    logger.info(f"Payment succeeded for customer {customer_id}")
    
    response = table.scan(
        FilterExpression=Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response.get("Items"):
        logger.warning(f"No user found for customer {customer_id}")
        return
    
    user = response["Items"][0]
    subscription = stripe.Subscription.retrieve(subscription_id)
    
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET subscriptionStatus = :status,
                isSubscribed = :sub,
                plan_monthly_cap = :cap,
                currentPeriodEnd = :period_end,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":status": subscription["status"],
            ":sub": True,
            ":cap": -1,  # Unlimited for paid plans
            ":period_end": int(subscription["current_period_end"]),
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
    
    logger.info(f"Confirmed subscription renewal for user {user['userId']}")

