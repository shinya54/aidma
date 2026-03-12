import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os, time, json, re # ★ <result>タグを抽出するために re を追加しました

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

        # ★ 変更点: Chain of Thought（思考プロセス）を導入したシステムプロンプト
        system_prompt = """あなたはプロの営業監査官です。以下の判定ルールに従って、テレアポ録音内の「切り返し」の回数をカウントしてください。

【判定ルール】
1. 顧客が「結構です」「間に合ってます」「高い」等の『拒絶・断り』を発言する。
2. その直後に、営業担当者が『会話を継続』し、かつ『日程打診（アポイントの提案）』を行う。
この「1と2がセットになった回数」のみをカウントします。

【除外・注意点】
・断られる前の日程打診はカウントしないでください。
・会話を継続させても、日程打診まで続けなければノーカウントです。

【出力ルール】
いきなり数値を出力するのではなく、必ず以下のフォーマットで出力してください。
最初に該当したやり取りの理由を書き出し、最後に <result>数値</result> というタグで結果を囲んでください。アポ獲得時は⚪︎を付けます。

出力例：
思考プロセス：
1回目：顧客「今は間に合ってます」に対し、営業が「来週のご都合はいかがですか？」と打診したためカウント（+1）
2回目：顧客「高いですね」に対し、営業が価値の説明のみを行い、日程打診はしなかったため除外。
最終的にアポには至らなかった。
<result>1</result>"""

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
                # ★ 変更点: ユーザープロンプトもタグ出力の指示に合わせて微調整
                response = model.generate_content([
                    "録音を分析し、ルールに従って思考プロセスを記述した上で、『切り返し』の回数（アポ成功なら⚪︎を付与）を <result> タグで囲んで回答してください。不明な場合は <result>0</result> と出力してください。",
                    {"mime_type": "audio/mp3", "data": file.getvalue()}
                ])
                
                if response.candidates and response.candidates[0].content.parts:
                    full_text = response.text.strip()
                    # ★ 変更点: LLMの回答（長文）から <result>〜</result> の中身の数値だけを抽出
                    match = re.search(r'<result>(.*?)</result>', full_text)
                    if match:
                        count = match.group(1).strip()
                    else:
                        count = "0 (抽出エラー)"
                else:
                    count = "0 (判定不能)"
                
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
