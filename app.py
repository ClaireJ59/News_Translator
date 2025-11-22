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
    1. **批次處理**：一次上傳多張報紙。
    2. **互動視覺化**：在原圖上懸浮滑鼠可查看區塊標題。
    3. **圖片提取**：自動識別並裁切報紙中的照片。
    """)

st.title("📰 日文報紙結構化工具 (視覺化互動版)")
st.markdown("上傳圖片 -> AI 批次分析 -> **互動式原圖預覽** & **圖文對照**")

# 輔助函數：建立互動式 Plotly 圖表
def create_interactive_plot(pil_image, sections):
    img_width, img_height = pil_image.size
    
    # 建立基本圖表
    fig = go.Figure()

    # 1. 添加底圖
    fig.add_trace(go.Image(z=pil_image))

    # 2. 繪製區塊框線和懸浮點
    for section in sections:
        box = section.get("box_2d") # [ymin, xmin, ymax, xmax] (0-1000)
        if not box:
            continue

        ymin, xmin, ymax, xmax = box
        
        # 轉換座標為像素 (Gemini 返回的是 0-1000 的比例)
        x0 = (xmin / 1000) * img_width
        y0 = (ymin / 1000) * img_height
        x1 = (xmax / 1000) * img_width
        y1 = (ymax / 1000) * img_height
        
        # 根據類型決定顏色
        is_image = section.get("type") == "image"
        color = "rgba(255, 50, 50, 0.3)" if is_image else "rgba(50, 100, 255, 0.3)" # 紅色是圖，藍色是文
        border_color = "red" if is_image else "blue"
        hover_text = section.get("content_zh") if is_image else section.get("headline_zh")

        # 添加矩形 (Shape) - 用於視覺顯示
        fig.add_shape(
            type="rect",
            x0=x0, y0=y0, x1=x1, y1=y1,
            line=dict(color=border_color, width=2),
            fillcolor=color,
        )

        # 添加透明的散點 (Scatter) - 用於顯示 Hover 資訊
        # Plotly 的 Shape hover 支援較差，用 Scatter 覆蓋在中心是常用技巧
        fig.add_trace(go.Scatter(
            x=[(x0 + x1) / 2],
            y=[(y0 + y1) / 2],
            text=[f"<b>{hover_text}</b><br>(點擊下方詳情查看全文)"],
            mode="markers",
            marker=dict(opacity=0, size=0.1), # 完全透明
            hoverinfo="text",
            showlegend=False
        ))

    # 設定圖表佈局
    fig.update_layout(
        width=800,
        height=800 * (img_height / img_width),
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, range=[0, img_width]),
        # yaxis 必須反轉，因為圖片座標 (0,0) 在左上角，Plotly 默認在左下角
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

    prompt = """
    你是一位專業的日文報紙結構化專家。
    請分析這張報紙圖片，識別其中的「文章區塊」和「圖片區塊」。
    
    **重要要求：**
    1. **座標識別 (Bounding Boxes)**：對於每個區塊，請準確估算出其位置。使用 [ymin, xmin, ymax, xmax] 格式，數值範圍為 0 到 1000 (代表相對位置)。
    2. **分類**：區分該區塊是 "text" (文章) 還是 "image" (新聞照片/插圖)。
    3. **翻譯與提取**：
       - 若是文章：提取日文標題、內文，並翻譯成**繁體中文**。
       - 若是圖片：請簡要描述圖片內容（繁體中文）。
    4. **輸出格式**：必須是純 JSON 格式。

    **JSON 結構範本：**
    {
      "date": "YYYY年MM月DD日",
      "sections": [
        {
          "type": "text",  // 或 "image"
          "box_2d": [ymin, xmin, ymax, xmax], 
          "headline_jp": "日文標題 (圖片則留空)",
          "headline_zh": "繁中標題 (圖片則留空)",
          "body_text_jp": "日文內文",
          "body_text_zh": "繁中內文 (若是圖片，請填寫描述)",
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

# 允許上傳多個檔案
uploaded_files = st.file_uploader("請拖入或選擇報紙圖片 (支援批次)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)

if uploaded_files and api_key:
    if st.button(f"🚀 開始批次處理 ({len(uploaded_files)} 張)", type="primary"):
        
        progress_bar = st.progress(0)
        
        for idx, uploaded_file in enumerate(uploaded_files):
            st.divider()
            st.header(f"📄 檔案：{uploaded_file.name}")
            
            # 讀取圖片
            image = Image.open(uploaded_file)
            
            with st.spinner(f"正在分析第 {idx+1} 張圖片..."):
                result_text = process_with_gemini(api_key, image)
                
                try:
                    data = json.loads(result_text)
                    
                    # -----------------------------
                    # 1. 互動式可視化 (Plotly)
                    # -----------------------------
                    st.subheader("1. 互動式版面分佈 (滑鼠懸停查看標題)")
                    sections = data.get("sections", [])
                    fig = create_interactive_plot(image, sections)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # -----------------------------
                    # 2. 獨立圖片提取 (Gallery)
                    # -----------------------------
                    st.subheader("2. 圖片提取 (Image Extraction)")
                    image_sections = [s for s in sections if s.get("type") == "image"]
                    
                    if image_sections:
                        cols = st.columns(len(image_sections) if len(image_sections) < 4 else 4)
                        for i, sec in enumerate(image_sections):
                            cropped_img = crop_image_section(image, sec.get("box_2d"))
                            with cols[i % 4]:
                                if cropped_img:
                                    st.image(cropped_img, use_container_width=True)
                                    st.caption(f"圖說：{sec.get('body_text_zh')}")
                    else:
                        st.info("本頁未偵測到主要新聞圖片。")

                    # -----------------------------
                    # 3. 詳細圖文對照 (JSON Data)
                    # -----------------------------
                    st.subheader("3. 詳細翻譯內容")
                    st.info(f"📅 提取日期：{data.get('date', '未知')}")
                    
                    # 只顯示文字類型的區塊
                    text_sections = [s for s in sections if s.get("type") == "text"]
                    
                    for sec in text_sections:
                        with st.expander(f"📝 {sec.get('headline_zh', '無標題')}", expanded=False):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown("**[繁中譯文]**")
                                st.write(sec.get('body_text_zh'))
                            with c2:
                                st.markdown("**[日文原文]**")
                                st.caption(sec.get('body_text_jp'))
                    
                    # 下載 JSON
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
                    st.text(result_text)
                except Exception as e:
                    st.error(f"發生錯誤: {e}")
            
            # 更新進度
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        st.success("✅ 所有圖片處理完成！")
