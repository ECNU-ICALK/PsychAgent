#!/bin/bash

# ========================
# Download LLaMA model using Hugging Face Mirror
# ========================

# 设置 Hugging Face 镜像源
export HF_ENDPOINT=https://hf-mirror.com

# 配置参数
MODEL_ID="meta-llama/Llama-3.1-8B-Instruct"
REPO_TYPE="model"
TOKEN="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"
LOCAL_DIR="/fs-computility/CL4Mind/shared/models/Llama-3.1-8B-Instruct"

# 检查 hf CLI 是否安装
if ! command -v hf &>/dev/null; then
  echo "❌ Error: 'hf' CLI not found. Please install it via: pip install -U huggingface_hub"
  exit 1
fi

# 输出信息
echo "🌍 Using Hugging Face mirror: $HF_ENDPOINT"
echo "🚀 Downloading model: $MODEL_ID"
echo "📁 Saving to: $LOCAL_DIR"

# 执行下载命令
hf download "$MODEL_ID" \
  --repo-type "$REPO_TYPE" \
  --token "$TOKEN" \
  --local-dir "$LOCAL_DIR"

# 检查是否成功
if [ $? -eq 0 ]; then
  echo "✅ Download completed successfully!"
else
  echo "❌ Download failed. Check token, endpoint or model permissions."
fi
