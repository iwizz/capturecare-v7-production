#!/bin/bash
# Reset the database password for the capturecare user

echo "🔐 Reset Cloud SQL Database Password"
echo "===================================="
echo ""

# Generate a secure random password
NEW_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

echo "📝 New password will be generated automatically"
echo ""
echo "Would you like to:"
echo "  1. Generate a new secure password (recommended)"
echo "  2. Set your own password"
read -p "Choice [1]: " choice
choice=${choice:-1}

if [ "$choice" = "2" ]; then
    echo ""
    echo "Enter your new password:"
    read -s NEW_PASSWORD
    echo ""
    echo "Confirm password:"
    read -s CONFIRM_PASSWORD
    
    if [ "$NEW_PASSWORD" != "$CONFIRM_PASSWORD" ]; then
        echo "❌ Passwords don't match!"
        exit 1
    fi
fi

echo ""
echo "🔄 Resetting password for user 'capturecare'..."
gcloud sql users set-password capturecare \
  --instance=capturecare-db \
  --password="$NEW_PASSWORD"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Password reset successful!"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Your new password is:"
    echo "   $NEW_PASSWORD"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "💡 Save this password - you'll need it for the migration!"
    echo ""
    echo "You can now run the migration:"
    echo "   ./scripts/quick_migrate.sh"
    echo ""
else
    echo ""
    echo "❌ Failed to reset password"
    exit 1
fi

