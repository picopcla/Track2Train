#!/bin/bash
# Kill old instances
pkill -f "python.*app.py" 2>/dev/null
sleep 2

# Start app in background
nohup .venv/bin/python app.py > /tmp/app_running.log 2>&1 &
APP_PID=$!

echo "Starting app (PID: $APP_PID)..."

# Wait for app to start
for i in {1..15}; do
  sleep 1
  if curl -s http://127.0.0.1:5002/ > /dev/null 2>&1; then
    echo "✅ App is ready!"
    break
  fi
  echo "Waiting... ($i/15)"
done

# Test segments display
echo ""
echo "Testing segments in dashboard..."
SEGMENTS_FOUND=$(curl -s http://127.0.0.1:5002/ | grep -o "Analyse par tronçons" | wc -l)

if [ "$SEGMENTS_FOUND" -gt 0 ]; then
  echo "✅ Segments section found in HTML ($SEGMENTS_FOUND occurrences)"
else
  echo "❌ Segments section NOT found in HTML"
fi

# Show last 20 lines of app log
echo ""
echo "Last 20 lines of app log:"
tail -20 /tmp/app_running.log
