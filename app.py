import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os, time, json, re

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
    """あなたが持っている『動くロジック』そのままです"""
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
st.success("一度全文を書き起こしてから判定する、高精度モードで動作中です。")

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

        # ★ここからプロンプトを変更（高精度版）★
        system_prompt = """あなたはプロの営業監査官です。
以下の手順で、テレアポ録音の「切り返し」を分析してください。

【手順】
1. 録音内容をすべて文字起こししてください。
2. 文字起こしから「顧客の断り」と、その直後の「営業による会話継続＋日程打診」のセットを探します。
3. そのセットが何回あったか数えてください。アポ成功なら数値に「⚪︎」を付けます。

【出力形式】
まず文字起こしを書き出し、最後に必ず「最終結果：[判定値]」という形式で締めてください。
例：最終結果：[1⚪︎]"""

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
                    "ルールに従って、文字起こしと判定を行ってください。",
                    {"mime_type": "audio/mp3", "data": file.getvalue()}
                ])
                
                full_text = response.text
                
                # AIが書いた文字の中から [ ] の中身（1⚪︎など）を抜き出す
                match = re.search(r"最終結果：\[(.*?)\]", full_text)
                count = match.group(1) if match else "0"
                
                # スプシ書き込み
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                if sheets_service:
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID, range="シート1!A1",
                        valueInputOption='USER_ENTERED', 
                        body={'values': [[file.name, count, now]]}
                    ).execute()

                st.write(f"  ✅ {file.name} -> **{count}**")
                # 画面で文字起こしも見れるようにしました
                with st.expander("分析詳細を表示"):
                    st.write(full_text)
                    
                results_table.append({"ファイル名": file.name, "回数": count, "状態": "✅ 完了"})
                
            except Exception as e:
                st.error(f"❌ {file.name} でエラー: {e}")
                results_table.append({"ファイル名": file.name, "回数": "-", "状態": f"エラー"})

            progress_bar.progress((i + 1) / len(uploaded_files))

        st.success("すべての解析が終了しました！")
        st.table(results_table)
