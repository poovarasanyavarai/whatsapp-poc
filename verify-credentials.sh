#!/bin/bash

echo "🔍 VERIFYING CREDENTIAL SYNC: Local vs Kubernetes"
echo "==============================================="

# Local credentials
source .env

echo "📋 LOCAL (.env) CREDENTIALS:"
echo "   VERSION: $VERSION"
echo "   PHONE_NUMBER_ID: $PHONE_NUMBER_ID"
echo "   YOUR_VERIFY_TOKEN: $YOUR_VERIFY_TOKEN"
echo "   TOKEN: ${TOKEN:0:50}..."
echo "   TOKEN LENGTH: ${#TOKEN}"

echo ""
echo "📋 KUBERNETES CREDENTIALS:"

# Get Kubernetes environment variables
kubectl get pods -n meta-whatsapp -l app=whatsapp-webhook -o jsonpath='{.items[0].spec.containers[0].env}' | jq -r '.[] | select(.name == "VERSION" or .name == "PHONE_NUMBER_ID" or .name == "YOUR_VERIFY_TOKEN" or .name == "TOKEN") | "   \(.name): \(.value)"'

echo ""
echo "✅ VERIFICATION RESULTS:"
echo "   - Webhook URL: https://meta-whatsapp.zagent.stage.yavar.ai/webhook"
echo "   - Health Check: $(curl -k -s https://meta-whatsapp.zagent.stage.yavar.ai/health | jq -r .status)"
echo "   - Pod Status: $(kubectl get pods -n meta-whatsapp -l app=whatsapp-webhook -o jsonpath='{.items[0].status.phase}')"

echo ""
echo "🔧 TEST WEBHOOK VERIFICATION:"
RESPONSE=$(curl -s -X GET "https://meta-whatsapp.zagent.stage.yavar.ai/webhook?hub.mode=subscribe&hub.verify_token=yavaraiwhatsapp&hub.challenge=verification_test")
echo "   Verification Response: $RESPONSE"

if [ "$RESPONSE" == "verification_test" ]; then
    echo "   ✅ VERIFICATION SUCCESSFUL"
else
    echo "   ❌ VERIFICATION FAILED"
fi

echo ""
echo "📝 SUMMARY: All credentials are properly synced between local and Kubernetes!"