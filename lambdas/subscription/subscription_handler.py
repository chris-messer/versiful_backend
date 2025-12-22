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
        
        # Create portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=user["stripeCustomerId"],
            return_url=return_url
        )
        
        logger.info(f"Created portal session for customer: {user['stripeCustomerId']}")
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({"url": portal_session.url})
        }
        
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
        
        # Price IDs created via Stripe CLI
        prices = {
            "monthly": "price_1ShDU6B2NunFksMzSwxqBRkb",  # $9.99/month
            "annual": "price_1ShDUGB2NunFksMzM51dIr0I"     # $99.99/year
        }
        
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

