# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# Copyright (c) 2026 SiliconFlow image generation route added.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import urllib.request
import urllib.error
import time
import sys
import json

# Default model = 硅基流动 Kolors (免费)
DEFAULT_MODEL = "Kwai-Kolors/Kolors"
SILICONFLOW_BASE = "https://api.siliconflow.cn/v1"


def _image_generate_siliconflow(prompt: str) -> int:
    """调用硅基流动 Kolors（OpenAI-compatible /v1/images/generations）。"""
    api_key = os.getenv("SILICONFLOW_API_KEY") or os.getenv("MODEL_IMAGE_API_KEY")
    if not api_key:
        print("Error: SILICONFLOW_API_KEY / MODEL_IMAGE_API_KEY 未设置")
        return 1

    model = os.getenv("MODEL_IMAGE_NAME", DEFAULT_MODEL)
    body = {
        "model": model,
        "prompt": prompt,
        "image_size": os.getenv("IMAGE_SIZE", "1024x1024"),
        "num_images": int(os.getenv("IMAGE_COUNT", "1")),
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{SILICONFLOW_BASE}/images/generations",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    download_dir = os.getenv("IMAGE_DOWNLOAD_DIR", os.path.expanduser("./"))
    if not os.path.exists(download_dir):
        try:
            os.makedirs(download_dir, exist_ok=True)
        except Exception as e:
            print(f"Failed to create directory {download_dir}: {e}")
            return 1

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 限流 / 余额不足 / 服务异常 → 返回 2 触发兜底
        body_err = e.read().decode("utf-8", errors="replace")
        print(f"SiliconFlow HTTP {e.code}: {body_err}")
        return 2
    except Exception as e:
        print(f"SiliconFlow error: {e}")
        return 2

    images = payload.get("images") or []
    if not images:
        print("No images returned.")
        return 2

    for i, image in enumerate(images):
        url = image.get("url") if isinstance(image, dict) else None
        if not url:
            continue
        try:
            timestamp = int(time.time() * 1000)
            filename = f"generated_image_{timestamp}_{i}.png"
            filepath = os.path.join(download_dir, filename)
            urllib.request.urlretrieve(url, filepath)
            print(f"Downloaded to: {filepath}")
        except Exception as e:
            print(f"Failed to download image from {url}: {e}")
    return 0


def _image_generate_ark(prompt: str) -> int:
    """火山方舟兜底（保持原逻辑）。"""
    try:
        from volcenginesdkarkruntime import Ark
    except ImportError:
        print("volcenginesdkarkruntime not installed; cannot fallback to ARK.")
        return 1

    api_key = os.getenv("MODEL_IMAGE_API_KEY") or os.getenv("ARK_API_KEY")
    if not api_key:
        print("Error: ARK_API_KEY 未设置，无法兜底。")
        return 1

    client = Ark(api_key=api_key)
    try:
        response = client.images.generate(
            model=os.getenv("ARK_IMAGE_MODEL", "doubao-seedream-4-5-251128"),
            prompt=prompt,
        )
    except Exception as e:
        print(f"ARK fallback error: {e}")
        return 1

    download_dir = os.getenv("IMAGE_DOWNLOAD_DIR", os.path.expanduser("./"))
    if not os.path.exists(download_dir):
        os.makedirs(download_dir, exist_ok=True)

    for i, image in enumerate(response.data):
        try:
            timestamp = int(time.time())
            filename = f"generated_image_{timestamp}_{i}.png"
            filepath = os.path.join(download_dir, filename)
            urllib.request.urlretrieve(image.url, filepath)
            print(f"Downloaded to: {filepath}")
        except Exception as e:
            print(f"Failed to download image: {e}")
    return 0


def image_generate(prompt: str) -> int:
    """主：硅基流动 Kolors（免费）→ 失败回落到 ARK doubao。"""
    if not prompt:
        print("Prompt is empty.")
        return 1

    # 强制走硅基流动免费档（除非 IMAGE_BACKEND=ark 显式指定）
    backend = os.getenv("IMAGE_BACKEND", "siliconflow")
    if backend == "ark":
        return _image_generate_ark(prompt)

    rc = _image_generate_siliconflow(prompt)
    if rc == 0:
        return 0
    print("[fallback] SiliconFlow 失败，回落到 ARK doubao...")
    return _image_generate_ark(prompt)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python image_generate.py <prompt>")
        sys.exit(1)
    prompt = sys.argv[1]
    sys.exit(image_generate(prompt))
