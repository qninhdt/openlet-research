"""
Phase 2: Image Augmentation using Augraphy
Load ảnh sạch và áp dụng augmentation
"""

import random
import cv2
import numpy as np
import json
import argparse
from pathlib import Path
from tqdm import tqdm
from augraphy import *


class ImageAugmenter:
    """
    Phase 2: Load ảnh sạch và áp dụng Augraphy augmentation.
    """

    def __init__(
        self,
        input_dir="outputs",
        output_dir="outputs",
    ):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)

        print(f"📂 Base input directory: {self.input_dir}")
        print(f"📁 Base output directory: {self.output_dir}")

    def create_augmentation_pipeline(self):
        """Tạo Augraphy pipeline với các hiệu ứng ngẫu nhiên"""

        pre_phase = []

        ink_phase = [
            InkColorSwap(
                ink_swap_color="random",
                ink_swap_sequence_number_range=(5, 10),
                ink_swap_min_width_range=(2, 3),
                ink_swap_max_width_range=(100, 120),
                ink_swap_min_height_range=(2, 3),
                ink_swap_max_height_range=(100, 120),
                ink_swap_min_area_range=(10, 20),
                ink_swap_max_area_range=(400, 500),
                p=0.2,
            ),
            LinesDegradation(
                line_roi=(0.0, 0.0, 1.0, 1.0),
                line_gradient_range=(32, 255),
                line_gradient_direction=(0, 2),
                line_split_probability=(
                    0.1,
                    0.2,
                ),  # [FIX] Giảm tỉ lệ tách nét để tránh đứt chữ
                line_replacement_value=(250, 255),
                line_min_length=(30, 40),
                line_long_to_short_ratio=(5, 7),
                line_replacement_probability=(0.3, 0.4),  # [FIX] Giảm nhẹ
                line_replacement_thickness=(1, 2),  # [FIX] Giảm độ dày nét xóa
                p=0.2,
            ),
            OneOf(
                [
                    # Dithering(
                    #     dither=random.choice(["ordered", "floyd-steinberg"]),
                    #     order=(3, 5),
                    # ),
                    InkBleed(
                        intensity_range=(0.1, 0.2),
                        kernel_size=(
                            3,
                            3,
                        ),  # [FIX] Kernel lớn (7,7) làm chữ nhòe không đọc được, giữ nhỏ
                        severity=(
                            0.2,
                            0.4,
                        ),  # [FIX] Giảm severity để mực không loang quá mức
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    InkShifter(
                        text_shift_scale_range=(18, 27),
                        text_shift_factor_range=(
                            1,
                            2,
                        ),  # [FIX] Giảm shift factor để chữ không bị méo mó quá
                        text_fade_range=(0, 1),
                        blur_kernel_size=(3, 3),  # [FIX] Giảm blur
                        blur_sigma=0,
                        noise_type="random",
                    ),
                    BleedThrough(
                        intensity_range=(0.1, 0.2),
                        color_range=(
                            200,
                            255,
                        ),  # [FIX] Đảm bảo màu thấm qua giấy là màu sáng (nền), không phải màu tối (mực)
                        ksize=(17, 17),
                        sigmaX=1,
                        alpha=random.uniform(
                            0.05, 0.1
                        ),  # [FIX] Giảm alpha để không lấn át chữ chính
                        offsets=(10, 20),
                    ),
                ],
                p=0.2,
            ),
            # OneOf(
            #     [
            #         Hollow(
            #             hollow_median_kernel_value_range=(71, 101),
            #             hollow_min_width_range=(1, 2),
            #             hollow_max_width_range=(
            #                 5,
            #                 10,
            #             ),  # [FIX] Quan trọng: Giảm max width từ 200 xuống 10. Nếu cao hơn sẽ xóa sạch chữ.
            #             hollow_min_height_range=(1, 2),
            #             hollow_max_height_range=(5, 10),  # [FIX] Tương tự width
            #             hollow_min_area_range=(10, 20),
            #             hollow_max_area_range=(50, 100),  # [FIX] Giảm area
            #             hollow_dilation_kernel_size_range=(1, 1),  # [FIX] Giảm dilation
            #         ),
            #         Letterpress(
            #             n_samples=(100, 200),
            #             n_clusters=(200, 300),
            #             std_range=(500, 1500),
            #             value_range=(150, 200),
            #             value_threshold_range=(96, 128),
            #             blur=0,  # [FIX] Tắt blur thêm
            #         ),
            #     ],
            #     p=0.2,
            # ),
            OneOf(
                [
                    LowInkRandomLines(
                        count_range=(3, 6),  # [FIX] Giảm số lượng đường cắt
                        use_consistent_lines=random.choice([True, False]),
                        noise_probability=0.05,
                    ),
                    LowInkPeriodicLines(
                        count_range=(1, 3),
                        period_range=(16, 32),
                        use_consistent_lines=random.choice([True, False]),
                        noise_probability=0.05,
                    ),
                ],
                p=0.2,
            ),
        ]

        paper_phase = [
            PaperFactory(p=0.2),
            ColorPaper(
                hue_range=(0, 255),
                saturation_range=(
                    10,
                    30,
                ),  # Giữ saturation thấp để background không quá sặc sỡ
                p=0.2,
            ),
            # OneOf(
            #     [
            #         DelaunayTessellation(
            #             n_points_range=(500, 800),
            #             n_horizontal_points_range=(500, 800),
            #             n_vertical_points_range=(500, 800),
            #             noise_type="random",
            #             color_list="default",
            #             color_list_alternate="default",
            #         ),
            #         VoronoiTessellation(
            #             mult_range=(50, 80),
            #             seed=19829813472,
            #             num_cells_range=(500, 1000),
            #             noise_type="random",
            #             background_value=(
            #                 220,
            #                 255,
            #             ),  # [FIX] Đảm bảo nền sáng để tương phản với chữ đen
            #         ),
            #     ],
            #     p=0.2,
            # ),
            WaterMark(
                watermark_word="random",
                watermark_font_size=(10, 15),
                watermark_font_thickness=(20, 25),
                watermark_rotation=(0, 360),
                watermark_location="random",
                watermark_color="random",
                watermark_method="darken",
                p=0.2,
            ),
            OneOf(
                [
                    AugmentationSequence(
                        [
                            NoiseTexturize(
                                sigma_range=(3, 8),
                                turbulence_range=(2, 4),
                                texture_width_range=(300, 500),
                                texture_height_range=(300, 500),
                            ),
                            BrightnessTexturize(
                                texturize_range=(0.9, 0.98),
                                deviation=0.02,
                            ),
                        ],
                    ),
                    AugmentationSequence(
                        [
                            BrightnessTexturize(
                                texturize_range=(0.9, 0.98),
                                deviation=0.02,
                            ),
                            NoiseTexturize(
                                sigma_range=(3, 8),
                                turbulence_range=(2, 4),
                                texture_width_range=(300, 500),
                                texture_height_range=(300, 500),
                            ),
                        ],
                    ),
                ],
                p=0.2,
            ),
        ]

        post_phase = [
            OneOf(
                [
                    GlitchEffect(
                        glitch_direction="random",
                        glitch_number_range=(4, 8),  # [FIX] Giảm số lượng glitch
                        glitch_size_range=(
                            5,
                            15,
                        ),  # [FIX] Giảm kích thước glitch để không cắt đôi dòng chữ
                        glitch_offset_range=(5, 15),  # [FIX] Giảm độ lệch
                    ),
                    ColorShift(
                        color_shift_offset_x_range=(1, 3),  # [FIX] Shift nhỏ thôi
                        color_shift_offset_y_range=(1, 3),
                        color_shift_iterations=(1, 2),
                        color_shift_brightness_range=(0.95, 1.05),
                        color_shift_gaussian_kernel_range=(3, 3),
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    DirtyDrum(
                        line_width_range=(1, 3),  # [FIX] Giảm độ dày vết bẩn
                        line_concentration=random.uniform(0.05, 0.1),
                        direction=random.randint(0, 2),
                        noise_intensity=random.uniform(0.6, 0.8),
                        noise_value=(
                            150,
                            224,
                        ),  # [FIX] Vết bẩn màu sáng hơn chút, đừng quá đen
                        ksize=(3, 3),
                        sigmaX=0,
                        p=0.2,
                    ),
                    DirtyRollers(
                        line_width_range=(
                            2,
                            8,
                        ),  # [FIX] Cực kỳ quan trọng: Giảm từ 32 xuống 8.
                        scanline_type=0,
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    LightingGradient(
                        light_position=None,
                        direction=None,
                        max_brightness=255,
                        min_brightness=96,  # [FIX] Tăng min_brightness để tránh vùng tối đen (pitch black)
                        mode="gaussian",
                        linear_decay_rate=None,
                        transparency=None,
                    ),
                    Brightness(
                        brightness_range=(0.8, 1.2),
                        min_brightness=0,
                        min_brightness_value=(100, 150),
                    ),
                    Gamma(
                        gamma_range=(0.9, 1.1),
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    SubtleNoise(
                        subtle_range=random.randint(5, 10),
                    ),
                    Jpeg(
                        quality_range=(30, 95),
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    Markup(
                        num_lines_range=(2, 5),
                        markup_length_range=(0.3, 0.7),
                        markup_thickness_range=(1, 2),
                        markup_type=random.choice(
                            [
                                "highlight",
                                "underline",
                            ]  # [FIX] Loại bỏ "strikethrough", "crossed"
                        ),
                        markup_color="random",
                        single_word_mode=False,
                        repetitions=1,
                    ),
                    Scribbles(
                        scribbles_type="random",
                        scribbles_location="random",
                        scribbles_size_range=(100, 250),  # [FIX] Giảm size scribble
                        scribbles_count_range=(1, 3),
                        scribbles_thickness_range=(1, 2),
                        scribbles_brightness_change=[32, 64],  # Đừng quá tối
                        scribbles_text="random",
                        scribbles_text_font="random",
                        scribbles_text_rotate_range=(0, 360),
                        scribbles_lines_stroke_count_range=(1, 3),
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    BadPhotoCopy(
                        noise_mask=None,
                        noise_type=-1,
                        noise_side="random",
                        noise_iteration=(1, 2),
                        noise_size=(1, 2),
                        noise_value=(150, 200),  # Noise sáng hơn
                        noise_sparsity=(0.4, 0.6),
                        noise_concentration=(0.1, 0.4),
                        blur_noise=False,  # Tắt blur noise để giữ nét chữ
                        blur_noise_kernel=(3, 3),
                        wave_pattern=random.choice([True, False]),
                        edge_effect=random.choice([True, False]),
                    ),
                    ShadowCast(
                        shadow_side="random",
                        shadow_vertices_range=(1, 10),
                        shadow_width_range=(0.3, 0.6),
                        shadow_height_range=(0.3, 0.6),
                        shadow_color=(0, 0, 0),
                        shadow_opacity_range=(
                            0.2,
                            0.5,
                        ),  # [FIX] Max opacity 0.5. Nếu 0.9 sẽ che hết chữ.
                        shadow_iterations_range=(1, 2),
                        shadow_blur_kernel_range=(101, 301),
                    ),
                    LowLightNoise(
                        num_photons_range=(50, 100),
                        alpha_range=(0.9, 1.0),
                        beta_range=(10, 30),
                        gamma_range=(1, 1.2),  # Gamma ổn định
                        bias_range=(20, 30),
                        dark_current_value=1.0,
                        exposure_time=0.1,  # Giảm exposure time
                        gain=0.1,
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    NoisyLines(
                        noisy_lines_direction="random",
                        noisy_lines_location="random",
                        noisy_lines_number_range=(5, 10),
                        noisy_lines_color=(0, 0, 0),
                        noisy_lines_thickness_range=(1, 1),  # Nét mảnh
                        noisy_lines_random_noise_intensity_range=(0.01, 0.1),
                    ),
                    BindingsAndFasteners(
                        overlay_types="darken",
                        foreground=None,
                        effect_type="random",
                        width_range="random",
                        height_range="random",
                        angle_range=(-10, 10),  # Giảm góc nghiêng
                        ntimes=(2, 4),
                        nscales=(0.9, 1.0),
                        edge="random",
                        edge_offset=(10, 50),
                        use_figshare_library=0,
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    Squish(
                        squish_direction="random",
                        squish_location="random",
                        squish_number_range=(3, 6),
                        squish_distance_range=(3, 5),
                        squish_line="random",
                        squish_line_thickness_range=(1, 1),
                    ),
                    Geometric(
                        scale=(0.9, 1.1),  # Giới hạn scale
                        translation=(-10, 10),
                        fliplr=False,  # [FIX] QUAN TRỌNG: Không lật ngang
                        flipud=False,  # [FIX] QUAN TRỌNG: Không lật dọc
                        crop=(),
                        rotate_range=(-3, 3),  # Rotate nhẹ
                        randomize=0,
                        p=0.2,
                    ),
                ],
                p=0.2,
            ),
            # OneOf(
            #     [
            #         DotMatrix(
            #             dot_matrix_shape="random",
            #             dot_matrix_dot_width_range=(1, 2),  # Dot nhỏ lại
            #             dot_matrix_dot_height_range=(1, 2),
            #             dot_matrix_min_width_range=(1, 2),
            #             dot_matrix_max_width_range=(150, 200),
            #             dot_matrix_gaussian_kernel_value_range=(1, 1),  # Ít blur
            #             dot_matrix_rotate_value_range=(0, 0),  # Tắt rotate dot
            #         ),
            #         Faxify(
            #             scale_range=(0.6, 0.8),
            #             monochrome=0,
            #             monochrome_method="random",
            #             monochrome_arguments={},
            #             halftone=0,
            #             invert=1,
            #             half_kernel_size=(1, 1),
            #             angle=(0, 360),
            #             sigma=(1, 2),
            #         ),
            #     ],
            #     p=0.2,
            # ),
            OneOf(
                [
                    InkMottling(
                        ink_mottling_alpha_range=(0.1, 0.2),  # Nhẹ nhàng
                        ink_mottling_noise_scale_range=(1, 2),
                        ink_mottling_gaussian_kernel_range=(3, 3),
                    ),
                    ReflectedLight(
                        reflected_light_smoothness=0.8,
                        reflected_light_internal_radius_range=(0.0, 0.001),
                        reflected_light_external_radius_range=(0.4, 0.6),
                        reflected_light_minor_major_ratio_range=(0.9, 1.0),
                        reflected_light_color=(255, 255, 255),
                        reflected_light_internal_max_brightness_range=(
                            0.6,
                            0.7,
                        ),  # Đừng quá sáng (cháy sáng)
                        reflected_light_external_max_brightness_range=(0.4, 0.6),
                        reflected_light_location="random",
                        reflected_light_ellipse_angle_range=(0, 360),
                        reflected_light_gaussian_kernel_size_range=(5, 100),
                        p=0.2,
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    PageBorder(
                        page_border_width_height="random",
                        page_border_color=(0, 0, 0),
                        page_border_background_color=(0, 0, 0),
                        page_numbers="random",
                        page_rotation_angle_range=(-1, 1),
                        curve_frequency=(2, 4),
                        curve_height=(1, 2),
                        curve_length_one_side=(50, 100),
                        same_page_border=random.choice([0, 1]),
                    ),
                    BookBinding(
                        shadow_radius_range=(30, 60),
                        curve_range_right=(10, 50),  # Giảm độ cong
                        curve_range_left=(10, 50),
                        curve_ratio_right=(0.05, 0.1),
                        curve_ratio_left=(0.05, 0.1),
                        mirror_range=(1.0, 1.0),
                        binding_align="random",
                        binding_pages=(2, 5),
                        curling_direction=-1,
                        backdrop_color=(0, 0, 0),
                        enable_shadow=1,
                    ),
                    Folding(
                        fold_x=None,
                        fold_deviation=(0, 0),
                        fold_count=random.randint(1, 3),  # [FIX] Giảm số lượng nếp gấp
                        fold_noise=0.0,
                        fold_angle_range=(-5, 5),
                        gradient_width=(0.1, 0.2),
                        gradient_height=(0.01, 0.02),
                        backdrop_color=(0, 0, 0),
                    ),
                ],
                p=0.2,
            ),
        ]

        pipeline = AugraphyPipeline(
            ink_phase=ink_phase,
            paper_phase=paper_phase,
            post_phase=post_phase,
            pre_phase=pre_phase,
            log=False,
        )

        return pipeline

    def augment_single_image(self, input_path, output_path):
        """
        Augment một ảnh đơn lẻ

        Args:
            input_path: Đường dẫn ảnh đầu vào
            output_path: Đường dẫn ảnh đầu ra
        """
        try:
            # Load ảnh
            clean_image = cv2.imread(str(input_path))
            if clean_image is None:
                raise ValueError(f"Cannot load image: {input_path}")

            # Tạo pipeline và augment
            pipeline = self.create_augmentation_pipeline()
            augmented_data = pipeline.augment(clean_image)

            # Lấy kết quả
            if isinstance(augmented_data, dict) and "output" in augmented_data:
                final_image = augmented_data["output"]
            else:
                final_image = augmented_data

            # Lưu file
            cv2.imwrite(str(output_path), final_image)
            return True

        except Exception as e:
            print(f"\n❌ Error augmenting {input_path.name}: {e}")
            return False

    def augment_batch(self, sources=None, input_pattern="*.png"):
        """
        Augment nhiều ảnh tuần tự với progress bar

        Args:
            sources: List of dataset sources to process (e.g., ['race', 'dream', 'logiqa'])
                    If None, all sources will be processed
            input_pattern: Pattern để tìm file (vd: "*.png", "clean_*.png")

        Returns:
            List đường dẫn các ảnh đã augment
        """
        # Find all source directories
        if sources is None:
            # Auto-detect all source directories
            source_dirs = [d for d in self.input_dir.iterdir() if d.is_dir()]
        else:
            source_dirs = [self.input_dir / source for source in sources if (self.input_dir / source).exists()]
        
        if not source_dirs:
            print(f"⚠️  No source directories found")
            return []
        
        all_output_paths = []
        
        for source_dir in source_dirs:
            source_name = source_dir.name
            clean_dir = source_dir / "images" / "clean"
            augmented_dir = source_dir / "images" / "augmented"
            
            if not clean_dir.exists():
                print(f"⚠️  Clean images not found for {source_name}: {clean_dir}")
                continue
            
            # Find all images
            image_files = sorted(list(clean_dir.glob(input_pattern)))
            
            if not image_files:
                print(f"⚠️  No images found for {source_name} matching pattern: {input_pattern}")
                continue
            
            # Create output directory
            augmented_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"\n� Processing {source_name}: {len(image_files)} images")
            print(f"📂 Input: {clean_dir}")
            print(f"📁 Output: {augmented_dir}")
            
            # Process with progress bar
            for img_path in tqdm(image_files, desc=f"🎭 Augmenting {source_name}", unit="img"):
                output_filename = img_path.name
                output_path = augmented_dir / output_filename
                
                success = self.augment_single_image(img_path, output_path)
                if success:
                    all_output_paths.append(str(output_path))
        
        return all_output_paths


# Example usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Augment clean images using Augraphy"
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="outputs",
        help="Base input directory (default: outputs). Will look for outputs/{source}/images/clean/",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Base output directory (default: outputs). Will save to outputs/{source}/images/augmented/",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="List of dataset sources to process (e.g., race dream logiqa reclor). If not specified, all sources will be processed.",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.png",
        help="File pattern to match (default: *.png)",
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("PHASE 2: IMAGE AUGMENTATION")
    print("=" * 70)

    augmenter = ImageAugmenter(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
    )

    # Augment tất cả ảnh clean
    paths = augmenter.augment_batch(sources=args.sources, input_pattern=args.pattern)

    print("\n" + "=" * 70)
    print(f"✅ Phase 2 completed. Augmented {len(paths)} images.")
    print(f"📁 Saved to: {args.output_dir}/{{source}}/images/augmented/")
    print("=" * 70)
