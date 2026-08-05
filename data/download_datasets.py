# -*- coding: utf-8 -*-
"""
公开数据集下载脚本
尝试从 ModelScope / HuggingFace 下载 AdvertiseGen 和天池商品描述数据集
"""

import urllib.request
import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def download_advertise_gen_modelscope():
    """
    通过 ModelScope API 下载 AdvertiseGen 数据集
    https://modelscope.cn/datasets/lvjianjin/AdvertiseGen
    """
    print("=" * 60)
    print("尝试从 ModelScope 下载 AdvertiseGen 数据集...")
    print("=" * 60)

    # 第 1 步：获取文件列表
    try:
        files_url = "https://modelscope.cn/api/v1/datasets/lvjianjin/AdvertiseGen/repo/files"
        req = urllib.request.Request(files_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        files = data.get("Data", {}).get("Files", [])
        print(f"找到 {len(files)} 个文件:")
        for f in files:
            name = f.get("Name", "unknown")
            size = f.get("Size", 0)
            print(f"  {name} ({size} bytes)")

        # 第 2 步：下载数据文件
        for f in files:
            name = f.get("Name", "")
            if name.endswith(".json") or name.endswith(".jsonl"):
                download_url = f"https://modelscope.cn/api/v1/datasets/lvjianjin/AdvertiseGen/repo?Revision=master&FilePath={name}"
                print(f"\n下载: {name} ...")
                
                req2 = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req2, timeout=120) as resp2:
                    content = resp2.read()
                
                output_file = RAW_DIR / name
                with open(output_file, "wb") as fout:
                    fout.write(content)
                print(f"  已保存: {output_file} ({len(content)} bytes)")
                return str(output_file)
        
        print("未找到数据文件")
        return None

    except Exception as e:
        print(f"ModelScope 下载失败: {e}")
        return None


def download_advertise_gen_hf_mirror():
    """
    通过 HuggingFace 镜像下载 AdvertiseGen
    """
    print("\n" + "=" * 60)
    print("尝试从 HuggingFace 镜像下载 AdvertiseGen...")
    print("=" * 60)

    mirrors = [
        "https://hf-mirror.com",
        "https://huggingface.co",
    ]

    for mirror in mirrors:
        try:
            # 获取文件列表
            api_url = f"{mirror}/api/datasets/lvjianjin/AdvertiseGen"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                info = json.loads(resp.read().decode("utf-8"))
            
            print(f"通过 {mirror} 连接成功!")
            
            siblings = info.get("siblings", [])
            for sib in siblings:
                fname = sib.get("rfilename", "")
                if fname.endswith(".json") or fname.endswith(".jsonl"):
                    # 下载文件
                    dl_url = f"{mirror}/datasets/lvjianjin/AdvertiseGen/resolve/main/{fname}"
                    print(f"下载: {fname} ...")
                    
                    req2 = urllib.request.Request(dl_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req2, timeout=120) as resp2:
                        content = resp2.read()
                    
                    output_file = RAW_DIR / fname
                    with open(output_file, "wb") as fout:
                        fout.write(content)
                    print(f"  已保存: {output_file} ({len(content)} bytes)")
                    return str(output_file)
            
            print("未找到数据文件")
            return None

        except Exception as e:
            print(f"  {mirror} 失败: {e}")
            continue

    print("所有镜像均不可用")
    return None


