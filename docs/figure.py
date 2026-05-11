import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# Set style
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.facecolor'] = '#f4f5f5'
plt.rcParams['figure.facecolor'] = '#f4f5f5'
plt.rcParams['grid.color'] = '#e0e0e0'
plt.rcParams['grid.linestyle'] = '-'
plt.rcParams['grid.linewidth'] = 1
plt.rcParams['axes.edgecolor'] = '#333333'
plt.rcParams['axes.linewidth'] = 1

script_dir = os.path.dirname(os.path.abspath(__file__))
out_dir = os.path.join(script_dir, "reports", "figures")
os.makedirs(out_dir, exist_ok=True)

def plot_group_comparison():
    csv_path = os.path.join(script_dir, 'Openlet Research - G-Eval.csv')
    df = pd.read_csv(csv_path, header=None)
    
    sllm_base = df.iloc[7:12]
    sllm_base_l1 = sllm_base.iloc[:, 1].astype(float).mean()
    sllm_base_l2 = sllm_base.iloc[:, 4].astype(float).mean()
    sllm_base_l3 = sllm_base.iloc[:, 7].astype(float).mean()
    
    sllm_multi = df.iloc[13:18]
    sllm_multi_l1 = sllm_multi.iloc[:, 1].astype(float).mean()
    sllm_multi_l2 = sllm_multi.iloc[:, 4].astype(float).mean()
    sllm_multi_l3 = sllm_multi.iloc[:, 7].astype(float).mean()
    
    prop = df.iloc[19:22]
    prop_l1 = prop.iloc[:, 1].astype(float).mean()
    prop_l2 = prop.iloc[:, 4].astype(float).mean()
    prop_l3 = prop.iloc[:, 7].astype(float).mean()
    
    labels = ['Cấp độ 1', 'Cấp độ 2', 'Cấp độ 3']
    sllm_vals = [sllm_base_l1, sllm_base_l2, sllm_base_l3]
    multi_vals = [sllm_multi_l1, sllm_multi_l2, sllm_multi_l3]
    prop_vals = [prop_l1, prop_l2, prop_l3]
    
    x = np.arange(len(labels))
    width = 0.25
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    rects1 = ax.bar(x - width, sllm_vals, width, label='sLLM cơ sở', color='#ff4d6d')
    rects2 = ax.bar(x, multi_vals, width, label='sLLM + đa tác tử', color='#5c7cfa')
    rects3 = ax.bar(x + width, prop_vals, width, label='LLM thương mại', color='#20d489')
    
    ax.set_ylabel('Tỉ lệ chấp nhận', fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=14)
    ax.legend(fontsize=12, facecolor='white', edgecolor='lightgray', framealpha=1)
    ax.set_ylim(0, 1.1)
    ax.tick_params(axis='y', labelsize=12)
    ax.grid(axis='y')
    ax.set_axisbelow(True)
    
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{height:.2f}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=10)
    
    autolabel(rects1)
    autolabel(rects2)
    autolabel(rects3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'group_comparison.pdf'), bbox_inches='tight')
    plt.close()

