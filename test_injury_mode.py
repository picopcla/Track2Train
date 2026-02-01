
import sys
import os
import datetime
from unittest.mock import MagicMock

# Add current dir to path to import app
sys.path.append(os.getcwd())

# Mock dependencies
sys.modules['google'] = MagicMock()
sys.modules['google.genai'] = MagicMock()
sys.modules['flask'] = MagicMock()
sys.modules['flask_cors'] = MagicMock()
sys.modules['numpy'] = MagicMock()
sys.modules['dateutil'] = MagicMock()
sys.modules['dateutil.parser'] = MagicMock()
sys.modules['dotenv'] = MagicMock()

# Import the function to test
import app

# Mock helpers
app.load_prompt = lambda x: f"PROMPT_NAME: {x} CONTENT: {{data}} KEYWORDS: {{injury_keywords}}"
app.read_weekly_plan = lambda x: None
app.read_weekly_objectives = lambda x: {}
app.load_feedbacks = lambda: {}
app.calculate_type_averages = lambda x, y, limit=10: {
    'count': 0, 
    'allure_moy': 0, 
    'k_moy': 0, 
    'drift_moy': 0, 
    'cadence_moy': 0, 
    'fc_moy': 0,
    'zones_fc': {}
}
app.classify_run_type = lambda x: 'tempo_rapide'
app.gemini_client = MagicMock()
app.gemini_client.models.generate_content.return_value.text = "MOCK AI RESPONSE"

# Test Data with INJURY NOTE
activity = {
    'date': '2026-02-01T10:00:00Z',
    'distance_km': 5.0,
    'duree_sec': 1500,
}

# Feedback containing injury keyword
feedback = {
    'rating_stars': 1,
    'notes': "J'ai eu une grosse douleur au genou au bout de 2km."
}
profile = {}
activities = [activity]

# Run generation
print("🚀 Running generate_coaching_comment with INJURY note...")
try:
    result = app.generate_coaching_comment(activity, feedback, profile, activities)
    print("✅ Result:", result)
    
    if "coaching_run_injury" in result:
        print("✅ SUCCESS: Detected injury and loaded correct prompt.")
    else:
        print("❌ FAILURE: Did not load injury prompt.")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
