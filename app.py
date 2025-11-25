import streamlit as st
import json
import io
import zipfile
import time
from PIL import Image
import google.generativeai as genai

# ---------------------------------------------------------
# 頁面基本設定
# ---------------------------------------------------------
st.set_page_config(
    page_title="日文報紙結構化分析助手",
    page_icon="📰",
    layout="wide"
)

st.title("📰 日文報紙結構化分析助手")
st.markdown("上傳報紙圖片 -> AI 自動識別版面與分隔線 -> **下載結構化資料夾 (ZIP)**")

# ---------------------------------------------------------
# 核心邏輯函數
# ---------------------------------------------------------

def crop_image_section(pil_image, box_2d):
    """
    根據 AI 回傳的 [ymin, xmin, ymax, xmax] (0-1000) 裁切圖片。
    """
    if not box_2d or len(box_2d) != 4:
        return None
        
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

        # 裁切並返回 PIL Image 物件
        return pil_image.crop((left, top, right, bottom))
    except Exception as e:
        print(f"警告：圖片裁切失敗，錯誤：{e}")
        return None

def process_with_gemini(api_key, image_input):
    """
    呼叫 Gemini API 進行報紙結構化分析。
    """
    try:
        genai.configure(api_key=api_key)
        # 使用 Gemini 1.5 Pro，對於版面分析能力最強
        model = genai.GenerativeModel('gemini-3-pro-preview')
    except Exception as e:
        raise ValueError(f"API 設定失敗: {e}")

    # ---------------------------------------------------------
    # Prompt 定義 (與 Colab 版本一致，包含分隔線與標題處理)
    # ---------------------------------------------------------
    prompt = """
    你是一位專業的日文報紙編輯與翻譯專家。
    請分析這張報紙圖片，根據版面上的「分隔線 (Line Separators)」與「空白間距」，將每一則獨立的新聞報導提取出來。

    **處理規則 (請嚴格執行)：**

    1. **新聞區塊識別 (Type: "news")**:
        - **獨立性判斷 (重要)**：請特別注意報紙中的**水平或垂直分隔線**。這些線條明確劃分了不同的新聞報導。
            - 遇到明顯的分隔線時，**必須**將線條兩側的內容視為兩個完全獨立的 `news` 物件，切勿合併。
            - 當出現新的獨立大標題（Visual Headline）時，通常代表新的一篇報導開始。
        - **邊界與合併**：在確認為同一篇報導的範圍內，請將跨欄、跨段落的文字合併。
        - **標題結構**：請精確區分「大標題 (Main Headline)」與「副標題 (Sub Headline)」。
            - **歸屬原則：副標題**只屬於在視覺上緊鄰的**大標題**。如果某個大標題在視覺上沒有緊跟的副標題，請將 `headline_sub_jp` 和 `headline_sub_zh` 留空。**絕對禁止**將其他新聞的標題或副標題填入此欄位。
        - **內容提取**：**內文 (body_text) 僅包含實際報導內容。請確保所有標題（大標題和副標題）的文字內容從內文中徹底排除，以避免重複或內容缺失。** 提取內文並翻譯成通順的**繁體中文**。請自動連接跨行或跨欄的句子。

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

    response = model.generate_content(
        [prompt, image_input],
        generation_config={"response_mime_type": "application/json"}
    )
    return response.text

# ---------------------------------------------------------
# 側邊欄與輸入
# ---------------------------------------------------------

with st.sidebar:
    st.header("⚙️ 設定")
    api_key_input = st.text_input("請輸入 Google AI Studio API Key", type="password")
    st.info("提示：此 Key 僅用於本次會話，不會被儲存。")
    st.markdown("---")
    st.markdown("**功能說明：**")
    st.markdown("- 自動識別報紙分隔線")
    st.markdown("- 大標/副標分離")
    st.markdown("- 自動打包每篇報導為資料夾")
    st.markdown("- **僅儲存圖片區塊的裁切圖**")

uploaded_files = st.file_uploader("請選擇報紙圖片 (可多選)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)

# ---------------------------------------------------------
# 主執行邏輯
# ---------------------------------------------------------

if st.button("🚀 開始分析並生成 ZIP", type="primary"):
    if not api_key_input:
        st.warning("請先輸入 API Key。")
        st.stop()
        
    if not uploaded_files:
        st.warning("請先上傳圖片檔案。")
        st.stop()

    # 建立一個記憶體中的 ZIP 檔案
    zip_buffer = io.BytesIO()
    
    # 用來顯示進度
    progress_bar = st.progress(0)
    status_text = st.empty()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        
        total_files = len(uploaded_files)
        
        for idx, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"正在處理第 {idx+1}/{total_files} 張圖片：{uploaded_file.name} ...")
            
            try:
                # 載入圖片
                image = Image.open(uploaded_file)
                base_filename = os.path.splitext(uploaded_file.name)[0]
                
                # 呼叫 Gemini
                result_text = process_with_gemini(api_key_input, image)
                
                # 解析 JSON
                data = json.loads(result_text)
                sections = data.get("sections", [])
                
                # 1. 寫入總表 JSON
                full_json_path = f"{base_filename}/{base_filename}_full_report.json"
                zf.writestr(full_json_path, json.dumps(data, indent=2, ensure_ascii=False))
                
                # 2. 處理各個區塊
                for i, section in enumerate(sections):
                    section_type = section.get('type', 'unknown')
                    box_2d = section.get('box_2d')
                    
                    # 命名資料夾
                    section_title = ""
                    if section_type == 'news':
                        section_title = section.get('headline_main_zh', '無標題')
                    elif section_type == 'image':
                        caption_snippet = section.get('caption_zh', '無附註')
                        section_title = f"圖片附註_{caption_snippet}"
                    
                    # 清理檔名
                    safe_title = "".join(c for c in section_title if c.isalnum() or c in (' ', '_')).strip()
                    safe_title = safe_title.replace(' ', '_')[:20] if safe_title else section_type
                    section_dir_name = f"{base_filename}/{i+1:02d}_{section_type}_{safe_title}"
                    
                    # -----------------------------------------
                    # 圖片處理邏輯 (僅 type='image' 存圖)
                    # -----------------------------------------
                    if section_type == 'image':
                        cropped_img = crop_image_section(image, box_2d)
                        if cropped_img:
                            # 將圖片轉為 bytes 寫入 zip
                            img_byte_arr = io.BytesIO()
                            cropped_img.save(img_byte_arr, format='JPEG')
                            img_path = f"{section_dir_name}/main_image.jpg"
                            zf.writestr(img_path, img_byte_arr.getvalue())
                            
                            # 更新 JSON 紀錄路徑 (相對路徑)
                            section['saved_image_path'] = "main_image.jpg"
                    else:
                        # 新聞區塊不存圖，確保移除舊欄位
                        if 'saved_image_path' in section:
                            del section['saved_image_path']
                    
                    # 寫入單篇 JSON
                    section_json_path = f"{section_dir_name}/report_data.json"
                    zf.writestr(section_json_path, json.dumps(section, indent=2, ensure_ascii=False))

            except Exception as e:
                st.error(f"處理檔案 {uploaded_file.name} 時發生錯誤: {e}")
            
            # 更新進度條
            progress_bar.progress((idx + 1) / total_files)

    status_text.text("✅ 所有處理完成！準備下載...")
    progress_bar.progress(1.0)
    
    # 讓指針回到開始位置
    zip_buffer.seek(0)
    
    # 生成下載按鈕
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="📥 下載分析結果 (ZIP)",
        data=zip_buffer,
        file_name=f"newspaper_analysis_{timestamp}.zip",
        mime="application/zip",
        type="primary"
    )
    
    st.success("分析完成！請點擊上方按鈕下載結果。")
