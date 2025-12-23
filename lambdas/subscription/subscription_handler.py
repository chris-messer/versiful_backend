"""
Stripe Subscription Handler Lambda
Handles subscription checkout, customer portal, and price retrieval
"""
import json
import os
import sys
import boto3
import stripe
import logging

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
    """Main handler routes to sub-handlers"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    path = event.get("path", "")
    method = event.get("httpMethod", "")
    
    try:
        if method == "POST" and path.endswith("/subscription/checkout"):
            return create_checkout_session(event, context)
        elif method == "POST" and path.endswith("/subscription/portal"):
            return create_portal_session(event, context)
        elif method == "GET" and path.endswith("/subscription/prices"):
            return get_prices(event, context)
        else:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Not found"})
            }
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


def create_checkout_session(event, context):
    """Create a Stripe checkout session for monthly or annual plan"""
    try:
        user_id = event["requestContext"]["authorizer"]["userId"]
        body = json.loads(event.get("body", "{}"))
        price_id = body.get("priceId")
        success_url = body.get("successUrl")  # Allow frontend to specify URLs
        cancel_url = body.get("cancelUrl")
        
        if not price_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "priceId is required"})
            }
        
        # Get frontend domain from environment, or use provided URLs
        frontend_domain = os.environ.get("FRONTEND_DOMAIN", f"{env}.versiful.io")
        
        # Use provided URLs if available, otherwise construct from frontend_domain
        if not success_url:
            success_url = f"https://{frontend_domain}/settings?session_id={{CHECKOUT_SESSION_ID}}"
        if not cancel_url:
            cancel_url = f"https://{frontend_domain}/subscription"
        
        # Get or create Stripe customer
        user = table.get_item(Key={"userId": user_id}).get("Item", {})
        email = user.get("email")
        
        if not email:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "User email not found"})
            }
        
        if user.get("stripeCustomerId"):
            customer_id = user["stripeCustomerId"]
            logger.info(f"Using existing Stripe customer: {customer_id}")
        else:
            # Create new Stripe customer
            customer = stripe.Customer.create(
                email=email,
                metadata={"userId": user_id}
            )
            customer_id = customer.id
            logger.info(f"Created new Stripe customer: {customer_id}")
            
            # Save customer ID to DynamoDB
            table.update_item(
                Key={"userId": user_id},
                UpdateExpression="SET stripeCustomerId = :cid",
                ExpressionAttributeValues={":cid": customer_id}
            )
        
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"userId": user_id}
        )
        
        logger.info(f"Created checkout session: {checkout_session.id}")
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "url": checkout_session.url,
                "sessionId": checkout_session.id
            })
        }
        
    except KeyError as e:
        logger.error(f"Missing required field: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Missing required field: {str(e)}"})
        }
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


def create_portal_session(event, context):
    """Create customer portal session for managing subscription"""
    try:
        user_id = event["requestContext"]["authorizer"]["userId"]
        body = json.loads(event.get("body", "{}"))
        return_url = body.get("returnUrl")  # Allow frontend to specify return URL
        
        user = table.get_item(Key={"userId": user_id}).get("Item", {})
        
        if not user.get("stripeCustomerId"):
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "No active subscription found"})
            }
        
        frontend_domain = os.environ.get("FRONTEND_DOMAIN", f"{env}.versiful.io")
        
        # Use provided return URL if available, otherwise construct from frontend_domain
        if not return_url:
            return_url = f"https://{frontend_domain}/settings"
        
        customer_id = user["stripeCustomerId"]
        
        try:
            # Try to create portal session with stored customer ID
            portal_session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url
            )
            
            logger.info(f"Created portal session for customer: {customer_id}")
            
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({"url": portal_session.url})
            }
            
        except stripe.error.InvalidRequestError as e:
            # If customer doesn't exist, try to find the correct customer by email
            if "No such customer" in str(e):
                logger.warning(f"Customer {customer_id} not found in Stripe, attempting to find by email")
                
                user_email = user.get("email")
                if not user_email:
                    logger.error(f"No email found for user {user_id}")
                    raise
                
                # Search for customer by email
                customers = stripe.Customer.list(email=user_email, limit=1)
                
                if not customers.data:
                    logger.error(f"No Stripe customer found for email {user_email}")
                    return {
                        "statusCode": 404,
                        "body": json.dumps({"error": "No Stripe customer found. Please resubscribe."})
                    }
                
                # Found the customer, update DynamoDB
                correct_customer_id = customers.data[0].id
                logger.info(f"Found correct customer ID: {correct_customer_id}, updating DynamoDB")
                
                # Get their active subscription
                subscriptions = stripe.Subscription.list(customer=correct_customer_id, status='active', limit=1)
                subscription_id = subscriptions.data[0].id if subscriptions.data else None
                
                # Update DynamoDB with correct IDs
                update_expr = "SET stripeCustomerId = :cid"
                expr_values = {":cid": correct_customer_id}
                
                if subscription_id:
                    update_expr += ", stripeSubscriptionId = :sid"
                    expr_values[":sid"] = subscription_id
                
                table.update_item(
                    Key={"userId": user_id},
                    UpdateExpression=update_expr,
                    ExpressionAttributeValues=expr_values
                )
                
                logger.info(f"Updated user {user_id} with correct customer ID: {correct_customer_id}")
                
                # Retry portal creation with correct customer ID
                portal_session = stripe.billing_portal.Session.create(
                    customer=correct_customer_id,
                    return_url=return_url
                )
                
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json"
                    },
                    "body": json.dumps({"url": portal_session.url})
                }
            else:
                # Some other Stripe error
                raise
        
    except KeyError as e:
        logger.error(f"Missing required field: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Missing required field: {str(e)}"})
        }
    except Exception as e:
        logger.error(f"Error creating portal session: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


def get_prices(event, context):
    """Return Stripe price IDs for frontend"""
    try:
        logger.info("Fetching Stripe price IDs")
        
        # Environment-specific price IDs
        # Determine environment based on Stripe API key
        is_live_mode = stripe.api_key.startswith('sk_live_')
        
        if is_live_mode:
            # Production (live mode) - Account 51Qszo...
            prices = {
                "monthly": "price_1ShYvGBcYhqWB9qElNFW7ZDS",  # $9.99/month
                "annual": "price_1ShYvHBcYhqWB9qEJQBepwRM"     # $99.99/year
            }
        elif '51ShHXv' in stripe.api_key:
            # Staging (test mode) - Account 51ShHXv...
            prices = {
                "monthly": "price_1ShZ1aAyC9k5KbaXIxag1Bd6",  # $9.99/month
                "annual": "price_1ShZ2BAyC9k5KbaXFrJCNHsl"     # $99.99/year
            }
        else:
            # Dev (test mode) - Account 51Qszoe...
            prices = {
                "monthly": "price_1ShYtwB2NunFksMzz5ZHryaw",  # $9.99/month
                "annual": "price_1ShYtwB2NunFksMzBLTSE1Fe"     # $99.99/year
            }
        
        logger.info(f"Returning price IDs for {env} environment: {prices}")
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(prices)
        }
        
    except Exception as e:
        logger.error(f"Error fetching prices: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

