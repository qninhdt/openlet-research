"""
Phase 1: Clean Image Generation using Pyppeteer
Generates clean images from text with random styling and auto-fitting logic.
"""

import json
import random
import asyncio
import nest_asyncio
import argparse
from pathlib import Path
import numpy as np
import cv2
from pyppeteer import launch
from tqdm import tqdm

# Allow nested event loops for Jupyter/Colab environments
nest_asyncio.apply()


class CleanImageGenerator:
    """
    Phase 1: Converts text into clean images with random attributes.
    Features:
    - Random page size per sample.
    - Auto-fit text to single page (prevents overflow).
    - Random fonts, colors, and layouts.
    """

    # Common dimensions (Width, Height)
    COMMON_SIZES = {
        "a4": (794, 1123),  # A4 at 96 DPI
        "a5": (559, 794),  # A5 at 96 DPI
        "letter": (816, 1056),  # US Letter
        "screen_hd": (1280, 720),
        "screen_fhd": (1920, 1080),
        "facebook_post": (1200, 630),
        "twitter_post": (1200, 675),
        "book_page": (600, 900),
        "newspaper": (800, 1200),
        "flyer": (816, 1056),
        "poster_small": (1200, 1800),
    }

    # 1. Định nghĩa Map: Tên Font -> Link Google Fonts
    GOOGLE_FONTS_MAP = {
        # --- Chữ in (Standard) ---
        "Roboto": "https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap",
        "Open Sans": "https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap",
        "Lora": "https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&display=swap",
        "Merriweather": "https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700&display=swap",
        # --- Chữ viết tay (Handwriting) - Hỗ trợ Tiếng Việt ---
        "Dancing Script": "https://fonts.googleapis.com/css2?family=Dancing+Script:wght@400;600;700&display=swap",
        "Pacifico": "https://fonts.googleapis.com/css2?family=Pacifico&display=swap",
        "Caveat": "https://fonts.googleapis.com/css2?family=Caveat:wght@400;600;700&display=swap",
        "Patrick Hand": "https://fonts.googleapis.com/css2?family=Patrick+Hand&display=swap",
        "Pangolin": "https://fonts.googleapis.com/css2?family=Pangolin&display=swap",
        "Charm": "https://fonts.googleapis.com/css2?family=Charm:wght@400;700&display=swap",
        "Mali": "https://fonts.googleapis.com/css2?family=Mali:wght@400;600;700&display=swap",
        "Itim": "https://fonts.googleapis.com/css2?family=Itim&display=swap",
    }

    # Tách danh sách tên để random
    ALL_FONTS = list(GOOGLE_FONTS_MAP.keys())
    HANDWRITING_FONTS = [
        "Dancing Script",
        "Pacifico",
        "Caveat",
        "Patrick Hand",
        "Pangolin",
        "Charm",
        "Mali",
        "Itim",
    ]

    BACKGROUND_COLORS = [
        "#FFFFFF",
        "#FFFEF7",
        "#FFFFF0",
        "#FEFEFE",
        "#F9F9F9",
        "#F5F5F5",
        "#FFF8DC",
        "#FFFACD",
        "#FFF5EE",
        "#FAF0E6",
        "#FAEBD7",
        "#FFE4E1",
        "#F0F8FF",
        "#F5FFFA",
        "#FFFFF0",
        "#FFFAFA",
        "#F8F8FF",
        "#FDF5E6",
        "#FFFAF0",
    ]

    TEXT_COLORS = [
        "#000000",
        "#1A1A1A",
        "#2C2C2C",
        "#333333",
        "#404040",
        "#1C1C1C",
        "#0A0A0A",
        "#111111",
        "#0D0D0D",
        "#262626",
        "#292929",
        "#1F1F1F",
        "#141414",
        "#3D3D3D",
    ]

    def __init__(self):
        # We do not set fixed width/height here anymore.
        # Sizes are determined per sample.
        self.output_dir = None

    def _get_random_size(self):
        """Pick a random size from COMMON_SIZES"""
        size_name = random.choice(list(self.COMMON_SIZES.keys()))
        return self.COMMON_SIZES[size_name]

    def _calculate_optimal_settings(self, text_length, width, height):
        """
        Calculate layout settings based on text density and image area.
        """
        image_area = width * height
        text_density = text_length / image_area

        # Dynamic settings based on density
        if text_density < 0.05:
            base_font = max(14, int(width / 50))
            return {
                "font_size_range": (base_font, base_font + 4),
                "num_columns_choices": [1, 1, 1, 2],
                "padding_range": (0.05, 0.15),
                "line_height_range": (1.5, 1.8),
                "paragraph_spacing_range": (15, 25),
            }
        elif text_density < 0.15:
            base_font = max(12, int(width / 60))
            return {
                "font_size_range": (base_font, base_font + 4),
                "num_columns_choices": [1, 1, 2, 2],
                "padding_range": (0.03, 0.1),
                "line_height_range": (1.4, 1.7),
                "paragraph_spacing_range": (12, 18),
            }
        elif text_density < 0.3:
            base_font = max(10, int(width / 70))
            return {
                "font_size_range": (base_font, base_font + 3),
                "num_columns_choices": [1, 2, 2, 2],
                "padding_range": (0.02, 0.07),
                "line_height_range": (1.3, 1.6),
                "paragraph_spacing_range": (10, 15),
            }
        elif text_density < 0.5:
            base_font = max(9, int(width / 80))
            return {
                "font_size_range": (base_font, base_font + 2),
                "num_columns_choices": [2, 2, 3, 3],
                "padding_range": (0.015, 0.05),
                "line_height_range": (1.2, 1.5),
                "paragraph_spacing_range": (8, 12),
            }
        else:
            base_font = max(8, int(width / 90))
            return {
                "font_size_range": (base_font, base_font + 2),
                "num_columns_choices": [2, 3, 3, 3],
                "padding_range": (0.01, 0.03),
                "line_height_range": (1.15, 1.4),
                "paragraph_spacing_range": (6, 10),
            }

    def generate_html_content(self, text):
        """
        Generates HTML content with JS auto-fit logic.
        Returns: (html_string, width, height)
        """
        # 1. Select Random Size
        width, height = self._get_random_size()

        text_length = len(text)
        settings = self._calculate_optimal_settings(text_length, width, height)

        # 2. Random Font Selection
        font_name = random.choice(self.ALL_FONTS)
        font_url = self.GOOGLE_FONTS_MAP[font_name]

        # Lấy base font size từ settings
        base_font_size = random.randint(*settings["font_size_range"])

        # TWEAK: Nếu là font viết tay, tăng size lên 1.3 lần cho dễ đọc
        # (Font viết tay 12px thường trông bé hơn Arial 12px rất nhiều)
        if font_name in self.HANDWRITING_FONTS:
            font_size = int(base_font_size * 1.3)
            # Giảm bớt weight đậm cho font viết tay để đỡ bị bết
            font_weight = random.choice([400, 500])
        else:
            font_size = base_font_size
            font_weight = random.choice([300, 400, 500, 600, 700])

        # Các thông số khác giữ nguyên
        num_columns = random.choice(settings["num_columns_choices"])
        bg_color = random.choice(self.BACKGROUND_COLORS)
        text_color = random.choice(self.TEXT_COLORS)

        # Calculate padding pixels based on percentage range
        pad_min, pad_max = settings["padding_range"]
        padding_horizontal = int(width * random.uniform(pad_min, pad_max))
        padding_bottom = random.randint(20, 60)  # Reserve space at bottom
        y_offset_percent = random.randint(0, 25)  # Random top margin start

        column_gap = random.randint(20, int(width * 0.05)) if num_columns > 1 else 0

        # Font style (italic) thường có sẵn trong font viết tay nên hạn chế force italic bằng CSS
        font_style = "normal"
        if font_name not in self.HANDWRITING_FONTS and random.random() < 0.2:
            font_style = "italic"

        line_height = round(random.uniform(*settings["line_height_range"]), 2)
        paragraph_spacing = random.randint(*settings["paragraph_spacing_range"])

        formatted_text = self._format_text(text, paragraph_spacing)

        # 3. CSS Construction
        css = f"""
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            width: {width}px; height: {height}px;
            background-color: {bg_color};
            padding: 0 {padding_horizontal}px;
            
            /* SỬ DỤNG FONT NAME TỪ GOOGLE FONTS */
            font-family: '{font_name}', cursive, sans-serif;
            
            font-size: {font_size}px; font-weight: {font_weight}; font-style: {font_style};
            color: {text_color}; line-height: {line_height};
            overflow: hidden; position: relative;
        }}
        .content {{
            column-count: {num_columns}; column-gap: {column_gap}px;
            column-fill: balance;
            text-align: justify; hyphens: auto;
            position: absolute;
            width: calc(100% - {padding_horizontal * 2}px);
            left: {padding_horizontal}px;
            height: auto;
            overflow-wrap: break-word; word-wrap: break-word; word-break: break-word;
        }}
        p {{ margin-bottom: {paragraph_spacing}px; break-inside: avoid; }}
        """

        # 4. JavaScript Auto-Fit Logic
        javascript = f"""
        async function fitTextAndPosition() {{
            const content = document.querySelector('.content');
            const body = document.body;
            const pageHeight = {height};
            const pageWidth = {width};
            const paddingBottom = {padding_bottom};
            const paddingHorizontal = {padding_horizontal};
            const yOffsetPercent = {y_offset_percent};
            const maxContentHeight = pageHeight - paddingBottom;
            const maxContentWidth = pageWidth - (paddingHorizontal * 2);

            let currentFontSize = parseFloat(window.getComputedStyle(body).fontSize);
            const minFontSize = 8; // Tăng min size lên một chút cho font viết tay

            while (
                (content.scrollHeight > maxContentHeight || 
                 content.scrollWidth > maxContentWidth + 5) && 
                currentFontSize > minFontSize
            ) {{
                currentFontSize -= 0.5;
                body.style.fontSize = currentFontSize + 'px';
                content.style.display = 'none';
                content.offsetHeight; 
                content.style.display = 'block';
            }}

            const finalContentHeight = content.getBoundingClientRect().height;
            const availableSpace = pageHeight - finalContentHeight - paddingBottom;
            if (availableSpace > 0) {{
                const desiredTop = (pageHeight * yOffsetPercent) / 100;
                const finalTop = Math.min(desiredTop, availableSpace);
                content.style.top = Math.max(20, finalTop) + 'px';
            }} else {{
                content.style.top = '20px';
            }}
            document.body.classList.add('render-done');
        }}
        if (document.readyState === 'loading') {{ document.addEventListener('DOMContentLoaded', fitTextAndPosition); }}
        else {{ fitTextAndPosition(); }}
        """

        # 5. Inject Google Font Link vào thẻ <head>
        html = f"""<!DOCTYPE html>
        <html lang="vi">
        <head>
            <meta charset="UTF-8">
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="{font_url}" rel="stylesheet">
            <style>{css}</style>
        </head>
        <body><div class="content">{formatted_text}</div><script>{javascript}</script></body>
        </html>"""

        return html, width, height

    def _format_text(self, text, paragraph_spacing):
        paragraphs = text.strip().split("\n\n")
        if len(paragraphs) == 1:
            paragraphs = text.strip().split("\n")
        formatted = []
        for para in paragraphs:
            para = para.strip()
            if para:
                # Replace newlines within paragraph with spaces
                cleaned_para = para.replace("\n", " ")
                formatted.append(f"<p>{cleaned_para}</p>")
        return "\n".join(formatted)

    async def _render_clean_image(self, page, html_content, output_path, width, height):
        """
        Renders the HTML to an image using Pyppeteer.
        Waits for the JS 'render-done' class.
        """
        await page.setViewport({"width": width, "height": height})
        await page.setContent(html_content)

        try:
            # Wait for JS auto-fit to complete
            await page.waitForSelector("body.render-done", {"timeout": 10000})
        except Exception as e:
            print(f"⚠️ Timeout waiting for auto-fit logic on {output_path.name}: {e}")

        # Screenshot (fullPage=False ensures we crop to viewport)
        image_bytes = await page.screenshot(fullPage=False)

        # Decode and Save
        nparr = np.frombuffer(image_bytes, np.uint8)
        clean_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        cv2.imwrite(str(output_path), clean_image)

    async def _generate_batch_task(self, items, output_dir):
        """
        Batched generation logic.
        """
        browser = None
        output_paths = []

        try:
            browser = await launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                ],
            )

            # Limit concurrency to avoid memory issues
            sem = asyncio.Semaphore(5)
            pbar = tqdm(total=len(items), desc="🎨 Generating clean images", unit="img")

            async def process_one(item, path):
                async with sem:
                    page = await browser.newPage()
                    try:
                        # 1. Generate HTML with random size
                        html, w, h = self.generate_html_content(item["content"])
                        # 2. Render
                        await self._render_clean_image(page, html, path, w, h)
                        pbar.update(1)
                    except Exception as e:
                        print(f"\n❌ Failed {path.name}: {e}")
                    finally:
                        await page.close()

            tasks = []
            for item in items:
                filename = f"{item['id']:04d}.png"
                output_path = output_dir / filename
                output_paths.append(str(output_path))
                tasks.append(process_one(item, output_path))

            await asyncio.gather(*tasks)
            pbar.close()

        except Exception as e:
            print(f"❌ Critical Error in batch: {e}")
        finally:
            if browser:
                await browser.close()

        return output_paths

    def generate_from_json(
        self,
        json_path="datasets/unified/data.json",
        output_dir="outputs",
        sources=None,
    ):
        """
        Entry point to generate images from a JSON file.

        Args:
            json_path: Path to the JSON file containing the data
            output_dir: Base directory to save generated images (will create outputs/{source}/images/clean/)
            sources: List of dataset sources to include (e.g., ['race', 'dream', 'logiqa'])
                    If None, all datasets will be processed
        """
        json_file = Path(json_path)
        if not json_file.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")

        print(f"📂 Loading data from: {json_path}")
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Filter by sources if specified
        if sources is not None:
            original_count = len(data)
            data = [item for item in data if item.get("source") in sources]
            print(
                f"📊 Filtered by sources {sources}: {len(data)}/{original_count} items"
            )
        else:
            print(f"📊 Total items to process: {len(data)}")

        if len(data) == 0:
            print("⚠️ No items to process after filtering!")
            return []

        # Group data by source
        data_by_source = {}
        for item in data:
            source = item.get("source", "unknown")
            if source not in data_by_source:
                data_by_source[source] = []
            data_by_source[source].append(item)

        all_output_paths = []
        base_output_dir = Path(output_dir)

        # Process each source separately
        for source, items in data_by_source.items():
            source_output_dir = base_output_dir / source / "images" / "clean"
            source_output_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n📦 Processing {source}: {len(items)} items")
            print(f"📁 Output: {source_output_dir}")

            # Run async task for this source
            output_paths = asyncio.run(
                self._generate_batch_task(items, source_output_dir)
            )
            all_output_paths.extend(output_paths)

        return all_output_paths


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate clean images from unified dataset JSON"
    )
    parser.add_argument(
        "--json-path",
        type=str,
        default="datasets/unified/data.json",
        help="Path to the JSON file containing the data (default: datasets/unified/data.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Base directory to save generated images (default: outputs). Images will be saved to outputs/{source}/images/clean/",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="List of dataset sources to include (e.g., race dream logiqa reclor). If not specified, all datasets will be processed.",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("PHASE 1: CLEAN IMAGE GENERATION (RANDOM SIZES & AUTO-FIT)")
    print("=" * 70)

    # Initialize without size (size is random per sample)
    generator = CleanImageGenerator()

    # Run generation
    try:
        paths = generator.generate_from_json(
            json_path=args.json_path,
            output_dir=args.output_dir,
            sources=args.sources,
        )
        print("\n" + "=" * 70)
        print(f"✅ Phase 1 completed. Generated {len(paths)} clean images.")
        print(f"📁 Saved to: {args.output_dir}")
        print("=" * 70)
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
