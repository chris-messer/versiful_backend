# How to Get Your Stripe Webhook Secrets

## For Development (dev.tfvars)
1. Go to https://dashboard.stripe.com/test/webhooks
2. Find your dev webhook endpoint: `https://api.dev.versiful.io/stripe/webhook`
3. Click on it
4. Click "Reveal" next to "Signing secret"
5. Copy the secret (starts with `whsec_...`)

## For Production (prod.tfvars)
1. Go to https://dashboard.stripe.com/webhooks (make sure you're NOT in test mode)
2. Find your prod webhook endpoint: `https://api.versiful.io/stripe/webhook`
3. Click on it
4. Click "Reveal" next to "Signing secret"  
5. Copy the secret (starts with `whsec_...`)

## Then Add to Your tfvars Files

### dev.tfvars
Add this line after `stripe_secret_key`:
```hcl
stripe_webhook_secret = "whsec_YOUR_DEV_SECRET_HERE"
```

### prod.tfvars
Add this line after `stripe_secret_key`:
```hcl
stripe_webhook_secret = "whsec_YOUR_PROD_SECRET_HERE"
```

## Deploy
After adding to both files:
```bash
cd terraform

# Dev
terraform workspace select dev
terraform apply -var-file=dev.tfvars

# Prod
terraform workspace select prod
terraform apply -var-file=prod.tfvars
```

This will update the Secrets Manager with the webhook secret, and your webhooks will start working!

