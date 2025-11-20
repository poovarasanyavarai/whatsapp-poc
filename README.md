# WhatsApp Webhook API

A FastAPI-based WhatsApp webhook receiver that handles text messages, images, and videos along with customer details.

## Features

- ✅ WhatsApp webhook verification
- ✅ Receive text, image, and video messages
- ✅ Extract customer details
- ✅ Download media files (images/videos)
- ✅ Comprehensive logging system
- ✅ Docker support
- ✅ Health check endpoint

## Setup

### 1. Clone and Set Up Environment

```bash
# Clone the repository
git clone <repository-url>
cd whatsapp-webhook

# Copy environment file
cp .env.example .env

# Edit .env with your WhatsApp Business API credentials
nano .env
```

### 2. Environment Variables

Update `.env` file with your WhatsApp Business API credentials:

```env
WHATSAPP_VERIFY_TOKEN=your_verify_token_here
WHATSAPP_ACCESS_TOKEN=your_access_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
WHATSAPP_APP_SECRET=your_app_secret_here
```

### 3. Run with Docker

```bash
# Using docker-compose (recommended)
docker-compose up -d

# Or using Docker directly
docker build -t whatsapp-webhook .
docker run -p 8000:8000 --env-file .env whatsapp-webhook
```

### 4. Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn main:app --reload
```

## API Endpoints

### Webhook Endpoints

- **GET `/webhook`** - Webhook verification (WhatsApp will call this)
- **POST `/webhook`** - Receive messages from WhatsApp

### Health Check

- **GET `/health`** - Health check endpoint
- **GET `/`** - Root endpoint to check API status

## WhatsApp Callback URL

For WhatsApp Business API configuration, use this URL:

```
https://your-domain.com/webhook
```

## API Usage Examples

### Test Webhook Verification

```bash
# Test webhook verification (replace with your actual verify token)
curl -X GET "http://localhost:8001/webhook?hub.mode=subscribe&hub.verify_token=your_verify_token_here&hub.challenge=test_challenge"
```

### Test Health Check

```bash
# Check API health
curl -X GET http://localhost:8001/health

# Response
{
  "status": "healthy",
  "timestamp": "2025-11-19T05:21:28.577202"
}
```

### Test Root Endpoint

```bash
# Check if API is running
curl -X GET http://localhost:8001/

# Response
{
  "message": "WhatsApp Webhook API is running",
  "status": "active"
}
```

### Simulate WhatsApp Message (Testing)

```bash
# Send a test message to the webhook (for testing purposes)
curl -X POST http://localhost:8001/webhook \
  -H "Content-Type: application/json" \
  -H "x-hub-signature-256: sha256=test_signature" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "field": "messages",
        "value": {
          "messages": [{
            "from": "1234567890",
            "id": "msg_id_123",
            "timestamp": "1700000000",
            "type": "text",
            "text": {
              "body": "Hello, this is a test message!"
            }
          }],
          "contacts": [{
            "wa_id": "1234567890",
            "profile": {
              "name": "John Doe"
            }
          }]
        }
      }]
    }]
  }'
```

### Simulate Image Message (Testing)

```bash
# Send a test image message
curl -X POST http://localhost:8001/webhook \
  -H "Content-Type: application/json" \
  -H "x-hub-signature-256: sha256=test_signature" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "field": "messages",
        "value": {
          "messages": [{
            "from": "1234567890",
            "id": "msg_img_123",
            "timestamp": "1700000000",
            "type": "image",
            "image": {
              "id": "media_id_456",
              "caption": "Check out this image!"
            }
          }],
          "contacts": [{
            "wa_id": "1234567890",
            "profile": {
              "name": "Jane Smith"
            }
          }]
        }
      }]
    }]
  }'
```

## Production Deployment

### Ngrok (for testing)

```bash
# Expose local port to internet
ngrok http 8001

# Use the generated https://xxxxx.ngrok.io/webhook URL in WhatsApp
```

## Webhook Configuration

In your WhatsApp Business API settings, configure the webhook URL:

```
https://your-domain.com/webhook
```

The webhook will:
- Verify the endpoint using the verify token
- Receive and process incoming messages
- Extract customer details
- Download media files (images/videos)
- Log all activities

## Message Types Supported

- **Text messages**: Extract text content
- **Images**: Download image files + captions
- **Videos**: Download video files + captions

## Customer Information

The webhook extracts:
- WhatsApp ID (`wa_id`)
- Customer name
- Phone number
- Message timestamp
- Message type

## Logging

The application includes comprehensive logging:
- Logs are written to console
- Different log levels (INFO, WARNING, ERROR)
- Detailed error reporting
- Message processing logs

## Development

### Project Structure

```
├── main.py              # Main FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker configuration
├── docker-compose.yml  # Docker Compose configuration
├── .env.example       # Environment variables template
└── README.md          # This file
```

### Database Integration

To add database storage, modify the `store_message_data` function in `main.py`:

```python
# Example with MongoDB
async def store_message_data(customer_id, customer_info, message_id, timestamp, message_type, content, media_file):
    await db.messages.insert_one({
        "customer_id": customer_id,
        "customer_info": customer_info,
        "message_id": message_id,
        "timestamp": datetime.fromtimestamp(int(timestamp)),
        "message_type": message_type,
        "content": content,
        "media_file": media_file
    })
```

## Security

- ✅ Webhook signature verification
- ✅ Input validation
- ✅ Error handling
- ✅ Non-root Docker user

## Monitoring

- Health check endpoint at `/health`
- Docker health checks
- Comprehensive logging
- Error tracking

## Troubleshooting

1. **Webhook verification fails**: Check your `VERIFY_TOKEN` matches in WhatsApp settings
2. **Messages not received**: Verify webhook URL is accessible and HTTPS
3. **Media download fails**: Check `ACCESS_TOKEN` is valid and has proper permissions
4. **Docker container crashes**: Check logs with `docker logs whatsapp-webhook`

## License

MIT License - see LICENSE file for details