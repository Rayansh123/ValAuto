# processor.py
import pandas as pd
import json
import time
import re
import google.generativeai as genai
import streamlit as st
from prompts import SYSTEM_INSTRUCTION
from config import MODEL_NAME, BATCH_SIZE, CONFIDENCE_THRESHOLD

def initialize_gemini(api_key):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config={"response_mime_type": "application/json"}
    )

def process_dataframe(df, api_key, validator_name, progress_bar, status_text):
    model = initialize_gemini(api_key)
    
    # Safety check for empty columns
    columns_to_force_string = ['pronunciation_guide', 'code_mixed', 'corrections', 'validated_by', 'speaker_gender']
    for col in columns_to_force_string:
        if col in df.columns:
            df[col] = df[col].astype('object')
            
    if 'Requires_Manual_Review' not in df.columns:
        df['Requires_Manual_Review'] = False
        
    # NEW: Add a column to track the exact AI score
    if 'AI_Confidence_Score' not in df.columns:
        df['AI_Confidence_Score'] = 0.0

    total_rows = len(df)

    for i in range(0, total_rows, BATCH_SIZE):
        chunk = df.iloc[i:i+BATCH_SIZE]
        payload = chunk[['sentence_id', 'text', 'domain', 'style', 'emotion', 'speaker_gender']].to_dict(orient='records')
        
        status_text.text(f"Processing rows {i+1} to {min(i+BATCH_SIZE, total_rows)} of {total_rows}...")
        
        # --- THE NEW RETRY LOGIC (Exponential Backoff) ---
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content(json.dumps(payload))
                raw_text = response.text
                
                # --- THE BULLETPROOF FIX: Regex JSON Extraction ---
                # This searches for the array brackets [] and ignores everything outside them
                match = re.search(r'\[.*\]', raw_text, re.DOTALL)
                
                if match:
                    json_str = match.group(0)
                    batch_results = json.loads(json_str)
                    success = True
                    break # Exit the retry loop if successful!
                else:
                    raise ValueError("No JSON array found in the AI response.")
                
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "Quota" in error_msg:
                    status_text.text(f"⚠️ Rate limit hit. Waiting 20 seconds to auto-retry... (Attempt {attempt+1} of {max_retries})")
                    time.sleep(20) # Wait out the Google penalty box
                else:
                    st.error(f"Error on batch {i}: {e}")
                    break # Break on non-rate-limit errors (like JSON parsing)

        # If it failed all retries, flag the batch
        if not success:
            for idx in chunk.index:
                df.at[idx, 'Requires_Manual_Review'] = True
                df.at[idx, 'AI_Confidence_Score'] = -1.0 
            continue # Skip the rest of the logic and move to the next batch

        # --- APPLYING SUCCESSFUL DATA (Remains unchanged) ---
        for res in batch_results:
            idx = df.index[df['sentence_id'] == res['row_id']].tolist()[0]
            
            score = float(res.get('confidence_score', 0.0))
            df.at[idx, 'AI_Confidence_Score'] = score
            
            if score >= CONFIDENCE_THRESHOLD:
                # 1. Pronunciation Guide Replacement
                new_text = str(df.at[idx, 'text'])
                loan_words = res.get('loan_words_found', [])
                
                if loan_words:
                    for word_pair in loan_words:
                        dev = word_pair.get('devanagari', '')
                        eng = word_pair.get('english', '')
                        if dev and eng:
                            new_text = new_text.replace(dev, eng)
                    df.at[idx, 'code_mixed'] = 'Yes'
                else:
                    df.at[idx, 'code_mixed'] = 'No'
                    
                df.at[idx, 'pronunciation_guide'] = new_text

                # 2. Corrections String
                mismatches = []
                vals = res.get('validations', {})
                if vals.get('domain_mismatch'): mismatches.append("Domain: mismatch")
                if vals.get('style_mismatch'): mismatches.append("Style: mismatch")
                if vals.get('emotion_mismatch'): mismatches.append("Emotion: mismatch")
                
                df.at[idx, 'corrections'] = ", ".join(mismatches)
                
                # 3. Validation and Gender
                df.at[idx, 'validated_by'] = validator_name
                if res.get('gender_override'):
                    df.at[idx, 'speaker_gender'] = res['gender_override']
            else:
                df.at[idx, 'Requires_Manual_Review'] = True

        progress_bar.progress(min((i + BATCH_SIZE) / total_rows, 1.0))
        time.sleep(15) # Standard safety delay between successful batches

    return df