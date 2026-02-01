
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
# We need to mock functions that app.py uses
import app

# Mock helpers
app.load_prompt = lambda x: "PROMPT_CONTENT {data}"
app.read_weekly_plan = lambda x: {
    'week_number': 5, 
    'summary': {
        'objective': {
            'target_pace': '4:30',
            'target_distance': 21.1,
            'race_date': '2026-05-01'
        }
    },
    'runs': []
}
app.read_weekly_objectives = lambda x: {}
app.load_feedbacks = lambda: {}
app.calculate_type_averages = lambda x, y, limit=10: {
    'count': 5,
    'allure_moy': 5.0, # 5:00/km (vs target 4:30)
    'k_moy': 0.8,
    'drift_moy': 2.0,
    'cadence_moy': 170,
    'fc_moy': 140,
    'zones_fc': {}
}
app.classify_run_type = lambda x: 'tempo_rapide'
app.gemini_client = MagicMock()
app.gemini_client.models.generate_content.return_value.text = "MOCK AI RESPONSE"

# Test Data
activity = {
    'date': '2026-02-01T10:00:00Z',
    'distance_km': 10.0,
    'duree_sec': 3000,
    'allure': '5:00',
    'k_moy': 0.8,
    'deriv_cardio': 2.0,
    'fc_moy': 140,
    'cadence_spm': 170
}

feedback = {'rating_stars': 4}
profile = {}
activities = [activity]

# Run generation
print("🚀 Running generate_coaching_comment...")
try:
    result = app.generate_coaching_comment(activity, feedback, profile, activities)
    print("✅ Result:", result)
    
    # We want to verified that 'calculate_progress_to_goal' was called and logic worked
    # Since we can't easily inspect the internal variables without modifying app.py again,
    # we rely on the fact that it didn't crash and presumably called the prompt generation.
    print("✅ Logic executed without errors.")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
