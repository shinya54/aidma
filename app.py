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
            gcp_info, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

def get_working_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        flash = [m for m in models if '1.5-flash' in m]
        return flash[0] if flash else "models/gemini-1.5-flash"
    except:
        return "models/gemini-1.5-flash"

st.title("⚡ テレアポ分析AI (基準微調整版)")

uploaded_files = st.file_uploader("mp3ファイルをドロップ", type=["mp3"], accept_multiple_files=True)

if st.button("🚀 解析スタート"):
    if not uploaded_files:
        st.error("ファイルを選択してください。")
    else:
        sheets_service = get_sheets_service()
        model_name = get_working_model()
        
        # --- 「説明を挟むのを許可」しつつ「アポ提案」を必須にするプロンプト ---
        system_prompt = """あなたは営業分析の専門家です。
録音から、以下の【切り返し1セット】に該当する箇所を抽出してください。

【切り返し1セットの定義】
1. 顧客が「結構です」「いらない」と断る。
2. 営業がその後に会話を続け、最終的に「具体的な日程や時間の打診（○分だけ、来週なら等）」を行う。

★ポイント：
・断られた後に「商品の説明」や「メリットの提示」を挟むのはOKです。
・ただし、説明だけで終わらずに、必ず最後に【日程の打診】まで行っていれば「1回」と数えてください。
・説明だけで引き下がった場合は「0回」です。

【除外ルール】
・「担当者不在」や「会議中」と言われた際のやり取りはカウントしないでください。
・ループバグ防止のため、文字起こしはせず、結果と理由だけを出力してください。

【出力形式】
最終結果：[数値]
理由：(例：断られた後に説明を挟み、最終的に〇〇と打診したため1回。 / 説明のみで打診がなかったため0回。など)"""

        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"temperature": 0, "max_output_tokens": 500},
            system_instruction=system_prompt
        )
        
        for file in uploaded_files:
            st.write(f"⏳ {file.name} を分析中...")
            try:
                response = model.generate_content([
                    "ルールに従って判定し、最終結果：[数値] を出してください。",
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

                st.write(f"✅ 結果: **{final_count}**")
                with st.expander("判定理由を確認"):
                    st.write(res_text)
                
            except Exception as e:
                st.error(f"エラー: {file.name} - {e}")

        st.success("すべての解析が終了しました！")
