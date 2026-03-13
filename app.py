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
    """【復旧】以前動いていたロジックをそのまま使用します"""
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
        
        # --- 判定精度を極限まで高めるプロンプト ---
        system_prompt = """あなたは営業専門の監査官です。
録音を聞き、以下のルールで「切り返し回数」を数えてください。

【1回とカウントする条件】
以下の2つが連続して行われた場合のみ「1回」です。
1. 顧客が「いらない」「興味ない」「結構です」と断る。
2. その直後に、営業が【具体的な日程や時間の打診】を伴う提案をする。

【❌ カウントしない例（重要）】
・「担当者不在」と言われた場合（不在対応は切り返しではありません）。
・断られた後に、単に「商品の説明」を続けたり「メリット」を並べただけの場合（日程を打診していなければノーカウント）。
・「結構です」と何度も言われても、営業が具体的に「いつ会えるか」を提案していない箇所はすべて無視してください。

【出力形式】
1. 判定根拠（どの発言を切り返しとみなしたか）
2. 最終結果：[数値]（アポ成功なら1⚪︎）"""

        model = genai.GenerativeModel(
            model_name=correct_model_name,
            generation_config={"temperature": 0},
            system_instruction=system_prompt
        )
        
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} を分析中...")
            try:
                response = model.generate_content([
                    "ルールに従って分析し、最終結果：[数値] の形式で出力してください。不在は除外してください。",
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
        st.success("完了しました！")
