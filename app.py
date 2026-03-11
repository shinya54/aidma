import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os, time, json

# ================= 設定情報 =================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = "1iJXDxkFM7A-YGg1BvgtOhXS_AYdIN5goDQWHvSj79_k"
# ===========================================

st.set_page_config(page_title="爆速・テレアポ分析AI", page_icon="⚡", layout="wide")
genai.configure(api_key=GEMINI_API_KEY)

# --- 認証関数 ---
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
        pro_models = [m for m in models if '1.5-pro' in m]
        return pro_models[0] if pro_models else "models/gemini-1.5-pro-latest"
    except:
        return "models/gemini-1.5-pro-latest"

# --- サイドバーでプロンプトを編集 ---
with st.sidebar:
    st.header("⚙️ 解析ルールの設定")
    st.write("ここでAIへの指示を自由に変更できます。")
    custom_prompt = st.text_area(
        "AIへの指示（プロンプト）",
        value="""あなたはプロの営業監査官です。以下のルールに従って、テレアポ録音内の「切り返し」の回数をカウントし、数値のみを出力してください。

【切り返しの定義】
・顧客が「結構です」「間に合ってます」「高い」などの『拒絶・断り』を発言した直後に、営業担当者が会話を継続した上で日程を打診した回数ををしたセットを「1回」とカウントします。
　　断られる前の日程打診は回数には入れないでください。会話を継続させても、日程打診まで続けなければノーカウントです。アポイントに繋がったものは回数の後に「⚪︎」と記載してください。切り返し1回でアポになったら「1⚪︎」と記載してください。""",
        height=400
    )
    st.info("※変更は即座に反映されます。")

# --- メイン画面 ---
st.title("⚡ チーム用：テレアポ高精度分析")

uploaded_files = st.file_uploader("mp3ファイルをドロップ", type=["mp3"], accept_multiple_files=True)

if st.button("🚀 爆速解析スタート"):
    if not uploaded_files:
        st.error("ファイルを選択してください。")
    else:
        sheets_service = get_sheets_service()
        correct_model_name = get_working_model()
        
        # 安全設定
        safe_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # 画面で入力されたプロンプトを使ってAIを起動
        model = genai.GenerativeModel(
            model_name=correct_model_name,
            generation_config={"temperature": 0},
            safety_settings=safe_settings,
            system_instruction=custom_prompt # ← ここがポイント！
        )
        
        progress_bar = st.progress(0)
        results_table = []
        
        for i, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} を分析中...")
            try:
                response = model.generate_content([
                    "録音を分析し、指示されたルールに従って数値のみで出力してください。",
                    {"mime_type": "audio/mp3", "data": file.getvalue()}
                ])
                count = response.text.strip() if response.text else "0"
                
                # スプシ書き込み
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                if sheets_service:
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID, range="シート1!A1",
                        valueInputOption='USER_ENTERED', 
                        body={'values': [[file.name, count, now]]}
                    ).execute()

                results_table.append({"ファイル名": file.name, "回数": count, "状態": "✅ 完了"})
            except Exception as e:
                results_table.append({"ファイル名": file.name, "回数": "-", "状態": f"エラー"})

            progress_bar.progress((i + 1) / len(uploaded_files))

        st.table(results_table)
