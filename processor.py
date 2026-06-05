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
    
    # --- THE FIX: Force specific columns to accept text/strings ---
    # Prevents 'float64' errors if the uploaded Excel columns are completely empty.
    columns_to_force_string = ['pronunciation_guide', 'code_mixed', 'corrections', 'validated_by', 'speaker_gender']
    for col in columns_to_force_string:
        if col in df.columns:
            df[col] = df[col].astype('object')
            
    if 'Requires_Manual_Review' not in df.columns:
        df['Requires_Manual_Review'] = False

    total_rows = len(df)
    results = []

    for i in range(0, total_rows, BATCH_SIZE):
        chunk = df.iloc[i:i+BATCH_SIZE]
        
        # Prepare the minimal data needed by the LLM
        payload = chunk[['sentence_id', 'text', 'domain', 'style', 'emotion', 'speaker_gender']].to_dict(orient='records')
        
        status_text.text(f"Processing rows {i+1} to {min(i+BATCH_SIZE, total_rows)} of {total_rows}...")
        
        try:
            response = model.generate_content(json.dumps(payload))
            batch_results = json.loads(response.text)
            
            # Map results back to the dataframe
            for res in batch_results:
                idx = df.index[df['sentence_id'] == res['row_id']].tolist()[0]
                
                # Apply Confidence Threshold Logic
                if res.get('confidence_score', 0) >= CONFIDENCE_THRESHOLD:
                    df.at[idx, 'pronunciation_guide'] = res.get('pronunciation_guide', df.at[idx, 'text'])
                    df.at[idx, 'code_mixed'] = res.get('code_mixed', 'No')
                    df.at[idx, 'corrections'] = res.get('corrections', "")
                    df.at[idx, 'validated_by'] = validator_name
                    
                    if res.get('gender_override'):
                        df.at[idx, 'speaker_gender'] = res['gender_override']
                else:
                    # Low confidence -> Flag for the human, touch nothing else
                    df.at[idx, 'Requires_Manual_Review'] = True

        except Exception as e:
            st.error(f"Error on batch {i}: {e}")
            for idx in chunk.index:
                df.at[idx, 'Requires_Manual_Review'] = True

        progress_bar.progress(min((i + BATCH_SIZE) / total_rows, 1.0))
        time.sleep(15) # Rate limit safety for Gemini Free Tier

    return df