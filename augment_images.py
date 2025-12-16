"""
Phase 2: Image Augmentation using Augraphy
Load ảnh sạch và áp dụng augmentation
"""
import random
import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm
from augraphy import *


class ImageAugmenter:
    """
    Phase 2: Load ảnh sạch và áp dụng Augraphy augmentation.
    """

    def __init__(self, input_dir="datasets/unified/images/clean", 
                 output_dir="datasets/unified/images/augmented"):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📂 Input directory: {self.input_dir}")
        print(f"📁 Output directory: {self.output_dir}")

    def create_augmentation_pipeline(self):
        """Tạo Augraphy pipeline với các hiệu ứng ngẫu nhiên"""
        
        ink_phase = [
            InkBleed(
                intensity_range=(0.1, 0.2),
                kernel_size=random.choice([(3, 3), (3, 3)]),
                severity=(0.05, 0.1),
                p=0.15,
            ),
            OneOf(
                [
                    InkShifter(
                        text_shift_scale_range=(2, 5),
                        text_shift_factor_range=(1, 1),
                        text_fade_range=(0, 0),
                        blur_kernel_size=(3, 3),
                        blur_sigma=0,
                        noise_type="random",
                    ),
                    BleedThrough(
                        intensity_range=(0.02, 0.08),
                        color_range=(96, 224),
                        ksize=(7, 7),
                        sigmaX=1,
                        alpha=random.uniform(0.02, 0.05),
                        offsets=(10, 20),
                    ),
                ],
                p=0.5,
            ),
        ]

        paper_phase = [
            ColorPaper(
                hue_range=(0, 255),
                saturation_range=(5, 20),
                p=0.2,
            ),
            OneOf(
                [
                    DelaunayTessellation(
                        n_points_range=(500, 800),
                        n_horizontal_points_range=(500, 800),
                        n_vertical_points_range=(500, 800),
                        noise_type="random",
                        color_list="default",
                        color_list_alternate="default",
                    ),
                    PatternGenerator(
                        imgx=random.randint(256, 512),
                        imgy=random.randint(256, 512),
                        n_rotation_range=(10, 15),
                        color="random",
                        alpha_range=(0.08, 0.2),
                    ),
                    VoronoiTessellation(
                        mult_range=(50, 80),
                        seed=19829813472,
                        num_cells_range=(500, 1000),
                        noise_type="random",
                        background_value=(200, 255),
                    ),
                ],
                p=0.7,
            ),
            AugmentationSequence(
                [
                    # NoiseTexturize(
                    #     sigma_range=(1, 4),
                    #     turbulence_range=(1, 2),
                    # ),
                    BrightnessTexturize(
                        texturize_range=(0.97, 0.99),
                        deviation=0.01,
                    ),
                ],
            ),
        ]

        post_phase = [
            OneOf(
                [
                    DirtyDrum(
                        line_width_range=(1, 2),
                        line_concentration=random.uniform(0.02, 0.05),
                        direction=random.randint(0, 2),
                        noise_intensity=random.uniform(0.2, 0.4),
                        noise_value=(128, 224),
                        ksize=random.choice([(3, 3), (5, 5)]),
                        sigmaX=0,
                        p=0.15,
                    ),
                    DirtyRollers(
                        line_width_range=(2, 16),
                        scanline_type=0,
                    ),
                ],
                p=0.5,
            ),
            SubtleNoise(
                subtle_range=random.randint(3, 6),
                p=0.2,
            ),
            Jpeg(
                quality_range=(65, 95),
                p=0.25,
            ),
            OneOf(
                [
                    Markup(
                        num_lines_range=(1, 3),
                        markup_length_range=(0.3, 0.6),
                        markup_thickness_range=(1, 1),
                        markup_type=random.choice(
                            ["strikethrough", "crossed", "highlight", "underline"]
                        ),
                        markup_color="random",
                        single_word_mode=False,
                        repetitions=1,
                    ),
                    Scribbles(
                        scribbles_type="random",
                        scribbles_location="random",
                        scribbles_size_range=(150, 400),
                        scribbles_count_range=(1, 3),
                        scribbles_thickness_range=(1, 2),
                        scribbles_brightness_change=[64, 128],
                        scribbles_text="random",
                        scribbles_text_font="random",
                        scribbles_text_rotate_range=(0, 360),
                        scribbles_lines_stroke_count_range=(1, 3),
                    ),
                ],
                p=0.5,
            ),
            OneOf(
                [
                    GlitchEffect(
                        glitch_direction="random",
                        glitch_number_range=(1, 4),
                        glitch_size_range=(2, 12),
                        glitch_offset_range=(2, 12),
                    ),
                    ColorShift(
                        color_shift_offset_x_range=(1, 2),
                        color_shift_offset_y_range=(1, 2),
                        color_shift_iterations=(1, 1),
                        color_shift_brightness_range=(0.97, 1.03),
                        color_shift_gaussian_kernel_range=(3, 3),
                    ),
                ],
                p=0.5,
            ),
            BadPhotoCopy(
                noise_mask=None,
                noise_type=-1,
                noise_side="random",
                noise_iteration=(1, 1),
                noise_size=(1, 1),
                noise_value=(200, 240),
                noise_sparsity=(0.6, 0.9),
                noise_concentration=(0.02, 0.1),
                blur_noise=False,
                blur_noise_kernel=random.choice([(3, 3), (5, 5)]),
                wave_pattern=False,
                edge_effect=False,
                p=0.15,
            ),
            Faxify(
                scale_range=(0.6, 0.9),
                monochrome=random.choice([0, 1]),
                monochrome_method="random",
                monochrome_arguments={},
                halftone=random.choice([0, 1]),
                invert=1,
                half_kernel_size=random.choice([(1, 1), (2, 2)]),
                angle=(0, 360),
                sigma=(1, 1),
                p=0.2,
            ),
        ]

        pipeline = AugraphyPipeline(
            ink_phase=ink_phase, 
            paper_phase=paper_phase, 
            post_phase=post_phase
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

    def augment_batch(self, input_pattern="*.png"):
        """
        Augment nhiều ảnh tuần tự với progress bar
        
        Args:
            input_pattern: Pattern để tìm file (vd: "*.png", "clean_*.png")
            
        Returns:
            List đường dẫn các ảnh đã augment
        """
        # Tìm tất cả file ảnh
        image_files = sorted(list(self.input_dir.glob(input_pattern)))
        
        if not image_files:
            print(f"⚠️  No images found matching pattern: {input_pattern}")
            return []
        
        print(f"📊 Found {len(image_files)} images to augment")
        
        # Process tuần tự với progress bar
        output_paths = []
        
        for img_path in tqdm(image_files, desc="🎭 Augmenting images", unit="img"):
            # Keep the same filename (just change directory)
            output_filename = img_path.name
            output_path = self.output_dir / output_filename
            
            success = self.augment_single_image(img_path, output_path)
            if success:
                output_paths.append(str(output_path))
        
        return output_paths


# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("PHASE 2: IMAGE AUGMENTATION")
    print("=" * 70)
    
    augmenter = ImageAugmenter(
        input_dir="datasets/unified/images/clean",
        output_dir="datasets/unified/images/augmented"
    )
    
    # Augment tất cả ảnh clean
    paths = augmenter.augment_batch(input_pattern="*.png")
    
    print("\n" + "=" * 70)
    print(f"✅ Phase 2 completed. Augmented {len(paths)} images.")
    print(f"📁 Saved to: datasets/unified/images/augmented/")
    print("=" * 70)
