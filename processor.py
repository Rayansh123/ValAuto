# processor.py
import pandas as pd
import json
import time
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
        
        try:
            response = model.generate_content(json.dumps(payload))
            
            # --- THE FIX: Clean the JSON string to prevent Decoder Errors ---
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                # Remove markdown backticks and 'json' keyword
                raw_text = raw_text.strip("`").removeprefix("json").strip()
                
            batch_results = json.loads(raw_text)
            
            for res in batch_results:
                idx = df.index[df['sentence_id'] == res['row_id']].tolist()[0]
                
                # Extract and Save the Confidence Score
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

        except Exception as e:
            st.error(f"Error on batch {i}: JSON parse failure. {e}")
            for idx in chunk.index:
                df.at[idx, 'Requires_Manual_Review'] = True
                df.at[idx, 'AI_Confidence_Score'] = -1.0 # -1 means API/JSON error

        progress_bar.progress(min((i + BATCH_SIZE) / total_rows, 1.0))
        time.sleep(15) 

    return df