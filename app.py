import streamlit as st
import json
import google.generativeai as genai
from PIL import Image
import io

# 頁面設定
st.set_page_config(
    page_title="日文報紙 AI 切割翻譯助手",
    page_icon="📰",
    layout="wide"
)

# 自定義 CSS 優化排版
st.markdown("""
<style>
    .stTextArea textarea {font-size: 16px !important;}
    div[data-testid="stExpander"] details summary p {font-size: 1.1rem; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# 側邊欄：設定
with st.sidebar:
    st.header("⚙️ 系統設定")
    api_key = st.text_input("請輸入 Google AI Studio API Key", type="password", help="建議使用 Gemini 1.5 Pro 以獲得最佳視覺識別效果")
    
    st.info("💡 提示：此版本支援批次處理與自動切圖。")
    st.markdown("---")
    st.markdown("""
    **功能說明：**
    1. **批次上傳**：一次處理多張報紙。
    2. **自動切圖**：AI 識別區塊座標，將原圖切分。
    3. **圖文對照**：左側顯示切片原圖，右側顯示繁中翻譯。
    4. **圖片提取**：獨立識別報紙中的照片。
    """)

st.title("📰 日文報紙 AI 切割翻譯助手 (繁體中文版)")
st.markdown("上傳報紙 -> AI 識別座標與內容 -> **自動切圖對照閱讀**")

# 輔助函式：裁切圖片
def crop_image(image, box_2d):
    """
    根據 Gemini 返回的 0-1000 比例座標裁切圖片
    box_2d 格式: [ymin, xmin, ymax, xmax]
    """
    try:
        width, height = image.size
        ymin, xmin, ymax, xmax = box_2d
        
        # 轉換為像素座標
        left = (xmin / 1000) * width
        top = (ymin / 1000) * height
        right = (xmax / 1000) * width
        bottom = (ymax / 1000) * height
        
        # 裁切
        cropped_img = image.crop((left, top, right, bottom))
        return cropped_img
    except Exception as e:
        return None

# 核心處理函式
def process_image_with_gemini(api_key, image_input):
    genai.configure(api_key=api_key)
    # 使用 Gemini 1.5 Pro，它的視覺定位能力較強
    model = genai.GenerativeModel('gemini-1.5-pro')

    prompt = """
    你是一位專業的日文報紙結構化專家。
    請分析這張報紙圖片，識別其中的「文章區塊」和「獨立圖片/照片區塊」。
    
    **重要要求：**
    1. **座標識別 (Bounding Boxes)**：對於每個區塊，請準確估算出其在圖片中的位置範圍。使用 [ymin, xmin, ymax, xmax] 格式，數值範圍為 0 到 1000 (代表相對位置)。
    2. **翻譯與提取**：
       - 若是文章：提取日文標題與內文，並翻譯成流暢的「繁體中文」。
       - 若是圖片：請簡要描述圖片內容（繁體中文）。
    3. **輸出格式**：必須是純 JSON 格式。

    **JSON 結構範本：**
    {
      "date": "YYYY年MM月DD日 (若無則填 '未知')",
      "sections": [
        {
          "type": "text",  // 或者是 "image"
          "box_2d": [ymin, xmin, ymax, xmax], // 例如 [100, 100, 500, 900]
          "headline_jp": "日文標題 (如果是圖片則留空)",
          "headline_zh": "繁中標題 (如果是圖片則留空)",
          "content_jp": "日文內文全文",
          "content_zh": "繁中內文全文 (若是圖片，請填寫圖片描述)"
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

# 上傳組件 (允許批次)
uploaded_files = st.file_uploader("請選擇報紙圖片 (支援多選)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)

if uploaded_files and api_key:
    if st.button(f"🚀 開始處理 {len(uploaded_files)} 張圖片", type="primary"):
        
        # 建立進度條
        progress_bar = st.progress(0)
        
        for idx, uploaded_file in enumerate(uploaded_files):
            st.markdown(f"### 📄 正在處理：{uploaded_file.name}")
            
            # 讀取圖片
            image = Image.open(uploaded_file)
            
            with st.spinner(f"AI 正在分析版面佈局與翻譯中... ({idx+1}/{len(uploaded_files)})"):
                json_result = process_image_with_gemini(api_key, image)
            
            try:
                data = json.loads(json_result)
                
                # 顯示整體資訊
                st.info(f"📅 發行日期：{data.get('date', '未知')}")
                
                # 遍歷每個區塊
                sections = data.get("sections", [])
                
                # 使用 Expander 讓介面更整潔
                with st.expander(f"點擊展開 {uploaded_file.name} 的詳細切片結果", expanded=True):
                    
                    for i, section in enumerate(sections):
                        col_img, col_text = st.columns([1, 2])
                        
                        # 處理圖片裁切
                        box = section.get("box_2d")
                        if box:
                            cropped = crop_image(image, box)
                        else:
                            cropped = None
                        
                        # 左欄：顯示切片
                        with col_img:
                            if cropped:
                                st.image(cropped, caption=f"區塊 #{i+1} 原圖切片", use_container_width=True)
                            else:
                                st.warning("無法取得裁切座標")
                                
                        # 右欄：顯示翻譯內容
                        with col_text:
                            sec_type = section.get("type", "text")
                            
                            if sec_type == "image":
                                st.markdown("#### 🖼️ 圖片/照片區塊")
                                st.success(f"**圖片描述：** {section.get('content_zh')}")
                            else:
                                st.markdown(f"#### {section.get('headline_zh', '無標題')}")
                                st.caption(f"原文標題：{section.get('headline_jp')}")
                                
                                tab_zh, tab_jp = st.tabs(["🇹🇼 繁中譯文", "🇯🇵 日文原文"])
                                with tab_zh:
                                    st.write(section.get('content_zh'))
                                with tab_jp:
                                    st.text(section.get('content_jp'))
                        
                        st.divider() # 分隔線
                
                # 下載 JSON
                json_str = json.dumps(data, indent=2, ensure_ascii=False)
                st.download_button(
                    label=f"📥 下載 {uploaded_file.name} 的 JSON",
                    data=json_str,
                    file_name=f"{uploaded_file.name}_result.json",
                    mime="application/json"
                )
                
            except json.JSONDecodeError:
                st.error(f"檔案 {uploaded_file.name} 解析失敗。AI 回傳了非標準 JSON。")
                with st.expander("查看原始錯誤內容"):
                    st.text(json_result)
            except Exception as e:
                st.error(f"處理檔案 {uploaded_file.name} 時發生未知錯誤: {e}")

            # 更新進度條
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        st.success("🎉 所有圖片處理完成！")