def generate_sample_data():
    """
    生成模拟数据作为 fallback（保留之前的数据）
    """
    print("\n" + "=" * 60)
    print("检查/生成模拟数据...")
    print("=" * 60)

    samples = {
        "3c_digital": [
            {
                "id": "3c_001",
                "title": "XX品牌 TWS Pro 真无线降噪耳机",
                "category": "3C数码/智能穿戴/耳机",
                "brand": "XX",
                "price": 299.00,
                "features": [
                    {"name": "蓝牙版本", "value": "5.3"},
                    {"name": "降噪类型", "value": "主动降噪ANC"},
                    {"name": "续航时间", "value": "30小时（含充电仓）"},
                    {"name": "防水等级", "value": "IPX5"},
                    {"name": "驱动单元", "value": "13mm动圈"}
                ],
                "target_audience": "运动爱好者、通勤族",
                "raw_desc": "XX品牌TWS耳机，蓝牙5.3，续航30小时..."
            }
        ],
        "beauty": [
            {
                "id": "beauty_001",
                "title": "YY品牌 水光焕肤精华液 30ml",
                "category": "美妆/护肤/精华",
                "brand": "YY",
                "price": 189.00,
                "features": [
                    {"name": "核心成分", "value": "烟酰胺+玻尿酸+积雪草提取物"},
                    {"name": "适用肤质", "value": "所有肤质"},
                    {"name": "功效", "value": "补水保湿、提亮肤色、修护屏障"},
                    {"name": "质地", "value": "清透水润不黏腻"},
                    {"name": "规格", "value": "30ml"}
                ],
                "target_audience": "25-35岁女性，关注护肤",
                "raw_desc": "YY品牌精华液，补水保湿，提亮肤色..."
            }
        ],
        "home": [
            {
                "id": "home_001",
                "title": "ZZ品牌 太空记忆棉护颈枕",
                "category": "家居/床上用品/枕头",
                "brand": "ZZ",
                "price": 159.00,
                "features": [
                    {"name": "材质", "value": "太空记忆棉+冰丝枕套"},
                    {"name": "高度", "value": "10-12cm可调节"},
                    {"name": "适用睡姿", "value": "仰卧/侧卧通用"},
                    {"name": "特点", "value": "慢回弹、透气、防螨"},
                    {"name": "认证", "value": "OEKO-TEX认证"}
                ],
                "target_audience": "颈椎不适人群、睡眠质量差",
                "raw_desc": "ZZ品牌护颈枕，记忆棉材质，慢回弹..."
            }
        ],
        "food": [
            {
                "id": "food_001",
                "title": "AA品牌 有机每日坚果 混合装 750g",
                "category": "食品/零食/坚果",
                "brand": "AA",
                "price": 69.90,
                "features": [
                    {"name": "成分", "value": "核桃仁、腰果、巴旦木、蔓越莓干、蓝莓干"},
                    {"name": "加工方式", "value": "低温烘焙、无油炸"},
                    {"name": "认证", "value": "有机认证、非转基因"},
                    {"name": "包装", "value": "独立小包30袋装"},
                    {"name": "保质期", "value": "240天"}
                ],
                "target_audience": "注重健康饮食的上班族、学生",
                "raw_desc": "AA品牌每日坚果，7种坚果果干搭配..."
            }
        ]
    }

    for category, items in samples.items():
        output_file = RAW_DIR / f"{category}.json"
        if not output_file.exists():
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            print(f"  已生成: {output_file} ({len(items)} 条)")
        else:
            print(f"  已存在: {output_file}")

    return samples


if __name__ == "__main__":
    success = False

    # 1. 尝试 ModelScope
    result = download_advertise_gen_modelscope()
    if result:
        success = True

    # 2. 尝试 HuggingFace 镜像
    if not success:
        result = download_advertise_gen_hf_mirror()
        if result:
            success = True

    # 3. 生成模拟数据（始终执行，补齐品类）
    generate_sample_data()

    print("\n" + "=" * 60)
    if success:
        print("真实数据集下载成功！")
    else:
        print("当前环境无法访问外网，请在你的本地终端手动运行：")
        print("  pip install datasets")
        print("  python data/download_datasets.py")
        print("")
        print("或手动下载：")
        print("  AdvertiseGen: https://modelscope.cn/datasets/lvjianjin/AdvertiseGen")
        print("  天池商品描述: https://tianchi.aliyun.com/dataset/9717")
    print("=" * 60)
