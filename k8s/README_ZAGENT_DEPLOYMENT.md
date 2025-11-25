# WhatsApp Webhook API with Zagent Integration

This deployment includes the WhatsApp Webhook API with integrated Zagent API support for message testing and processing.

## 🚀 Features

- **WhatsApp Webhook Processing**: Handle incoming WhatsApp messages
- **Z-Transact Integration**: Upload and process documents
- **Zagent API Integration**: Send messages to Zagent chatbot for testing
- **Kubernetes Deployment**: Production-ready deployment with health checks
- **Persistent Storage**: Media and logs persistence
- **Environment Configuration**: Secure secrets management

## 📋 Prerequisites

- Kubernetes cluster (AKS, GKE, EKS, or local)
- kubectl configured
- Azure Container Registry access
- WhatsApp Business API credentials
- Zagent API credentials

## 🔧 Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `YOUR_VERIFY_TOKEN` | WhatsApp webhook verify token | `your_verify_token` |
| `TOKEN` | WhatsApp access token | `EAAHb5EERGkEBP8...` |
| `PHONE_NUMBER_ID` | WhatsApp phone number ID | `921528817706587` |
| `WHATSAPP_APP_SECRET` | WhatsApp app secret | `your_app_secret` |
| `Z_TRANSACT_ACCESS_TOKEN` | Z-Transact API token | `eyJhbGciOiJIUzI1NiIs...` |
| `Z_TRANSACT_API_URL` | Z-Transact API URL | `https://api.z-transact.yavar.ai/v1` |
| `ZAGENT_API_URL` | Zagent API URL | `https://app.zagent.stage.yavar.ai/v2` |
| `ZAGENT_ACCESS_TOKEN` | Zagent API access token | `eyJhbGciOiJIUzI1NiIs...` |
| `ZAGENT_BOT_UUID` | Zagent bot UUID | `9a23d7a3-1d16-4746-a420-d4881929d1d2` |
| `ZAGENT_CONVERSATION_ID` | Zagent conversation ID | `787` |

## 🚢 Deployment

### 1. Create Secrets

```bash
kubectl apply -f secret.yaml
```

### 2. Deploy the Application

```bash
kubectl apply -f deployment.yaml
```

### 3. Verify Deployment

```bash
# Check pods
kubectl get pods -l app=whatsapp-webhook -n meta-whatsapp

# Check services
kubectl get services -n meta-whatsapp

# Check logs
kubectl logs -l app=whatsapp-webhook -n meta-whatsapp -f
```

## 🌐 API Endpoints

### WhatsApp Endpoints
- `GET /webhook` - Webhook verification
- `POST /webhook` - Receive WhatsApp messages
- `GET /health` - Health check
- `GET /` - Root endpoint

### Testing Endpoints
- `GET /test/zagent` - Test Zagent API connection
- `POST /test/zagent/message` - Send test message to Zagent

## 🧪 Testing the Integration

### Test Zagent Connection

```bash
# Test connection to Zagent API
curl -X GET http://your-service-url/test/zagent

# Expected response
{
  "status": "success",
  "zagent_connected": true,
  "timestamp": "2025-11-24T17:45:30.123Z"
}
```

### Send Test Message to Zagent

```bash
# Send a test message
curl -X POST http://your-service-url/test/zagent/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello from WhatsApp webhook API",
    "conversation_id": "787"
  }'

# Expected response (with parsed content)
{
  "status": "success",
  "message": "Message processed successfully",
  "user_input": "Hello from WhatsApp webhook API",
  "bot_reply": "Hello! How can I assist you today?",
  "response_details": {
    "message_id": 2702,
    "end": false,
    "end_reason": null,
    "time_taken": 1.39,
    "should_connect_agent": false
  },
  "timestamp": "2025-11-24T17:45:30.123Z"
}
```

### Simple Echo Test (for response format validation)

```bash
# Test echo endpoint
curl -X POST http://your-service-url/test/echo \
  -H "Content-Type: application/json" \
  -d '{"message": "Test message"}'

# Expected response
{
  "status": "success",
  "user_input": "Test message",
  "bot_reply": "Echo: Test message",
  "response_details": {
    "message_id": 12345,
    "end": true,
    "end_reason": "completed",
    "time_taken": 0.1,
    "should_connect_agent": false
  },
  "timestamp": "2025-11-24T17:45:30.123Z"
}
```

### Test WhatsApp Webhook

```bash
# Test webhook verification (replace with your actual verify token)
curl -X GET "http://your-service-url/webhook?hub.mode=subscribe&hub.verify_token=your_verify_token&hub.challenge=test_challenge"
```

## 🔍 Monitoring and Logs

### View Application Logs

```bash
# View all logs
kubectl logs -l app=whatsapp-webhook -n meta-whatsapp -f

# View logs for specific pod
kubectl logs <pod-name> -n meta-whatsapp -f
```

### Health Checks

```bash
# Check health status
kubectl exec -it <pod-name> -n meta-whatsapp -- curl http://localhost:8000/health
```

## 📊 Scaling

### Horizontal Scaling

```bash
# Scale the deployment
kubectl scale deployment whatsapp --replicas=3 -n meta-whatsapp

# Verify scaling
kubectl get pods -l app=whatsapp-webhook -n meta-whatsapp
```

### Resource Limits

The deployment includes the following resource limits:
- **Requests**: 100m CPU, 128Mi memory
- **Limits**: 500m CPU, 512Mi memory

## 🔒 Security

- **Secrets Management**: Sensitive data stored in Kubernetes secrets
- **Non-root User**: Container runs as non-root user
- **HTTPS**: Ingress configured with SSL/TLS
- **Network Policies**: Restrict network access (if configured)

## 🛠️ Troubleshooting

### Common Issues

1. **Pod Not Starting**
   ```bash
   kubectl describe pod <pod-name> -n meta-whatsapp
   ```

2. **Environment Variables Missing**
   ```bash
   kubectl get secret whatsapp-secrets -n meta-whatsapp -o yaml
   ```

3. **Zagent API Connection Failed**
   ```bash
   # Check network connectivity
   kubectl exec -it <pod-name> -n meta-whatsapp -- curl -v https://app.zagent.stage.yavar.ai/v2
   ```

4. **WhatsApp Webhook Issues**
   - Verify webhook URL is accessible
   - Check verify token matches WhatsApp settings
   - Review logs for error messages

### Logs Analysis

```bash
# Filter logs by keyword
kubectl logs -l app=whatsapp-webhook -n meta-whatsapp | grep "ERROR"

# View recent logs
kubectl logs -l app=whatsapp-webhook -n meta-whatsapp --tail=100
```

## 🔄 Updates and Maintenance

### Update Application

```bash
# Build and push new image
docker build -t zinfradevv1.azurecr.io/meta-whatsapp:v2.0.0 .
docker push zinfradevv1.azurecr.io/meta-whatsapp:v2.0.0

# Update deployment
kubectl set image deployment/whatsapp whatsapp=zinfradevv1.azurecr.io/meta-whatsapp:v2.0.0 -n meta-whatsapp
```

### Rolling Restart

```bash
# Restart deployment
kubectl rollout restart deployment/whatsapp -n meta-whatsapp

# Check rollout status
kubectl rollout status deployment/whatsapp -n meta-whatsapp
```

## 📞 Support

For issues related to:
- **WhatsApp API**: Check Facebook Developer documentation
- **Zagent API**: Contact Zagent support team
- **Kubernetes**: Refer to Kubernetes documentation
- **Application**: Check application logs and configuration

---

**Note**: Ensure all environment variables and secrets are properly configured before deploying to production.