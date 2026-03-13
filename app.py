import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os, time, json, re

# ================= 設定情報 =================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = "1iJXDxkFM7A-YGg1BvgtOhXS_AYdIN5goDQWHvSj79_k"
# ===========================================

st.set_page_config(page_title="テレアポ分析AI", page_icon="⚡")
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
    """【復旧】以前確実に動いていたモデル選択ロジックです"""
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        pro_models = [m for m in models if '1.5-pro' in m]
        if pro_models:
            latest = [m for m in pro_models if 'latest' in m]
            return latest[0] if latest else pro_models[0]
        flash_models = [m for m in models if '1.5-flash' in m]
        return flash_models[0] if flash_models else models[0]
    except Exception as e:
        return "models/gemini-1.5-pro-latest"

st.title("⚡ テレアポ分析AI")

uploaded_files = st.file_uploader("mp3ファイルをドロップ", type=["mp3"], accept_multiple_files=True)

if st.button("🚀 解析スタート"):
    if not uploaded_files:
        st.error("ファイルを選択してください。")
    else:
        sheets_service = get_sheets_service()
        correct_model_name = get_working_model()
        
        safe_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # --- 基準を反映したプロンプト ---
        system_prompt = """あなたは営業専門の監査官です。
以下の【1セット】の定義に従って、切り返し回数を数えてください。

【切り返し1セットの定義】
1. 顧客が「結構です」「いらない」と断る。
2. 営業がその後に話を続け、最終的に「具体的な日程や時間の打診（○分だけ、来週なら等）」を行う。

★重要な判定基準：
・断られた直後に「商品の説明」や「メリットの提示」を挟むのはOKです。
・ただし、説明だけで終わらずに、その流れの最後で必ず【日程の打診】まで行っていれば「1回」とカウントしてください。
・どれだけ長く説明しても、最終的に日程を打診せずに引き下がった場合は「0回」です。
・「担当者不在」や「外出中」への対応はカウントしません。

【出力形式】
最終結果：[数値]
判定理由：（どの断りに対して、どのような説明を経て、最後にどう日程打診したか）"""

        model = genai.GenerativeModel(
            model_name=correct_model_name,
            generation_config={"temperature": 0},
            safety_settings=safe_settings,
            system_instruction=system_prompt
        )
        
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} を分析中...")
            try:
                response = model.generate_content([
                    "ルールに従って分析し、最終結果：[数値] の形式で出力してください。",
                    {"mime_type": "audio/mp3", "data": file.getvalue()}
                ])
                
                res_text = response.text
                match = re.search(r"最終結果：\[(.*?)\]", res_text)
                final_count = match.group(1) if match else "0"
                
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                if sheets_service:
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID, range="シート1!A1",
                        valueInputOption='USER_ENTERED', 
                        body={'values': [[file.name, final_count, now]]}
                    ).execute()

                with st.expander(f"✅ {file.name} の分析詳細"):
                    st.write(res_text)
                
                st.write(f"結果: **{final_count}**")
                
            except Exception as e:
                st.error(f"❌ {file.name} でエラー: {e}")

            progress_bar.progress((i + 1) / len(uploaded_files))
        st.success("解析完了しました！")
