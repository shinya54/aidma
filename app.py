import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os, time, json

# ================= 設定情報 =================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = "1iJXDxkFM7A-YGg1BvgtOhXS_AYdIN5goDQWHvSj79_k"
# ===========================================

st.set_page_config(page_title="爆速・テレアポ分析AI", page_icon="⚡")
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
    """今使えるモデルを自動で探す（あなたの環境で動く唯一のロジック）"""
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

st.title("⚡ チーム用：テレアポ高精度分析")
st.success("ファイルをドロップするだけで全自動解析し、スプレッドシートに記録します。")

uploaded_files = st.file_uploader("mp3ファイルをドロップ", type=["mp3"], accept_multiple_files=True)

if st.button("🚀 爆速解析スタート"):
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

        # ★★★ プロンプトを極限まで最適化 ★★★
        system_prompt = """あなたはプロの営業監査官です。
録音から、営業担当者の「切り返し」の回数を判定してください。

【判定基準：1回とカウントする条件】
顧客が明確に拒絶した直後に、
営業が話を継続し、最終的に「具体的な日程や時間の打診」を行った場合のみを1回とします。

【❌ カウント対象外（重要）】
・「担当者不在」「外出中」「会議中」と言われた不在の際の受付対応。
・拒絶後に「商品の説明」や「メリット」を語っただけで、最後に日程打診をせずに引き下がった場合。
・断られる前の、最初の挨拶段階での日程打診。

【出力ルール】
・結果は「数値のみ」または「数値+⚪︎」を出力してください。
・アポイントが成功（承諾）した場合は、数値の後に「⚪︎」を付けてください（例: 1⚪︎）。
・条件に合う切り返しがない場合は「0」と出力してください。"""

        model = genai.GenerativeModel(
            model_name=correct_model_name,
            generation_config={"temperature": 0},
            safety_settings=safe_settings,
            system_instruction=system_prompt
        )
        
        progress_bar = st.progress(0)
        results_table = []
        
        for i, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} を分析中... ({i+1}/{len(uploaded_files)})")
            
            try:
                response = model.generate_content([
                    "ルールに従って、不在や単なる説明を除外し、切り返しの回数（アポ成功なら⚪︎を付与）を数値のみで回答してください。",
                    {"mime_type": "audio/mp3", "data": file.getvalue()}
                ])
                
                if response.candidates and response.candidates[0].content.parts:
                    count = response.text.strip()
                else:
                    count = "0"
                
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                if sheets_service:
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID, range="シート1!A1",
                        valueInputOption='USER_ENTERED', 
                        body={'values': [[file.name, count, now]]}
                    ).execute()

                st.write(f"  ✅ {file.name} -> **{count}**")
                results_table.append({"ファイル名": file.name, "回数": count, "状態": "✅ 完了"})
                
            except Exception as e:
                st.error(f"❌ {file.name} でエラー: {e}")
                results_table.append({"ファイル名": file.name, "回数": "-", "状態": f"エラー"})

            progress_bar.progress((i + 1) / len(uploaded_files))

        st.success("すべての解析が終了しました！")
        st.table(results_table)
