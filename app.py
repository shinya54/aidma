import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os, time, json, re

# ================= 設定情報 =================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = "1iJXDxkFM7A-YGg1BvgtOhXS_AYdIN5goDQWHvSj79_k"
# ===========================================

st.set_page_config(page_title="高精度・テレアポ分析AI", page_icon="⚡")
genai.configure(api_key=GEMINI_API_KEY)

def get_sheets_service():
    try:
        gcp_info = json.loads(st.secrets["GCP_JSON"])
        creds = Credentials.from_service_account_info(
            gcp_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        st.error(f"スプレッドシートの認証エラー: {e}")
        return None

def get_working_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        flash_models = [m for m in models if '1.5-flash' in m]
        return flash_models[0] if flash_models else "models/gemini-1.5-flash"
    except:
        return "models/gemini-1.5-flash"

st.title("⚡ テレアポ分析AI (精度特化・バグ防止Ver)")

uploaded_files = st.file_uploader("mp3ファイルをドロップ", type=["mp3"], accept_multiple_files=True)

if st.button("🚀 解析スタート"):
    if not uploaded_files:
        st.error("ファイルを選択してください。")
    else:
        sheets_service = get_sheets_service()
        model_name = get_working_model()
        
        # --- 判定基準を極限まで具体化したプロンプト ---
        system_prompt = """あなたは営業専門の監査官です。
録音を聞き、以下の【1セットの定義】に合致する箇所がいくつあるか数えてください。

【1セットの定義】
以下のAとBが「この順番で」行われた場合のみ、1回とカウントします。
A. 顧客が「結構です」「いらない」「間に合っている」と拒絶する。
B. その直後に、営業が【具体的な日程や時間の打診】を行う。

※重要：単に商品の説明を続けたり、不在を確認したりするだけではカウントしないでください。必ず「日程の打診」を伴う必要があります。

【出力形式】
1. 判定の根拠（例：〇分〇秒で拒絶。その直後に〇〇と日程を打診したため1回と判定）
2. 不在や単なる説明のため除外した理由（もしあれば）
3. 最終結果：[数値]（アポ成功なら1⚪︎）"""

        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"temperature": 0, "max_output_tokens": 800},
            system_instruction=system_prompt
        )
        
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} を分析中...")
            try:
                response = model.generate_content([
                    "録音を分析し、最終結果：[数値] の形式で出力してください。",
                    {"mime_type": "audio/mp3", "data": file.getvalue()}
                ])
                
                res_text = response.text
                match = re.search(r"最終結果：\[(.*?)\]", res_text)
                final_count = match.group(1) if match else "0"
                
                # スプシ保存
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                if sheets_service:
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID, range="シート1!A1",
                        valueInputOption='USER_ENTERED', 
                        body={'values': [[file.name, final_count, now]]}
                    ).execute()

                with st.expander(f"✅ {file.name} の分析根拠"):
                    st.write(res_text)
                
                st.write(f"結果: **{final_count}**")
                
            except Exception as e:
                st.error(f"❌ {file.name} でエラー: {e}")

            progress_bar.progress((i + 1) / len(uploaded_files))
        st.success("解析完了！")
