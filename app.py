import streamlit as st
import json
import google.generativeai as genai
from PIL import Image
import io

# ---------------------------------------------------------
# 頁面基本設定
# ---------------------------------------------------------
st.set_page_config(
    page_title="日文報紙新聞分塊助手",
    page_icon="📰",
    layout="wide"
)

# CSS 優化：讓文字顯示更清晰，並增加區塊邊框感
st.markdown("""
<style>
    .news-card {
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        background-color: #f9f9f9;
        margin-bottom: 20px;
    }
    .main-title {
        color: #2c3e50;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        margin-bottom: 5px !important;
    }
    .sub-title {
        color: #555;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        margin-bottom: 15px !important;
    }
    .caption-text {
        font-size: 0.9rem;
        color: #666;
        font-style: italic;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 側邊欄設定
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 系統設定")
    api_key = st.text_input("請輸入 Google AI Studio API Key", type="password")
    
    if not api_key:
        st.warning("請輸入 API Key。")
    else:
        st.success("API Key 已就緒")

    st.markdown("---")
    st.markdown("""
    **功能說明：**
    1. **線段識別**：依據報紙分隔線獨立提取新聞。
    2. **標題結構**：區分大標與副標。
    3. **跨段合併**：自動連接跨欄位的文章內容。
    4. **圖片分離**：乾淨裁切圖片，翻譯附註。
    """)

st.title("📰 日文報紙新聞分塊助手")
st.markdown("上傳圖片 -> AI 依分隔線切分新聞 -> **獨立卡片式閱讀**")

# ---------------------------------------------------------
# 核心邏輯函數
# ---------------------------------------------------------

def crop_image_section(pil_image, box_2d):
    """
    根據 AI 回傳的 [ymin, xmin, ymax, xmax] (0-1000) 裁切圖片
    """
    if not box_2d: return None
    try:
        width, height = pil_image.size
        ymin, xmin, ymax, xmax = box_2d
        
        # 轉換座標
        left = (xmin / 1000) * width
        top = (ymin / 1000) * height
        right = (xmax / 1000) * width
        bottom = (ymax / 1000) * height
        
        # 邊界檢查
        left = max(0, left)
        top = max(0, top)
        right = min(width, right)
        bottom = min(height, bottom)

        if right <= left or bottom <= top:
            return None

        return pil_image.crop((left, top, right, bottom))
    except Exception:
        return None

def process_with_gemini(api_key, image_input):
    genai.configure(api_key=api_key)
    # 使用 Gemini 1.5 Pro，對於版面分析能力最強
    model = genai.GenerativeModel('gemini-3-pro-preview')

    # ---------------------------------------------------------
    # Prompt 重點：
    # 1. 依據線段 (Visual Separators) 分隔新聞。
    # 2. 區分 main_headline, sub_headline。
    # 3. 跨欄合併 (Cross-column merging)。
    # ---------------------------------------------------------
    prompt = """
    你是一位專業的日文報紙編輯與翻譯專家。
    請分析這張報紙圖片，根據版面上的「分隔線 (Line Separators)」與「空白間距」，將每一則獨立的新聞報導提取出來。

    **處理規則 (請嚴格執行)：**

    1. **新聞區塊識別 (Type: "news")**:
       - **邊界判斷**：請仔細觀察報紙上的直線或分隔線，這些通常區隔了不同的新聞。請將同一則新聞的所有內容（包含跨欄、跨段落的文字）合併為一個區塊。
       - **標題結構**：請區分「大標題 (Main Headline)」與「副標題 (Sub Headline)」。若只有一個標題則填入大標題。
       - **內容提取**：提取內文並翻譯成通順的**繁體中文**。請自動連接跨行或跨欄的句子。

    2. **圖片區塊 (Type: "image")**:
       - **純淨裁切**：座標範圍 (box_2d) **必須嚴格只包含圖片畫面本身**，絕對排除旁邊的說明文字 (Caption)。
       - **附註翻譯**：讀取圖片旁邊的說明文字並翻譯。絕對不要自行解釋圖片內容。

    3. **座標識別**:
       - 回傳 [ymin, xmin, ymax, xmax] (0-1000 比例)。

    **輸出格式 (JSON Only)**：
    {
      "date": "YYYY年MM月DD日",
      "sections": [
        {
          "type": "news", 
          "box_2d": [ymin, xmin, ymax, xmax], // 包含該則新聞所有文字的範圍
          "headline_main_jp": "日文大標",
          "headline_main_zh": "繁中大標翻譯",
          "headline_sub_jp": "日文副標 (若無則空)",
          "headline_sub_zh": "繁中副標翻譯 (若無則空)",
          "body_text_jp": "日文內文全文...",
          "body_text_zh": "繁中內文全文..."
        },
        {
          "type": "image",
          "box_2d": [ymin, xmin, ymax, xmax], // 僅圖片本身
          "caption_jp": "識別到的日文附註",
          "caption_zh": "附註翻譯"
        }
      ]
    }
    """

    try:
        response = model.generate_content(
            [prompt, image_input],
            generation_config={"response_mime_type": "application/json"}
        )
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# ---------------------------------------------------------
# 主程式
# ---------------------------------------------------------

uploaded_files = st.file_uploader("請選擇報紙圖片 (支援批次上傳)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)

if uploaded_files and api_key:
    if st.button(f"🚀 開始分析 ({len(uploaded_files)} 張)", type="primary"):
        
        progress_bar = st.progress(0)
        
        for idx, uploaded_file in enumerate(uploaded_files):
            st.divider()
            st.header(f"📰 處理檔案：{uploaded_file.name}")
            
            image = Image.open(uploaded_file)
            
            with st.spinner(f"正在依據版面線段切分新聞... ({idx+1}/{len(uploaded_files)})"):
                result_text = process_with_gemini(api_key, image)
                
                try:
                    data = json.loads(result_text)
                    st.info(f"📅 發行日期：{data.get('date', '未知')}")
                    
                    sections = data.get("sections", [])
                    
                    # 分類區塊
                    news_sections = [s for s in sections if s.get("type") == "news"]
                    image_sections = [s for s in sections if s.get("type") == "image"]

                    # -----------------------------------------
                    # 1. 顯示新聞內容 (逐條列出)
                    # -----------------------------------------
                    st.subheader("📝 獨立新聞報導")
                    
                    if not news_sections:
                        st.warning("未偵測到文字新聞區塊。")
                    
                    for i, news in enumerate(news_sections):
                        # 使用容器將每則新聞包起來
                        with st.container(border=True):
                            col_text, col_origin = st.columns([3, 1])
                            
                            with col_text:
                                # 大標題
                                h_main = news.get('headline_main_zh') or news.get('headline_main_jp') or "無標題"
                                st.markdown(f"<div class='main-title'>{h_main}</div>", unsafe_allow_html=True)
                                
                                # 副標題
                                h_sub = news.get('headline_sub_zh')
                                if h_sub:
                                    st.markdown(f"<div class='sub-title'>└ {h_sub}</div>", unsafe_allow_html=True)
                                
                                # 內文翻譯
                                st.markdown("##### 🇹🇼 內文翻譯")
                                st.write(news.get('body_text_zh'))

                                # 日文原文 (折疊)
                                with st.expander("查看日文原文"):
                                    st.text(news.get('headline_main_jp'))
                                    if news.get('headline_sub_jp'):
                                        st.text(news.get('headline_sub_jp'))
                                    st.markdown("---")
                                    st.text(news.get('body_text_jp'))

                            # 右側顯示該新聞在原圖的位置裁切 (方便對照)
                            with col_origin:
                                crop = crop_image_section(image, news.get("box_2d"))
                                if crop:
                                    st.image(crop, caption="原圖位置", use_container_width=True)
                                else:
                                    st.caption("無法顯示原圖位置")

                    # -----------------------------------------
                    # 2. 顯示圖片與附註 (Gallery 模式)
                    # -----------------------------------------
                    if image_sections:
                        st.subheader("🖼️ 圖片集與附註")
                        img_cols = st.columns(3) # 每行 3 張
                        
                        for i, img_sec in enumerate(image_sections):
                            crop = crop_image_section(image, img_sec.get("box_2d"))
                            caption = img_sec.get("caption_zh")
                            
                            with img_cols[i % 3]:
                                if crop:
                                    st.image(crop, use_container_width=True)
                                else:
                                    st.warning("圖片裁切失敗")
                                
                                if caption:
                                    st.markdown(f"<div class='caption-text'>📝 {caption}</div>", unsafe_allow_html=True)
                                else:
                                    st.caption("(無附註)")
                    
                    # 下載 JSON
                    json_str = json.dumps(data, indent=2, ensure_ascii=False)
                    st.download_button(
                        label=f"📥 下載 JSON",
                        data=json_str,
                        file_name=f"{uploaded_file.name}_parsed.json",
                        mime="application/json",
                        key=f"dl_{idx}"
                    )

                except json.JSONDecodeError:
                    st.error("解析失敗，AI 回傳格式不正確。")
                except Exception as e:
                    st.error(f"發生錯誤: {e}")

            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        st.success("✅ 所有任務完成！")