def plot_cost_quality():
    costs = {
        'Gemma 3 12B': {'base': 0.02, 'multi': 0.21},
        'Qwen3 8B': {'base': 0.01, 'multi': 0.18},
        'Phi-4': {'base': 0.02, 'multi': 0.19},
        'Nemotron 9B': {'base': 0.02, 'multi': 0.30},
        'Llama 3.1 8B': {'base': 0.04, 'multi': 0.47},
        'Gemini 3 Flash': {'prop': 0.46},
        'GPT-5 Mini': {'prop': 0.26},
        'Claude Haiku 4.5': {'prop': 0.80}
    }
    
    csv_path = os.path.join(script_dir, 'Openlet Research - G-Eval.csv')
    df = pd.read_csv(csv_path, header=None)
    
    quals_base = {
        'Gemma 3 12B': df.iloc[7, [1,4,7]].astype(float).mean(),
        'Qwen3 8B': df.iloc[8, [1,4,7]].astype(float).mean(),
        'Phi-4': df.iloc[9, [1,4,7]].astype(float).mean(),
        'Nemotron 9B': df.iloc[10, [1,4,7]].astype(float).mean(),
        'Llama 3.1 8B': df.iloc[11, [1,4,7]].astype(float).mean(),
    }
    
    quals_multi = {
        'Gemma 3 12B': df.iloc[13, [1,4,7]].astype(float).mean(),
        'Qwen3 8B': df.iloc[14, [1,4,7]].astype(float).mean(),
        'Phi-4': df.iloc[15, [1,4,7]].astype(float).mean(),
        'Nemotron 9B': df.iloc[16, [1,4,7]].astype(float).mean(),
        'Llama 3.1 8B': df.iloc[17, [1,4,7]].astype(float).mean(),
    }
    
    quals_prop = {
        'Gemini 3 Flash': df.iloc[19, [1,4,7]].astype(float).mean(),
        'GPT-5 Mini': df.iloc[20, [1,4,7]].astype(float).mean(),
        'Claude Haiku 4.5': df.iloc[21, [1,4,7]].astype(float).mean(),
    }
    
    fig, ax = plt.subplots(figsize=(10, 7))
    
    # Manual adjustments for base models
    base_label_settings = {
        'Gemma 3 12B': {'ox': 0.015, 'oy': 0.01, 'ha': 'left', 'va': 'bottom'},
        'Qwen3 8B': {'ox': 0.01, 'oy': 0.015, 'ha': 'center', 'va': 'bottom'},
        'Phi-4': {'ox': 0.0, 'oy': -0.02, 'ha': 'center', 'va': 'top'},
        'Nemotron 9B': {'ox': 0.015, 'oy': 0.0, 'ha': 'left', 'va': 'center'},
        'Llama 3.1 8B': {'ox': 0.015, 'oy': 0.01, 'ha': 'left', 'va': 'bottom'}
    }

    for model, q in quals_base.items():
        c = costs[model]['base']
        ax.scatter(c, q, color='#e60039', marker='o', s=100, zorder=3)
        s = base_label_settings.get(model, {'ox': 0.015, 'oy': 0.01, 'ha': 'left', 'va': 'bottom'})
        ax.text(c + s['ox'], q + s['oy'], model, fontsize=9, color='#e60039', 
                ha=s['ha'], va=s['va'])
        
    ax.scatter([], [], color='#e60039', marker='o', s=100, label='sLLM cơ sở')
    
    # Manual adjustments for multi-agent models
    multi_label_settings = {
        'Gemma 3 12B': {'ox': 0.0, 'oy': -0.02, 'ha': 'center', 'va': 'top'},
        'Qwen3 8B': {'ox': 0.015, 'oy': 0.01, 'ha': 'left', 'va': 'bottom'},
        'Phi-4': {'ox': -0.015, 'oy': 0.01, 'ha': 'right', 'va': 'bottom'},
        'Nemotron 9B': {'ox': 0.015, 'oy': 0.01, 'ha': 'left', 'va': 'bottom'},
        'Llama 3.1 8B': {'ox': 0.015, 'oy': 0.01, 'ha': 'left', 'va': 'bottom'}
    }

    for model, q in quals_multi.items():
        c = costs[model]['multi']
        ax.scatter(c, q, color='#4169e1', marker='s', s=100, zorder=3)
        s = multi_label_settings.get(model, {'ox': 0.015, 'oy': 0.01, 'ha': 'left', 'va': 'bottom'})
        ax.text(c + s['ox'], q + s['oy'], model, fontsize=9, color='#4169e1',
                ha=s['ha'], va=s['va'])
        
    ax.scatter([], [], color='#4169e1', marker='s', s=100, label='sLLM + đa tác tử')
    
    for model, q in quals_prop.items():
        c = costs[model]['prop']
        ax.scatter(c, q, color='#00c982', marker='D', s=100, zorder=3)
        ax.text(c + 0.015, q + 0.01, model, fontsize=9, color='#00c982')
        
    ax.scatter([], [], color='#00c982', marker='D', s=100, label='LLM thương mại')
    
    ax.set_xlabel('Chi phí (USD trên 100 đoạn văn)', fontsize=14)
    ax.set_ylabel('Tỉ lệ chấp nhận trung bình', fontsize=14)
    ax.set_xlim(-0.02, 0.9)
    ax.set_ylim(0.1, 1.05)
    ax.tick_params(axis='both', labelsize=12)
    ax.grid(True, zorder=0)
    ax.legend(loc='lower right', fontsize=12, facecolor='white', edgecolor='lightgray', framealpha=1)
    
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'cost_quality.pdf'), bbox_inches='tight')
    plt.close()

