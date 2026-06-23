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

# Import SMS notifications helper
try:
    from sms_notifications import send_subscription_confirmation_sms, send_cancellation_sms
except ImportError:
    # Fallback for local testing
    from lambdas.shared.sms_notifications import send_subscription_confirmation_sms, send_cancellation_sms

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
promo_codes_table = dynamodb.Table(f"{env}-{project_name}-promo-codes")


def _field(obj, key, default=None):
    """Read a field from a plain dict or Stripe API object."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except (KeyError, TypeError):
        return default


def _stripe_json(obj):
    """Serialize Stripe objects for logging without crashing on nested data."""
    try:
        if hasattr(obj, "to_dict_recursive"):
            payload = obj.to_dict_recursive()
        elif hasattr(obj, "to_dict"):
            payload = obj.to_dict()
        elif isinstance(obj, dict):
            payload = obj
        else:
            payload = str(obj)
        return json.dumps(payload, default=str, indent=2)
    except Exception:
        return str(obj)


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
    subscription_id = _field(session, "subscription")
    user_id = _field(_field(session, "metadata") or {}, "userId")
    
    if not user_id:
        logger.error("No userId in checkout session metadata")
        return
    
    logger.info(f"Checkout completed for user {user_id}, subscription {subscription_id}")
    
    # Extract promo code from checkout session if one was applied
    promo_code = _extract_promo_code(session)
    if promo_code:
        logger.info(f"Promo code '{promo_code}' used by user {user_id}")
    
    # Get subscription details - use expand to get all fields
    subscription = stripe.Subscription.retrieve(
        subscription_id,
        expand=['items.data.price']
    )
    
    logger.info(f"RAW SUBSCRIPTION OBJECT: {_stripe_json(subscription)}")
    
    # Access plan information
    plan_interval = subscription['items']['data'][0]['price']['recurring']['interval']
    plan = "monthly" if plan_interval == "month" else "annual"
    
    # Get current_period_end from the subscription object (not from items)
    period_end = _field(subscription, 'current_period_end')
    logger.info(f"Got current_period_end from subscription: {period_end}")
    
    update_expression = """
        SET stripeCustomerId = :cid,
            stripeSubscriptionId = :sid,
            isSubscribed = :sub,
            #plan = :plan,
            plan_monthly_cap = :cap,
            subscriptionStatus = :status,
            cancelAtPeriodEnd = :cancel,
            updatedAt = :now
    """
    
    expression_values = {
        ":cid": customer_id,
        ":sid": subscription_id,
        ":sub": True,
        ":plan": plan,
        ":cap": -1,  # Unlimited for paid plans
        ":status": subscription['status'],
        ":cancel": _field(subscription, 'cancel_at_period_end', False) or _field(subscription, 'cancel_at') is not None,
        ":now": datetime.now(timezone.utc).isoformat()
    }
    
    # Only add currentPeriodEnd if we have it
    if period_end:
        update_expression += ", currentPeriodEnd = :period_end"
        expression_values[":period_end"] = int(period_end)
    
    # Store promo code on user record for attribution
    if promo_code:
        update_expression += ", promoCode = :promo"
        expression_values[":promo"] = promo_code
    
    table.update_item(
        Key={"userId": user_id},
        UpdateExpression=update_expression,
        ExpressionAttributeNames={
            "#plan": "plan"
        },
        ExpressionAttributeValues=expression_values
    )
    
    logger.info(f"Updated user {user_id} with subscription {plan}, period_end: {period_end}, promoCode: {promo_code}")
    
    # Track promo code usage in promo-codes table
    if promo_code:
        _track_promo_code_usage(promo_code, user_id)
    
    # Send subscription confirmation SMS if user has a phone number
    try:
        user_response = table.get_item(Key={"userId": user_id})
        if "Item" in user_response:
            phone_number = user_response["Item"].get("phoneNumber")
            if phone_number:
                logger.info(f"Sending subscription confirmation SMS to {phone_number}")
                send_subscription_confirmation_sms(phone_number)
            else:
                logger.info(f"User {user_id} has no phone number registered, skipping SMS")
    except Exception as sms_error:
        logger.error(f"Failed to send subscription confirmation SMS for user {user_id}: {str(sms_error)}", exc_info=True)


def _extract_promo_code(session):
    """Extract the customer-facing promotion code from a checkout session.
    
    Retrieves the full session with discounts expanded to get the
    promotion code the customer entered (e.g. 'WELCOME', 'FRIEND2026').
    Returns None if no promotion code was applied.
    """
    try:
        full_session = stripe.checkout.Session.retrieve(
            session["id"],
            expand=["total_details.breakdown"]
        )
        
        total_details = _field(full_session, "total_details") or {}
        breakdown = _field(total_details, "breakdown") or {}
        discounts = _field(breakdown, "discounts") or []
        if discounts:
            discount = _field(discounts[0], "discount") or {}
            promo = _field(discount, "promotion_code")
            if promo:
                # promo is a Stripe PromotionCode ID; retrieve it to get the customer-facing code
                promo_obj = stripe.PromotionCode.retrieve(promo)
                return (_field(promo_obj, "code") or "").upper()
    except Exception as e:
        logger.warning(f"Could not extract promo code from session: {e}")
    
    return None


def _track_promo_code_usage(code, user_id):
    """Atomically increment usage counter on the promo-codes table.
    
    Creates the record if it doesn't exist yet (first redemption before
    the code was seeded via the dashboard). Appends the userId to a
    redeemedBy list for audit.
    """
    try:
        promo_codes_table.update_item(
            Key={"code": code},
            UpdateExpression="""
                SET updatedAt = :now
                ADD timesRedeemed :inc, redeemedBy :uid
            """,
            ExpressionAttributeValues={
                ":inc": 1,
                ":now": datetime.now(timezone.utc).isoformat(),
                ":uid": {user_id}
            }
        )
        logger.info(f"Tracked promo code '{code}' redemption by user {user_id}")
    except Exception as e:
        logger.error(f"Failed to track promo code usage for '{code}': {e}", exc_info=True)


def handle_subscription_created(subscription):
    """Subscription was created (usually same as checkout.completed)"""
    logger.info(f"Subscription created: {subscription['id']}")
    # Usually handled by checkout.session.completed
    # But we can update here too for safety


def handle_subscription_updated(subscription):
    """Subscription was modified (plan change, cancellation scheduled, etc)"""
    logger.info(f"RAW SUBSCRIPTION UPDATE OBJECT: {_stripe_json(subscription)}")
    
    customer_id = subscription["customer"]
    
    logger.info(f"Subscription updated for customer {customer_id}")
    logger.info(f"cancel_at_period_end: {_field(subscription, 'cancel_at_period_end')}")
    logger.info(f"status: {_field(subscription, 'status')}")
    
    # Find user by customer ID
    response = table.scan(
        FilterExpression=Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response.get("Items"):
        logger.warning(f"No user found for customer {customer_id}")
        return
    
    user = response["Items"][0]
    logger.info(
        f"Found user: {user['userId']}, cancel_at={_field(subscription, 'cancel_at')}, "
        f"cancel_at_period_end={_field(subscription, 'cancel_at_period_end')}"
    )
    
    plan_interval = subscription["items"]["data"][0]["price"]["recurring"]["interval"]
    plan = "monthly" if plan_interval == "month" else "annual"
    
    # Get current_period_end from subscription object (not from items)
    period_end = _field(subscription, 'current_period_end')
    if not period_end:
        logger.warning(f"No current_period_end in subscription update for {subscription['id']}")
    
    # Determine if subscription is being canceled
    # Stripe sets either cancel_at_period_end=true OR cancel_at to a timestamp
    is_canceling = _field(subscription, 'cancel_at_period_end', False) or _field(subscription, 'cancel_at') is not None
    logger.info(f"Computed is_canceling: {is_canceling}")
    
    # Build update expression dynamically
    update_expression = """
        SET subscriptionStatus = :status,
            #plan = :plan,
            plan_monthly_cap = :cap,
            cancelAtPeriodEnd = :cancel,
            isSubscribed = :sub,
            updatedAt = :now
    """
    
    expression_values = {
        ":status": subscription["status"],
        ":plan": plan,
        ":cap": -1 if subscription["status"] in ["active", "trialing"] else 5,
        ":cancel": is_canceling,  # Use computed is_canceling
        ":sub": subscription["status"] in ["active", "trialing"],
        ":now": datetime.now(timezone.utc).isoformat()
    }
    
    # Only add currentPeriodEnd if we have it
    if period_end:
        update_expression += ", currentPeriodEnd = :period_end"
        expression_values[":period_end"] = int(period_end)
    
    # Update subscription details
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression=update_expression,
        ExpressionAttributeNames={
            "#plan": "plan"
        },
        ExpressionAttributeValues=expression_values
    )
    
    logger.info(
        f"Updated subscription for user {user['userId']}: {subscription['status']}, "
        f"cancel_at_period_end: {_field(subscription, 'cancel_at_period_end', False)}"
    )


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
    # REMOVE currentPeriodEnd to avoid showing stale billing dates
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET isSubscribed = :sub,
                #plan = :plan,
                plan_monthly_cap = :cap,
                subscriptionStatus = :status,
                cancelAtPeriodEnd = :cancel,
                updatedAt = :now
            REMOVE currentPeriodEnd
        """,
        ExpressionAttributeNames={
            "#plan": "plan"
        },
        ExpressionAttributeValues={
            ":sub": False,
            ":plan": "free",
            ":cap": 5,  # Revert to free tier limit (5 messages/month)
            ":status": "canceled",
            ":cancel": False,  # Clear the cancel flag since subscription has ended
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
    
    logger.info(f"Reverted user {user['userId']} to free plan after subscription ended")
    
    # Send cancellation SMS if user has a phone number
    try:
        phone_number = user.get("phoneNumber")
        if phone_number:
            logger.info(f"Sending cancellation SMS to {phone_number}")
            send_cancellation_sms(phone_number)
        else:
            logger.info(f"User {user['userId']} has no phone number registered, skipping SMS")
    except Exception as sms_error:
        # Log error but don't fail the webhook
        logger.error(f"Failed to send cancellation SMS for user {user['userId']}: {str(sms_error)}", exc_info=True)


def handle_payment_failed(invoice):
    """Payment failed - mark subscription at risk"""
    customer_id = invoice["customer"]
    subscription_id = _field(invoice, "subscription")
    
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
            ":status": subscription['status'],  # Will be "past_due" or "unpaid"
            ":sub": subscription['status'] == "past_due",  # Still subscribed if past_due
            ":cap": -1 if subscription['status'] == "past_due" else 5,  # Keep unlimited if past_due
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
    
    logger.warning(f"Marked user {user['userId']} subscription as {subscription['status']}")


def handle_payment_succeeded(invoice):
    """Payment succeeded - renewal confirmed"""
    customer_id = invoice["customer"]
    subscription_id = _field(invoice, "subscription")
    
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
    
    # Get current_period_end from subscription object (not from items)
    period_end = _field(subscription, 'current_period_end')
    if not period_end:
        logger.warning(f"No current_period_end in subscription {subscription_id}")
    
    update_expression = """
        SET subscriptionStatus = :status,
            isSubscribed = :sub,
            plan_monthly_cap = :cap,
            updatedAt = :now
    """
    
    expression_values = {
        ":status": subscription['status'],
        ":sub": True,
        ":cap": -1,  # Unlimited for paid plans
        ":now": datetime.now(timezone.utc).isoformat()
    }
    
    # Only add currentPeriodEnd if we have it
    if period_end:
        update_expression += ", currentPeriodEnd = :period_end"
        expression_values[":period_end"] = int(period_end)
    
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_values
    )
    
    logger.info(f"Confirmed subscription renewal for user {user['userId']}")

