"""
Phase 2: Image Augmentation using Augraphy
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
    Phase 2: Load clean images and apply Augraphy augmentation.
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
        """Create Augraphy pipeline with random effects"""

        pre_phase = []

        ink_phase = [
            OneOf(
                [
                    InkBleed(
                        intensity_range=(0.05, 0.15),
                        kernel_size=(3, 3),
                        severity=(0.1, 0.3),
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    LowInkRandomLines(
                        count_range=(3, 6),
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
            PaperFactory(p=0.1),
            ColorPaper(
                hue_range=(0, 255),
                saturation_range=(
                    10,
                    30,
                ),
                p=0.2,
            ),
            WaterMark(
                watermark_word="random",
                watermark_font_size=(10, 15),
                watermark_font_thickness=(15, 20),
                watermark_rotation=(0, 360),
                watermark_location="random",
                watermark_color="random",
                watermark_method="darken",
                p=0.15,
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
                    ColorShift(
                        color_shift_offset_x_range=(1, 3),
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
                        line_width_range=(1, 2),
                        line_concentration=random.uniform(0.03, 0.06),
                        direction=random.randint(0, 2),
                        noise_intensity=random.uniform(0.4, 0.6),
                        noise_value=(180, 235),
                        ksize=(3, 3),
                        sigmaX=0,
                        p=0.15,
                    ),
                    DirtyRollers(
                        line_width_range=(2, 5),
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
                        min_brightness=140,
                        mode="gaussian",
                        linear_decay_rate=None,
                        transparency=None,
                    ),
                    Brightness(
                        brightness_range=(0.85, 1.15),
                        min_brightness=0,
                        min_brightness_value=(120, 170),
                    ),
                    Gamma(
                        gamma_range=(0.92, 1.08),
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    SubtleNoise(
                        subtle_range=random.randint(3, 7),
                    ),
                    Jpeg(
                        quality_range=(45, 95),
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    Markup(
                        num_lines_range=(1, 3),
                        markup_length_range=(0.2, 0.5),
                        markup_thickness_range=(1, 1),
                        markup_type=random.choice(["highlight", "underline"]),
                        markup_color="random",
                        single_word_mode=False,
                        repetitions=1,
                    ),
                    Scribbles(
                        scribbles_type="random",
                        scribbles_location="random",
                        scribbles_size_range=(50, 150),
                        scribbles_count_range=(1, 2),
                        scribbles_thickness_range=(1, 1),
                        scribbles_brightness_change=[48, 80],
                        scribbles_text="random",
                        scribbles_text_font="random",
                        scribbles_text_rotate_range=(0, 360),
                        scribbles_lines_stroke_count_range=(1, 2),
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
                        noise_iteration=(1, 1),
                        noise_size=(1, 1),
                        noise_value=(180, 220),
                        noise_sparsity=(0.5, 0.7),
                        noise_concentration=(0.05, 0.2),
                        blur_noise=False,
                        blur_noise_kernel=(3, 3),
                        wave_pattern=False,
                        edge_effect=random.choice([True, False]),
                    ),
                    ShadowCast(
                        shadow_side="random",
                        shadow_vertices_range=(1, 6),
                        shadow_width_range=(0.2, 0.4),
                        shadow_height_range=(0.2, 0.4),
                        shadow_color=(0, 0, 0),
                        shadow_opacity_range=(0.1, 0.3),
                        shadow_iterations_range=(1, 1),
                        shadow_blur_kernel_range=(101, 301),
                    ),
                    LowLightNoise(
                        num_photons_range=(80, 150),
                        alpha_range=(0.95, 1.0),
                        beta_range=(5, 15),
                        gamma_range=(1, 1.1),
                        bias_range=(10, 20),
                        dark_current_value=0.5,
                        exposure_time=0.05,
                        gain=0.05,
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
                        noisy_lines_thickness_range=(1, 1),
                        noisy_lines_random_noise_intensity_range=(0.01, 0.1),
                    ),
                    BindingsAndFasteners(
                        overlay_types="darken",
                        foreground=None,
                        effect_type="random",
                        width_range="random",
                        height_range="random",
                        angle_range=(-10, 10),
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
                        squish_number_range=(2, 4),
                        squish_distance_range=(2, 3),
                        squish_line="random",
                        squish_line_thickness_range=(1, 1),
                    ),
                    Geometric(
                        scale=(0.95, 1.05),
                        translation=(-5, 5),
                        fliplr=False,
                        flipud=False,
                        crop=(),
                        rotate_range=(-2, 2),
                        randomize=0,
                        p=0.15,
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    InkMottling(
                        ink_mottling_alpha_range=(0.05, 0.15),
                        ink_mottling_noise_scale_range=(1, 2),
                        ink_mottling_gaussian_kernel_range=(3, 3),
                    ),
                    ReflectedLight(
                        reflected_light_smoothness=0.8,
                        reflected_light_internal_radius_range=(0.0, 0.001),
                        reflected_light_external_radius_range=(0.3, 0.5),
                        reflected_light_minor_major_ratio_range=(0.9, 1.0),
                        reflected_light_color=(255, 255, 255),
                        reflected_light_internal_max_brightness_range=(0.4, 0.55),
                        reflected_light_external_max_brightness_range=(0.3, 0.45),
                        reflected_light_location="random",
                        reflected_light_ellipse_angle_range=(0, 360),
                        reflected_light_gaussian_kernel_size_range=(5, 100),
                        p=0.15,
                    ),
                ],
                p=0.2,
            ),
            OneOf(
                [
                    PageBorder(
                        page_border_width_height="random",
                        page_border_color=(0, 0, 0),
                        page_border_background_color=(200, 200, 200),
                        page_numbers="random",
                        page_rotation_angle_range=(-1, 1),
                        curve_frequency=(2, 3),
                        curve_height=(1, 1),
                        curve_length_one_side=(50, 80),
                        same_page_border=random.choice([0, 1]),
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
        Augment a single image.

        Args:
            input_path: Path to input image
            output_path: Path to output image
        """
        try:
            clean_image = cv2.imread(str(input_path))
            if clean_image is None:
                raise ValueError(f"Cannot load image: {input_path}")

            pipeline = self.create_augmentation_pipeline()
            augmented_data = pipeline.augment(clean_image)

            if isinstance(augmented_data, dict) and "output" in augmented_data:
                final_image = augmented_data["output"]
            else:
                final_image = augmented_data

            cv2.imwrite(str(output_path), final_image)
            return True

        except Exception as e:
            print(f"\n❌ Error augmenting {input_path.name}: {e}")
            return False

    def augment_batch(self, sources=None, input_pattern="*.png"):
        """
        Augment multiple images sequentially with a progress bar.

        Args:
            sources: List of dataset sources to process (e.g., ['race', 'dream', 'logiqa'])
                    If None, all sources will be processed
            input_pattern: File pattern to match (e.g., "*.png", "clean_*.png")

        Returns:
            List of output image paths
        """
        # Find all source directories
        if sources is None:
            source_dirs = [d for d in self.input_dir.iterdir() if d.is_dir()]
        else:
            source_dirs = [
                self.input_dir / source
                for source in sources
                if (self.input_dir / source).exists()
            ]

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

            image_files = sorted(list(clean_dir.glob(input_pattern)))

            if not image_files:
                print(
                    f"⚠️  No images found for {source_name} matching pattern: {input_pattern}"
                )
                continue

            augmented_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n� Processing {source_name}: {len(image_files)} images")
            print(f"📂 Input: {clean_dir}")
            print(f"📁 Output: {augmented_dir}")

            # Process with progress bar
            for img_path in tqdm(
                image_files, desc=f"🎭 Augmenting {source_name}", unit="img"
            ):
                output_filename = img_path.name
                output_path = augmented_dir / output_filename

                success = self.augment_single_image(img_path, output_path)
                if success:
                    all_output_paths.append(str(output_path))

        return all_output_paths


# Example usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Augment clean images using Augraphy")
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

    paths = augmenter.augment_batch(sources=args.sources, input_pattern=args.pattern)

    print("\n" + "=" * 70)
    print(f"✅ Phase 2 completed. Augmented {len(paths)} images.")
    print(f"📁 Saved to: {args.output_dir}/{{source}}/images/augmented/")
    print("=" * 70)
