# app.py
import streamlit as st
import pandas as pd
from processor import process_dataframe
from config import EXPECTED_COLUMNS
import io

st.set_page_config(page_title="TTS Validator Pipeline", layout="wide")

st.title("🎙️ TTS Dataset AI Validator")
st.markdown("Automated QA for Pronunciation, Code-Mixing, and Label Mismatches.")

with st.sidebar:
    st.header("Settings")
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        api_key = st.text_input("Enter Gemini API Key", type="password")
    
    validator_name = st.text_input("Validator Name", placeholder="e.g., Rayansh")

uploaded_file = st.file_uploader("Upload TTS Excel Sheet", type=["xlsx"])

if uploaded_file and api_key and validator_name:
    df = pd.read_excel(uploaded_file)
    
    missing_cols = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    if missing_cols:
        st.warning(f"Warning: Missing expected columns: {missing_cols}")
    
    st.write("### Data Preview")
    st.dataframe(df.head())

    if st.button("🚀 Run AI Validation Pipeline"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("Pipeline running..."):
            processed_df = process_dataframe(df, api_key, validator_name, progress_bar, status_text)
            
        status_text.text("✅ Processing Complete!")
        
        # --- THIS IS THE NEW SPLIT LOGIC ---
        
        # 1. Split into two dataframes based on the confidence flag
        review_df = processed_df[processed_df['Requires_Manual_Review'] == True]
        clean_df = processed_df[processed_df['Requires_Manual_Review'] == False]
        
        # Optional: Remove the tracking column from the clean sheet so the recording team doesn't see it
        if 'Requires_Manual_Review' in clean_df.columns:
            clean_df = clean_df.drop(columns=['Requires_Manual_Review'])

        # 2. Display the flagged items in the UI for a quick preview
        if not review_df.empty:
            st.warning(f"⚠️ {len(review_df)} rows flagged for manual review due to low confidence.")
            st.dataframe(review_df)
        else:
            st.success("All rows processed with high confidence!")

        # 3. Write to a Multi-Tab Excel File
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Tab 1: Clean Data
            clean_df.to_excel(writer, index=False, sheet_name="Ready_for_Recording")
            
            # Tab 2: Flagged Data (Only create this tab if there are actually flagged rows)
            if not review_df.empty:
                review_df.to_excel(writer, index=False, sheet_name="Requires_Human_Review")
        
        # 4. The Download Button
        st.download_button(
            label="📥 Download Split Excel File",
            data=buffer,
            file_name="validated_tts_dataset_split.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

elif not validator_name:
    st.info("Please enter a Validator Name to proceed.")
elif not api_key:
    st.info("Please provide a Gemini API Key to proceed.")