#!/bin/bash

# Capture Care - GitHub Backup Script
# This script helps you back up the codebase to a new GitHub repository

set -e

REPO_DIR="/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"
cd "$REPO_DIR"

echo "🚀 Capture Care - GitHub Backup Script"
echo "======================================"
echo ""

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "📦 Initializing Git repository..."
    git init
    echo "✅ Git repository initialized"
else
    echo "✅ Git repository already initialized"
fi

# Add all files (respecting .gitignore)
echo ""
echo "📝 Adding files to Git..."
git add .

# Check if there are changes to commit
if git diff --staged --quiet; then
    echo "ℹ️  No changes to commit"
else
    echo "💾 Committing changes..."
    git commit -m "Backup: Capture Care System - Complete codebase

Features:
- Patient management with health data integration
- Calendar and appointment scheduling
- AI health reporting (Grok 3 / GPT-4)
- Twilio SMS, Voice, and Video calls
- Withings health device integration
- HeyGen AI video avatar generation
- Email notifications and health reports
- Stripe billing integration
- Cliniko practice management integration
- Google Sheets and Calendar sync

Backup date: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "✅ Changes committed"
fi

echo ""
echo "📋 Next Steps:"
echo "=============="
echo ""
echo "1. Create a new repository on GitHub:"
echo "   - Go to https://github.com/new"
echo "   - Name it: capture-care-system (or your preferred name)"
echo "   - Choose Private or Public"
echo "   - DO NOT initialize with README, .gitignore, or license"
echo ""
echo "2. Add the remote and push:"
echo ""
echo "   git remote add origin https://github.com/YOUR_USERNAME/capture-care-system.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "   OR if you prefer SSH:"
echo ""
echo "   git remote add origin git@github.com:YOUR_USERNAME/capture-care-system.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "3. If you need to set up GitHub authentication:"
echo "   - For HTTPS: Use a Personal Access Token (Settings > Developer settings > Personal access tokens)"
echo "   - For SSH: Set up SSH keys (Settings > SSH and GPG keys)"
echo ""
echo "✅ Repository is ready for backup!"
echo ""
echo "Current branch: $(git branch --show-current 2>/dev/null || echo 'main')"
echo "Total commits: $(git rev-list --count HEAD 2>/dev/null || echo '0')"

