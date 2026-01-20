"""
Twilio Status Callback Handler
Receives webhook callbacks from Twilio with message status and pricing information
Updates DynamoDB with actual costs and sends PostHog events
"""
import json
import logging
import sys
import os
from urllib.parse import parse_qs

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from sms_operations import update_sms_cost
except ImportError:
    # Fallback for Lambda layer
    sys.path.append('/opt/python')
    from sms_operations import update_sms_cost

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def parse_twilio_callback(body: str) -> dict:
    """
    Parse Twilio status callback POST body
    
    Args:
        body: URL-encoded form data from Twilio
        
    Returns:
        Dict with callback parameters
    """
    parsed = parse_qs(body)
    
    # Convert from lists to single values
    result = {}
    for key, value in parsed.items():
        result[key] = value[0] if len(value) == 1 else value
    
    return result


def handler(event, context):
    """
    Lambda handler for Twilio status callbacks
    
    Expected Twilio callback parameters:
    - MessageSid: Twilio message SID
    - MessageStatus: sent, delivered, undelivered, failed, etc.
    - To: Recipient phone number
    - From: Sender phone number  
    - Body: Message content (if included)
    - NumSegments: Number of SMS segments
    - Price: Cost (can be negative for inbound)
    - PriceUnit: Currency unit (e.g., 'USD')
    - ErrorCode: If message failed
    """
    logger.info("Twilio callback received: %s", json.dumps(event))
    
    try:
        # Parse the callback body
        if event.get('isBase64Encoded', False):
            import base64
            body = base64.b64decode(event['body']).decode('utf-8')
        else:
            body = event.get('body', '')
        
        params = parse_twilio_callback(body)
        logger.info("Parsed Twilio callback: %s", json.dumps(params))
        
        # Extract required fields
        message_sid = params.get('MessageSid')
        message_status = params.get('MessageStatus')
        price = params.get('Price')
        price_unit = params.get('PriceUnit', 'USD')
        num_segments = int(params.get('NumSegments', '1'))
        error_code = params.get('ErrorCode')
        
        if not message_sid:
            logger.error("MessageSid missing from callback")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'MessageSid required'})
            }
        
        # Price might not be available yet in early callbacks (queued, sent)
        # We only update costs when price is available
        if price is None or price == '':
            logger.info(f"Price not yet available for {message_sid}, status: {message_status}")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Acknowledged, price pending'})
            }
        
        # Convert price to float
        try:
            price_value = float(price)
        except ValueError:
            logger.error(f"Invalid price value: {price}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid price'})
            }
        
        # Look up our message by Twilio SID
        # We need to find the messageId (UUID) from our DynamoDB record
        # The message_logger stores twilioSid in metadata
        
        # For now, we'll need to scan/query to find the message by twilioSid
        # This is a bit inefficient, but Twilio callbacks are async and infrequent
        # A better approach would be to maintain a mapping table, but for MVP this works
        
        # Try to extract messageId if we stored it in the callback URL
        # Otherwise we'll need to query DynamoDB
        message_uuid = params.get('MessageUuid')  # Custom parameter if we add it
        
        if not message_uuid:
            # Need to find message by Twilio SID
            # For now, log and skip - we'll improve this in next iteration
            logger.warning(f"Cannot find messageId for Twilio SID {message_sid}. Need to implement SID lookup.")
            
            # TODO: Implement lookup by scanning chat-messages for metadata.twilioSid
            # or maintain a separate mapping table
            
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Acknowledged, but messageId lookup not implemented'})
            }
        
        # Update the message with cost data
        success = update_sms_cost(
            message_id=message_uuid,
            price=price_value,
            price_unit=price_unit,
            status=message_status,
            num_segments=num_segments
        )
        
        if success:
            logger.info(f"Successfully updated cost for message {message_uuid}: {price_value} {price_unit}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Cost updated successfully',
                    'messageId': message_uuid,
                    'price': price_value,
                    'status': message_status
                })
            }
        else:
            logger.error(f"Failed to update cost for message {message_uuid}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Failed to update cost'})
            }
        
    except Exception as e:
        logger.error(f"Error processing Twilio callback: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


# For local testing
if __name__ == "__main__":
    # Test with sample Twilio callback
    test_event = {
        'body': 'MessageSid=SM123&MessageStatus=delivered&To=%2B12345678901&From=%2B19876543210&NumSegments=1&Price=-0.0079&PriceUnit=USD&MessageUuid=test-uuid-123'
    }
    
    result = handler(test_event, None)
    print(json.dumps(result, indent=2))

