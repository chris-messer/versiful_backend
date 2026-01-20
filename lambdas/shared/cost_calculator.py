"""
Cost calculation utilities for GPT and Twilio usage
"""
from decimal import Decimal
from typing import Dict, Optional

# OpenAI Pricing (per 1 million tokens) - as of January 2026
# Source: https://openai.com/api/pricing/
MODEL_PRICING = {
    'gpt-4o': {
        'input': Decimal('2.50'),   # per 1M input tokens
        'output': Decimal('10.00')  # per 1M output tokens
    },
    'gpt-4o-mini': {
        'input': Decimal('0.15'),
        'output': Decimal('0.60')
    },
    'gpt-4-turbo': {
        'input': Decimal('10.00'),
        'output': Decimal('30.00')
    },
    'gpt-4': {
        'input': Decimal('30.00'),
        'output': Decimal('60.00')
    },
    'gpt-3.5-turbo': {
        'input': Decimal('0.50'),
        'output': Decimal('1.50')
    }
}


def calculate_gpt_cost(
    model: str,
    input_tokens: int,
    output_tokens: int
) -> Optional[Decimal]:
    """
    Calculate the cost of a GPT API call based on token usage
    
    This uses OpenAI's published pricing to calculate the ACTUAL cost
    that will be billed. It's not an estimate - OpenAI bills deterministically
    based on token counts and these published rates.
    
    Args:
        model: Model name (e.g., 'gpt-4o', 'gpt-4o-mini')
        input_tokens: Number of prompt/input tokens
        output_tokens: Number of completion/output tokens
        
    Returns:
        Cost in USD as Decimal, or None if model pricing not found
        
    Example:
        >>> calculate_gpt_cost('gpt-4o', 1000, 500)
        Decimal('0.00750')  # $0.0075 = (1000/1M * $2.50) + (500/1M * $10.00)
    """
    if model not in MODEL_PRICING:
        # Try to match model prefix (e.g., 'gpt-4o-2024-08-06' -> 'gpt-4o')
        model_prefix = None
        for known_model in MODEL_PRICING.keys():
            if model.startswith(known_model):
                model_prefix = known_model
                break
        
        if not model_prefix:
            return None
        
        model = model_prefix
    
    pricing = MODEL_PRICING[model]
    
    # Cost = (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * pricing['input']
    output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * pricing['output']
    
    total_cost = input_cost + output_cost
    
    # Round to 6 decimal places for precision (fractions of a cent)
    return total_cost.quantize(Decimal('0.000001'))


def format_cost_for_dynamodb(cost: Decimal) -> Decimal:
    """
    Format a cost value for storage in DynamoDB
    DynamoDB Decimals should be properly formatted
    
    Args:
        cost: Cost as Decimal
        
    Returns:
        Formatted Decimal safe for DynamoDB
    """
    return cost.quantize(Decimal('0.000001'))


def get_model_pricing() -> Dict[str, Dict[str, Decimal]]:
    """
    Get the full model pricing dictionary
    
    Returns:
        Dictionary of model pricing
    """
    return MODEL_PRICING.copy()


# Example usage and testing
if __name__ == "__main__":
    # Test cases
    print("GPT Cost Calculator - Test Cases")
    print("=" * 50)
    
    # Test 1: GPT-4o with moderate usage
    cost1 = calculate_gpt_cost('gpt-4o', 1000, 500)
    print(f"GPT-4o (1000 input, 500 output): ${cost1}")
    
    # Test 2: GPT-4o-mini (cheaper)
    cost2 = calculate_gpt_cost('gpt-4o-mini', 1000, 500)
    print(f"GPT-4o-mini (1000 input, 500 output): ${cost2}")
    
    # Test 3: Large conversation
    cost3 = calculate_gpt_cost('gpt-4o', 5000, 2000)
    print(f"GPT-4o (5000 input, 2000 output): ${cost3}")
    
    # Test 4: Model with date suffix
    cost4 = calculate_gpt_cost('gpt-4o-2024-08-06', 1000, 500)
    print(f"GPT-4o-2024-08-06 (1000 input, 500 output): ${cost4}")
    
    # Test 5: Unknown model
    cost5 = calculate_gpt_cost('unknown-model', 1000, 500)
    print(f"Unknown model: {cost5}")
    
    print("=" * 50)
    print("\nAll pricing:")
    for model, pricing in MODEL_PRICING.items():
        print(f"{model:20} Input: ${pricing['input']}/1M  Output: ${pricing['output']}/1M")

