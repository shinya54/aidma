import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os, time, json, re

# ================= 設定情報 =================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = "1iJXDxkFM7A-YGg1BvgtOhXS_AYdIN5goDQWHvSj79_k"
# ===========================================

st.set_page_config(page_title="高精度・テレアポ分析AI", page_icon="⚡", layout="wide")
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
    """Flashモデルを優先的に取得"""
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        flash_models = [m for m in models if '1.5-flash' in m]
        if flash_models:
            latest = [m for m in flash_models if 'latest' in m]
            return latest[0] if latest else flash_models[0]
        return "models/gemini-1.5-flash"
    except:
        return "models/gemini-1.5-flash"

st.title("⚡ チーム用：高精度テレアポ分析（文字起こし経由）")
st.info("一度全文を文字起こししてから判定することで、誤判定を減らす『思考連鎖モード』で動作しています。")

uploaded_files = st.file_uploader("mp3ファイルをドロップ", type=["mp3"], accept_multiple_files=True)

if st.button("🚀 集中解析スタート"):
    if not uploaded_files:
        st.error("ファイルを選択してください。")
    else:
        sheets_service = get_sheets_service()
        model_name = get_working_model()
        
        safe_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # --- プロンプト設計 ---
        system_prompt = """あなたはプロの営業監査官です。
以下のステップで、テレアポ録音の「切り返し」を分析してください。

【STEP 1：文字起こし】
録音内容を、話者（営業/顧客）を区別してすべて文字起こししてください。

【STEP 2：切り返しの抽出】
文字起こしから、以下のセットを抽出してください。
・顧客の「拒絶・断り（結構です、忙しい、高い等）」
・その直後の、営業の「会話継続」および「日程打診（具体的なアポ提案）」

【STEP 3：最終判定】
STEP 2のセットが何回あったか数えてください。
アポ成功なら数値に「⚪︎」を、失敗なら数値のみを出力します。

【出力形式の指定】
1. 文字起こし内容を記述
2. 最後に必ず「最終結果：[判定値]」という形式で締めてください。
例：最終結果：[2⚪︎]"""

        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"temperature": 0},
            safety_settings=safe_settings,
            system_instruction=system_prompt
        )
        
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            st.subheader(f"📊 分析対象: {file.name}")
            status_text = st.empty()
            status_text.write(f"⏳ AIが録音を書き起こし中... ({i+1}/{len(uploaded_files)})")
            
            try:
                response = model.generate_content([
                    "ルールに従って、文字起こしと切り返し回数の判定を行ってください。",
                    {"mime_type": "audio/mp3", "data": file.getvalue()}
                ])
                
                full_text = response.text
                
                # 「最終結果：[〇〇]」の部分を抜き出す
                match = re.search(r"最終結果：\[(.*?)\]", full_text)
                final_count = match.group(1) if match else "0"
                
                # スプレッドシートには「回数」のみ保存
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                if sheets_service:
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID, range="シート1!A1",
                        valueInputOption='USER_ENTERED', 
                        body={'values': [[file.name, final_count, now]]}
                    ).execute()

                # 画面には詳細（文字起こし）を表示
                with st.expander(f"👁️ {file.name} の文字起こしと分析詳細を確認"):
                    st.write(full_text)
                
                st.write(f"✅ 判定結果: **{final_count}**")
                st.divider()
                
            except Exception as e:
                st.error(f"❌ {file.name} でエラー: {e}")

            progress_bar.progress((i + 1) / len(uploaded_files))

        st.success("すべての解析が終了しました！")
