# config.py

# Model Settings
MODEL_NAME = "gemini-1.5-flash"
BATCH_SIZE = 15
CONFIDENCE_THRESHOLD = 0.85

# Expected Excel Columns (For Validation)
EXPECTED_COLUMNS = [
    "sentence_id", "text", "pronunciation_guide", "transliteration", 
    "code_mixed", "domain", "style", "emotion", "sentence_length", 
    "validated_by", "corrections", "speaker_gender", "speaker_id"
]

# Glossary to help the LLM catch difficult technical words
DOMAIN_GLOSSARY = [
    "रिएक्टर -> reactor",
    "डेटा -> data",
    "सर्वर -> server",
    "पैथोलॉजी -> pathology",
    "एल्गोरिदम -> algorithm"
]