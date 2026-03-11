import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os, time, json

# ===========================================
# 1. 基本設定
# ===========================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = "1iJXDxkFM7A-YGg1BvgtOhXS_AYdIN5goDQWHvSj79_k"

# 2. AIへの指示
SYSTEM_PROMPT = """
あなたはプロの営業監査官です。以下のルールに従って、テレアポ録音内の「切り返し」の回数をカウントしてください。

【切り返しの定義】
・顧客が「結構です」「間に合ってます」「高い」などの『拒絶・断り』を発言した直後に、営業担当者が会話を継続した上で日程を打診したセットを「1回」とカウントします。
・断られる前の日程打診は回数には入れないでください。
・会話を継続させても、日程打診まで続けなければノーカウントです。

【出力ルール】
・「数値のみ」を出力してください（例: 2）
・ただし、アポイントに繋がったものは数値の後に「⚪︎」を付けてください（例: 1⚪︎）
・不明な場合は「0」と出力してください。
"""

# ===========================================
# 3. メインプログラム
# ===========================================
st.set_page_config(page_title="爆速・テレアポ分析AI", page_icon="⚡")
genai.configure(api_key=GEMINI_API_KEY)

def get_sheets_service():
    try:
        gcp_info = json.loads(st.secrets["GCP_JSON"])
        creds = Credentials.from_service_account_info(
            gcp_info, scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        st.error(f"スプレッドシート認証エラー: {e}")
        return None

# ★モデル名を最も安定しているものに固定しました
MODEL_NAME = "gemini-1.5-pro"

st.title("⚡ チーム用：テレアポ高精度分析")
uploaded_files = st.file_uploader("mp3ファイルをドロップ", type=["mp3"], accept_multiple_files=True)

if st.button("🚀 爆速解析スタート"):
    if not uploaded_files:
        st.error("ファイルを選択してください。")
    else:
        sheets_service = get_sheets_service()
        # 安全設定を考慮しつつAIモデルを準備
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            generation_config={"temperature": 0},
            system_instruction=SYSTEM_PROMPT
        )
        
        progress_bar = st.progress(0)
        results = []
        
        for i, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} を分析中...")
            try:
                # 録音データの解析
                response = model.generate_content([
                    "録音を分析し、ルールに従って結果のみ（数値または数値+⚪︎）を出力してください。",
                    {"mime_type": "audio/mp3", "data": file.getvalue()}
                ])
                
                # 回答の取り出し（安全フィルター対策付き）
                if response.candidates and response.candidates[0].content.parts:
                    output = response.text.strip()
                else:
                    output = "判定不可"
                
                # スプレッドシートへ保存
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                if sheets_service:
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID, range="シート1!A1",
                        valueInputOption='USER_ENTERED', 
                        body={'values': [[file.name, output, now]]}
                    ).execute()

                results.append({"ファイル名": file.name, "結果": output, "状態": "✅ 完了"})
            except Exception as e:
                st.error(f"解析エラー: {file.name} - {e}")
                results.append({"ファイル名": file.name, "結果": "-", "状態": "❌ エラー"})
            
            progress_bar.progress((i + 1) / len(uploaded_files))
        
        st.table(results)
        st.success("すべての解析が終了しました！")
