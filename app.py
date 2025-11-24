import streamlit as st
import json
import google.generativeai as genai
from PIL import Image
import plotly.graph_objects as go
import io

# 頁面設定
st.set_page_config(
    page_title="日文報紙 AI 批次處理助手",
    page_icon="📰",
    layout="wide"
)

# 自定義 CSS
st.markdown("""
<style>
    .stTextArea textarea {font-size: 16px !important;}
    div[data-testid="stExpander"] details summary p {font-size: 1.1rem; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# 側邊欄：設定
with st.sidebar:
    st.header("⚙️ 設定 (Gemini)")
    api_key = st.text_input("請輸入 Google AI Studio API Key", type="password")
    
    if not api_key:
        st.warning("請輸入 API Key。")
    else:
        st.success("API Key 已就緒")

    st.markdown("---")
    st.markdown("""
    **功能說明：**
    1. **純淨圖片裁切**：AI 會精準框選圖片範圍，排除旁邊的附註文字。
    2. **依標題分段**：文章自動分塊。
    3. **互動視覺化**：懸浮查看資訊。
    """)

st.title("📰 日文報紙結構化工具 (純淨圖片版)")
st.markdown("上傳圖片 -> AI 批次分析 -> **純圖片提取** & **文章精準翻譯**")

# 輔助函數：建立互動式 Plotly 圖表
def create_interactive_plot(pil_image, sections):
    img_width, img_height = pil_image.size
    
    fig = go.Figure()

    # 1. 添加底圖
    fig.add_trace(go.Image(z=pil_image))

    # 2. 繪製區塊框線和懸浮點
    for section in sections:
        box = section.get("box_2d") 
        if not box:
            continue

        ymin, xmin, ymax, xmax = box
        
        # 轉換座標
        x0 = (xmin / 1000) * img_width
        y0 = (ymin / 1000) * img_height
        x1 = (xmax / 1000) * img_width
        y1 = (ymax / 1000) * img_height
        
        is_image = section.get("type") == "image"
        # 圖片用紅色框，文字用藍色框
        color = "rgba(255, 50, 50, 0.2)" if is_image else "rgba(50, 100, 255, 0.2)"
        border_color = "red" if is_image else "blue"
        
        hover_text = section.get("body_text_zh") if is_image else section.get("headline_zh")
        if not hover_text:
            hover_text = "(無文字內容)"

        # 繪製矩形
        fig.add_shape(
            type="rect",
            x0=x0, y0=y0, x1=x1, y1=y1,
            line=dict(color=border_color, width=2),
            fillcolor=color,
        )

        # 繪製透明懸浮點
        fig.add_trace(go.Scatter(
            x=[(x0 + x1) / 2],
            y=[(y0 + y1) / 2],
            text=[f"<b>{hover_text}</b>"],
            mode="markers",
            marker=dict(opacity=0, size=0.1),
            hoverinfo="text",
            showlegend=False
        ))

    fig.update_layout(
        width=800,
        height=800 * (img_height / img_width),
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, range=[0, img_width]),
        yaxis=dict(visible=False, range=[img_height, 0], scaleanchor="x"),
    )
    
    return fig

# 輔助函數：裁切圖片
def crop_image_section(pil_image, box_2d):
    if not box_2d: return None
    width, height = pil_image.size
    ymin, xmin, ymax, xmax = box_2d
    left = (xmin / 1000) * width
    top = (ymin / 1000) * height
    right = (xmax / 1000) * width
    bottom = (ymax / 1000) * height
    return pil_image.crop((left, top, right, bottom))

# 核心處理函數
def process_with_gemini(api_key, image_input):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-pro')

    # ---------------------------------------------------------
    # Prompt 修改重點：
    # 要求 box_2d 嚴格排除文字，只包含圖像
    # ---------------------------------------------------------
    prompt = """
    你是一位專業的日文報紙結構化專家。
    請分析這張報紙圖片，識別其中的「文章區塊」和「圖片區塊」。
    
    **處理規則 (嚴格執行)：**

    1. **文章區塊 (Type: "text")**:
       - **分段依據**：請依照報紙的「標題 (Headline/見出し)」來劃分區塊。
       - **內容提取**：提取日文標題與內文，並翻譯成流暢的**繁體中文**。
       - **座標**：包含標題和內文的範圍。
    
    2. **圖片區塊 (Type: "image")**:
       - **重要：座標範圍 (box_2d)**：**請嚴格只標示「照片/插圖圖像本身」的邊界**。絕對**不要**將下方的說明文字（Caption）包含在座標框內。我要乾淨的圖片裁切。
       - **文字識別**：雖然座標框不包含文字，但請你視覺上讀取該圖片緊鄰的說明文字。
       - **翻譯**：將讀取到的說明文字翻譯成繁體中文。若無文字則留空。絕對不要自行看圖說故事。

    3. **輸出格式 (JSON Only)**：
       - 請回傳標準 JSON。
       - 座標格式 [ymin, xmin, ymax, xmax] (0-1000 比例)。

    **JSON 範本**：
    {
      "date": "YYYY年MM月DD日",
      "sections": [
        {
          "type": "text", 
          "box_2d": [ymin, xmin, ymax, xmax], 
          "headline_jp": "...",
          "headline_zh": "...",
          "body_text_jp": "...",
          "body_text_zh": "..."
        },
        {
          "type": "image",
          "box_2d": [ymin, xmin, ymax, xmax], // 必須只包住圖片，不包住文字
          "headline_jp": "", 
          "headline_zh": "",
          "body_text_jp": "圖片旁的日文說明文",
          "body_text_zh": "說明文的繁中翻譯"
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

# --------------------------
# 主程式邏輯
# --------------------------

uploaded_files = st.file_uploader("請拖入或選擇報紙圖片 (支援批次)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)

if uploaded_files and api_key:
    if st.button(f"🚀 開始批次處理 ({len(uploaded_files)} 張)", type="primary"):
        
        progress_bar = st.progress(0)
        
        for idx, uploaded_file in enumerate(uploaded_files):
            st.divider()
            st.header(f"📄 檔案：{uploaded_file.name}")
            
            image = Image.open(uploaded_file)
            
            with st.spinner(f"正在分析第 {idx+1} 張圖片..."):
                result_text = process_with_gemini(api_key, image)
                
                try:
                    data = json.loads(result_text)
                    
                    # 1. 互動式可視化
                    st.subheader("1. 版面互動預覽 (紅色為純圖片範圍)")
                    sections = data.get("sections", [])
                    fig = create_interactive_plot(image, sections)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 2. 純圖片提取
                    st.subheader("2. 圖片提取 (僅顯示純圖與附註翻譯)")
                    image_sections = [s for s in sections if s.get("type") == "image"]
                    
                    if image_sections:
                        cols = st.columns(3)
                        for i, sec in enumerate(image_sections):
                            cropped_img = crop_image_section(image, sec.get("box_2d"))
                            caption_zh = sec.get('body_text_zh')
                            
                            with cols[i % 3]:
                                if cropped_img:
                                    st.image(cropped_img, use_container_width=True)
                                    
                                    # 這裡顯示翻譯好的附註，但圖片本身不含文字
                                    if caption_zh and caption_zh.strip():
                                        st.caption(f"📝 {caption_zh}")
                                    else:
                                        st.caption("(無附註文字)")
                    else:
                        st.info("未偵測到圖片。")

                    # 3. 文章內容
                    st.subheader("3. 文章內容翻譯")
                    st.info(f"📅 發行日期：{data.get('date', '未知')}")
                    
                    text_sections = [s for s in sections if s.get("type") == "text"]
                    
                    for sec in text_sections:
                        with st.expander(f"📰 {sec.get('headline_zh', '無標題')}", expanded=True):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown("**[繁中譯文]**")
                                st.write(sec.get('body_text_zh'))
                            with c2:
                                st.markdown("**[日文原文]**")
                                st.markdown(f"*{sec.get('body_text_jp')}*")
                    
                    # 下載按鈕
                    json_str = json.dumps(data, indent=2, ensure_ascii=False)
                    st.download_button(
                        label=f"📥 下載 {uploaded_file.name} JSON",
                        data=json_str,
                        file_name=f"{uploaded_file.name}_result.json",
                        mime="application/json",
                        key=f"dl_{idx}"
                    )

                except json.JSONDecodeError:
                    st.error("解析失敗，AI 回傳格式有誤。")
                except Exception as e:
                    st.error(f"發生錯誤: {e}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        st.success("✅ 所有圖片處理完成！")
