import streamlit as st
import openai
import os
import json

st.set_page_config(page_title="Multi-Nodule TI-RADS Agent", layout="wide", page_icon="🦋")
st.title("🦋 Multi-Nodule TI-RADS Automated Agent")
st.write("Processes single or multiple thyroid nodules into dedicated Body and Impression sections.")

api_key = os.getenv("OPENAI_API_KEY", "")
if api_key:
    openai.api_key = api_key
else:
    st.sidebar.warning("⚠️ OpenAI API Key not detected in system environment.")

def calculate_tirads_tier(points):
    if points <= 1: return "TR1 (Benign)", "No biopsy or follow-up required."
    elif points == 2: return "TR2 (Not Suspicious)", "No biopsy or follow-up required."
    elif points == 3: return "TR3 (Mildly Suspicious)", "Biopsy if ≥ 2.5 cm. Follow-up if ≥ 1.5 cm."
    elif 4 <= points <= 6: return "TR4 (Moderately Suspicious)", "Biopsy if ≥ 1.5 cm. Follow-up if ≥ 1.0 cm."
    else: return "TR5 (Highly Suspicious)", "Biopsy if ≥ 1.0 cm. Follow-up if ≥ 0.5 cm."

pasted_text = st.text_area("Paste clinical ultrasound text here (can describe multiple nodules):", height=200, placeholder="E.g., Right lobe nodule measuring 1.5cm, solid...")

if st.button("🚀 Process Data & Generate Split Report", type="primary"):
    if not api_key:
        st.error("Please configure an OpenAI API Key before proceeding.")
    elif not pasted_text.strip():
        st.error("Please provide some text notes first.")
    else:
        with st.spinner("AI Agent extracting metrics and computing risk tiers..."):
            try:
                client = openai.OpenAI(api_key=api_key)
                
                # Step 1: Standardized Data Extraction JSON Mode
                extraction_prompt = """
                Extract ALL thyroid nodules found in the text. For EVERY separate nodule, extract its characteristics into a JSON list exactly matching this structure:
                - composition: 'Cystic/spongiform', 'Mixed', or 'Solid'
                - echogenicity: 'Anechoic', 'Hyperechoic/Isoechoic', 'Hypoechoic', or 'Very hypoechoic'
                - shape: 'Wider-than-tall' or 'Taller-than-wide'
                - margin: 'Smooth', 'Ill-defined', 'Lobulated/Irregular', or 'Extrathyroidal extension'
                - foci_list: A list containing zero or more of: 'Macrocalcifications', 'Peripheral', 'Punctate'
                - size: Max dimension as a string (e.g., "1.8")
                - location: Where it is (e.g., "Right Lobe")
                - label: A unique identifier (e.g., "Nodule #1")
                
                Respond ONLY with a valid JSON list.
                """
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": extraction_prompt},
                        {"role": "user", "content": pasted_text}
                    ]
                )

                raw_json = response.choices.message.content.strip()
                nodules_data = json.loads(raw_json)
                
                if isinstance(nodules_data, dict):
                    nodules_list = next(iter(nodules_data.values())) if isinstance(next(iter(nodules_data.values())), list) else [nodules_data]
                else:
                    nodules_list = nodules_data

                # Step 2: Running Independent Calculations
                calculated_payloads = []
                for nodule in nodules_list:
                    pts = 0
                    pts += 0 if "Cystic" in nodule.get("composition","") else (1 if "Mixed" in nodule.get("composition","") else 2)
                    pts += 3 if "Very" in nodule.get("echogenicity","") else (2 if "Hypoechoic" in nodule.get("echogenicity","") else (0 if "Anechoic" in nodule.get("echogenicity","") else 1))
                    pts += 3 if "Taller" in nodule.get("shape","") else 0
                    pts += 2 if "Lobulated" in nodule.get("margin","") else (3 if "Extra" in nodule.get("margin","") else 0)
                    
                    for f in nodule.get("foci_list", []):
                        if "Macro" in f: pts += 1
                        if "Peripheral" in f: pts += 2
                        if "Punctate" in f: pts += 3
                    
                    tier, recommendation = calculate_tirads_tier(pts)
                    nodule["calculated_points"] = pts
                    nodule["tier"] = tier
                    nodule["recommendation"] = recommendation
                    calculated_payloads.append(nodule)

                # Step 3: Enforcing Two-Part Medical Prose Format
                narrative_prompt = """You are an elite clinical endocrine radiologist. Take the provided data and write a formal report divided explicitly into two separate parts:

                PART 1: BODY OF REPORT (FINDINGS)
                - Create a structured text section that describes each nodule's physical location, size, and detailed ultrasound traits (composition, echogenicity, shape, margin, and foci findings) in comprehensive prose paragraphs.

                PART 2: IMPRESSION
                - Provide a clear, bulleted list summarizing each nodule by its final mathematical total points, its ACR TI-RADS tier classification, and the corresponding exact medical management recommendation.
                - Keep this section highly actionable and compact.

                Do not write conversational sentences. Start directly with 'PART 1: BODY OF REPORT'."""
                
                final_text_report = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": narrative_prompt},
                        {"role": "user", "content": f"Generate a split report using this metrics matrix:\n\n{json.dumps(calculated_payloads)}"}
                    ],
                    temperature=0.1
                ).choices.message.content.strip()

                st.subheader("📋 Final Generated Report (Ready to Copy)")
                st.text_area("Final Segmented Output", value=final_text_report, height=380)
                st.info("💡 Copy the respective sections and insert them smoothly into your master documentation templates.")

            except Exception as e:
                st.error(f"An operational error occurred: {str(e)}")
