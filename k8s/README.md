# WhatsApp Webhook Kubernetes Deployment

Simplified Kubernetes deployment for WhatsApp webhook API using Azure Container Registry.

## Files

- `namespace.yaml` - Creates `meta-whatsapp` namespace
- `configmap.yaml` - Non-sensitive configuration
- `secret.yaml` - Sensitive credentials (base64 encoded)
- `deployment.yaml` - Pod deployment with ACR image
- `domain-mapping.yaml` - LoadBalancer service for domain mapping

## Build and Push Image

```bash
# Login to Azure Container Registry
az acr login --name zinfradevv1

# Build and push Docker image
docker build -t zinfradevv1.azurecr.io/meta-whatsapp:latest .
docker push zinfradevv1.azurecr.io/meta-whatsapp:latest
```

## Deployment Steps

### 1. Create ACR Secret

```bash
kubectl create secret docker-registry acr-secret \
  --docker-server=zinfradevv1.azurecr.io \
  --docker-username=$(az acr credential show --name zinfradevv1 --query usernames[0] --output tsv) \
  --docker-password=$(az acr credential show --name zinfradevv1 --query passwords[0].value --output tsv) \
  --namespace=meta-whatsapp
```

### 2. Deploy All Resources

```bash
# Deploy in order
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f deployment.yaml
kubectl apply -f domain-mapping.yaml
```

### 3. Update Configuration

Before deploying, update:

1. **configmap.yaml**: Set your phone number ID
2. **secret.yaml**: Base64 encode your credentials:

```bash
# Example for encoding secrets
echo -n "your_verify_token" | base64
echo -n "your_access_token" | base64
echo -n "your_app_secret" | base64
```

## Domain Mapping

The service will be mapped to: `https://meta-whatsapp.zagent.stage.yavar.ai`

## WhatsApp Webhook URL

Use this URL in WhatsApp Business API settings:
```
https://meta-whatsapp.zagent.stage.yavar.ai/webhook
```

## Verify Deployment

```bash
# Check pods
kubectl get pods -n meta-whatsapp

# Check service
kubectl get svc -n meta-whatsapp

# Check logs
kubectl logs -n meta-whatsapp deployment/whatsapp -f

# Test endpoint
kubectl exec -n meta-whatsapp deployment/whatsapp -- curl http://localhost:8000/health
```

## Clean Up

```bash
kubectl delete namespace meta-whatsapp
```