def plot_ocr_comparison():
    csv_path = os.path.join(script_dir, 'Openlet Research - OCR.csv')
    df = pd.read_csv(csv_path, header=None)
    
    models_vlm = ['DeepSeek\nOCR 2', 'DotOCR\n1.5', 'MinerU\n2.5', 'Paddle\nOCR VL']
    models_prop = ['Gemini 3\nFlash', 'GPT-5\nMini', 'Claude\nHaiku 4.5']
    models = models_vlm + models_prop
    
    clean_cer = df.iloc[[5,6,7,8,10,11,12], 1].astype(float).tolist()
    clean_wer = df.iloc[[5,6,7,8,10,11,12], 2].astype(float).tolist()
    
    aug_cer = df.iloc[[17,18,19,20,22,23,24], 1].astype(float).tolist()
    aug_wer = df.iloc[[17,18,19,20,22,23,24], 2].astype(float).tolist()
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    x = np.arange(len(models))
    width = 0.35
    
    color_clean = '#527ff4'
    color_aug = '#f24063'
    
    ax1.bar(x - width/2, clean_cer, width, label='Ảnh sạch', color=color_clean)
    ax1.bar(x + width/2, aug_cer, width, label='Ảnh thêm nhiễu', color=color_aug)
    ax1.set_ylabel('CER', fontsize=14)
    ax1.set_title('Tỉ lệ lỗi kí tự (CER)', fontsize=16)
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, fontsize=10)
    ax1.grid(axis='y', zorder=0)
    ax1.set_axisbelow(True)
    ax1.legend(fontsize=12, facecolor='white', edgecolor='lightgray', framealpha=1, loc='upper left')
    
    ax1.axvline(x=3.5, color='gray', linestyle='--', alpha=0.5)
    # ax1.text(1.5, ax1.get_ylim()[1]*0.95, 'VLM mã nguồn mở', ha='center', va='top', color='gray', fontsize=10)
    # ax1.text(5, ax1.get_ylim()[1]*0.95, 'LLM thương mại', ha='center', va='top', color='gray', fontsize=10)
    
    ax2.bar(x - width/2, clean_wer, width, label='Ảnh sạch', color=color_clean)
    ax2.bar(x + width/2, aug_wer, width, label='Ảnh thêm nhiễu', color=color_aug)
    ax2.set_ylabel('WER', fontsize=14)
    ax2.set_title('Tỉ lệ lỗi từ (WER)', fontsize=16)
    ax2.set_xticks(x)
    ax2.set_xticklabels(models, fontsize=10)
    ax2.grid(axis='y', zorder=0)
    ax2.set_axisbelow(True)
    ax2.legend(fontsize=12, facecolor='white', edgecolor='lightgray', framealpha=1, loc='upper right')
    
    ax2.axvline(x=3.5, color='gray', linestyle='--', alpha=0.5)
    # ax2.text(1.5, ax2.get_ylim()[1]*0.95, 'VLM mã nguồn mở', ha='center', va='top', color='gray', fontsize=10)
    # ax2.text(5, ax2.get_ylim()[1]*0.95, 'LLM thương mại', ha='center', va='top', color='gray', fontsize=10)

    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'ocr_comparison.pdf'), bbox_inches='tight')
    plt.close()

if __name__ == '__main__':
    plot_group_comparison()
    plot_cost_quality()
    plot_ocr_comparison()