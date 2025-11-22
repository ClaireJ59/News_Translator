import streamlit as st
import json
import google.generativeai as genai
from PIL import Image
import io

# 頁面設定
st.set_page_config(
    page_title="日文報紙助手 (Gemini版)",
    page_icon="📰",
    layout="wide"
)

# 側邊欄：設定 API Key
with st.sidebar:
    st.header("⚙️ 設定 (Gemini)")
    api_key = st.text_input("請輸入 Google AI Studio API Key", type="password", help="需要 Gemini 1.5 Pro 權限")
    
    st.info("💡 提示：您可以前往 Google AI Studio 免費獲取 API Key。")
    
    if not api_key:
        st.warning("請先輸入 API Key 以開始使用。")
    else:
        st.success("API Key 已就緒")

    st.markdown("---")
    st.markdown("""
    **模型說明：**
    本應用程式使用 **Gemini 1.5 Pro**。
    該模型具有極強的長上下文窗口和視覺識別能力，非常適合處理複雜的報紙版面。
    """)

# 主介面
st.title("📰 日文報紙結構化工具 (Powered by Gemini)")
st.markdown("上傳圖片 -> Gemini 視覺分析 -> 翻譯繁體中文 -> 生成 JSON")

# 核心處理函數
def process_with_gemini(api_key, image_input):
    # 配置 API
    genai.configure(api_key=api_key)
    
    # 使用最新的 Gemini 1.5 Pro 模型
    model = genai.GenerativeModel('gemini-3-pro-preview')

    # 定義 Prompt
    prompt = """
    您是一位專業的日文報紙翻譯和結構化專家。您的任務是接收一張日本報紙的圖片，執行 OCR，然後將直式日文文本精確翻譯成繁體中文，並按照指定的 JSON 格式進行結構化輸出。

    **處理要求 (必須嚴格遵循)：**
    1. **直式文本提取 (Layout Analysis):** 識別報紙的版面結構（從上到下，從右到左），將文本分割成邏輯區塊。
    2. **核心資訊提取：** 提取日期 (Date)、標題 (Headline) 和內文 (Body Text)。
    3. **圖片識別：** 描述每個區塊關聯的圖片內容 (用繁體中文)。
    4. **翻譯：** 將日文標題和內文翻譯成高品質的**繁體中文**。
    5. **輸出格式：** 必須直接輸出標準的 JSON 格式，不要包含 Markdown 標記（如 ```json ... ```），也不要包含任何其他解釋性文字。

    **JSON 結構模板：**
    {
      "date": "YYYY年MM月DD日 (如果找不到則填 '未知')",
      "sections": [
        {
          "section_id": 1,
          "headline_jp": "日文標題",
          "headline_zh": "中文標題",
          "body_text_jp": "日文內文",
          "body_text_zh": "中文內文",
          "image_description": "圖片描述(中文)"
        }
      ]
    }
    """

    try:
        # 發送請求：Gemini 支援直接傳入 PIL Image 物件
        # 强制要求 JSON 響應 (JSON Mode)
        response = model.generate_content(
            [prompt, image_input],
            generation_config={"response_mime_type": "application/json"}
        )
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# 上傳元件
uploaded_file = st.file_uploader("請拖入或選擇報紙圖片 (JPG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # 將上傳的檔案轉換為 PIL Image 物件，以便展示和傳給 Gemini
    image = Image.open(uploaded_file)
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.image(image, caption="原始報紙圖片", use_container_width=True)
    
    with col2:
        st.info("圖片已載入 (Gemini 模式)")
        if st.button("🚀 開始 Gemini 識別", type="primary"):
            if not api_key:
                st.error("請在左側側邊欄輸入 Google API Key！")
            else:
                with st.spinner("Gemini 1.5 Pro 正在閱讀報紙中... (速度通常很快)"):
                    # 呼叫 AI
                    result_text = process_with_gemini(api_key, image)
                    
                    try:
                        # Gemini 在 JSON 模式下通常返回非常乾淨的 JSON
                        data = json.loads(result_text)
                        
                        st.success("處理完成！")
                        
                        # 選項卡顯示結果
                        tab1, tab2 = st.tabs(["📄 視覺化閱讀", "💾 原始 JSON"])
                        
                        with tab1:
                            st.subheader(f"📅 提取日期：{data.get('date', '未知')}")
                            for section in data.get("sections", []):
                                with st.container(border=True):
                                    st.markdown(f"### 🔹 {section.get('headline_zh')}")
                                    st.caption(f"原文：{section.get('headline_jp')}")
                                    
                                    c1, c2 = st.columns(2)
                                    with c1:
                                        st.markdown("**[中文譯文]**")
                                        st.write(section.get('body_text_zh'))
                                    with c2:
                                        st.markdown("**[日文原文]**")
                                        st.markdown(f"*{section.get('body_text_jp')}*")
                                    
                                    if section.get('image_description'):
                                        st.info(f"🖼️ 圖片描述：{section.get('image_description')}")
                        
                        with tab2:
                            st.json(data)
                            # 下載按鈕
                            json_str = json.dumps(data, indent=2, ensure_ascii=False)
                            st.download_button(
                                label="📥 下載 JSON 檔案",
                                data=json_str,
                                file_name="gemini_result.json",
                                mime="application/json"
                            )

                    except json.JSONDecodeError:
                        st.error("解析失敗。以下是 Gemini 返回的原始內容（可能未完全遵循 JSON 格式）：")
                        st.text(result_text)
                    except Exception as e:
                        st.error(f"發生系統錯誤: {e}")
