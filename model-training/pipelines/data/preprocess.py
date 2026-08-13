# -*- coding: utf-8 -*-
"""
数据预处理脚本
将 AdvertiseGen + 天池商品描述数据集转换为 Alpaca 格式

数据来源:
  1. AdvertiseGen (清华 CoAI): 114K 条服装类结构化属性+文案
  2. 天池商品描述 (阿里): 212万条 title + 描述文案，覆盖全品类

处理流程:
  1. 加载 AdvertiseGen → 解析 content 属性键值对 → Alpaca格式
  2. 加载天池数据 → 品类分类 → 过滤采样 → Alpaca格式
  3. 合并、去重、质量过滤
  4. 输出 train/val/test
"""

import json
import re
import random
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent
RAW_DIR = DATA_DIR / "raw"
LABELED_DIR = DATA_DIR / "labeled"
LABELED_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)

# ============================================================
# 品类关键词映射（扩展版，覆盖天池全品类）
# ============================================================
CATEGORY_KEYWORDS = {
    "3c_digital": [
        "耳机", "手机", "电脑", "笔记本", "平板", "充电器", "数据线", "键盘",
        "鼠标", "音箱", "蓝牙", "智能手表", "手环", "相机", "无人机", "投影仪",
        "显示器", "移动硬盘", "U盘", "路由器", "数码", "电子", "智能机器人",
        "机器人", "阿尔法", "优必选", "switch", "ps4", "xbox", "游戏机",
        "充电宝", "type-c", "typec", "内存卡", "sd卡", "读卡器", "拓展坞",
        "机械键盘", "电竞", "麦克风", "声卡", "手机壳", "钢化膜", "自拍杆"
    ],
    "beauty": [
        "护肤", "精华", "面霜", "乳液", "面膜", "防晒", "口红", "粉底", "眼影",
        "化妆", "美妆", "香水", "洗面奶", "卸妆", "BB霜", "CC霜", "气垫",
        "遮瑕", "眉笔", "眼线", "睫毛", "腮红", "高光", "美甲", "护发",
        "洗发水", "沐浴露", "身体乳", "爽肤水", "隔离霜", "素颜霜", "散粉",
        "精华液", "眼霜", "颈霜", "唇膏", "唇釉", "染发", "烫发", "发膜"
    ],
    "home": [
        "家居", "家具", "枕头", "被子", "床垫", "沙发", "桌椅", "灯具", "窗帘",
        "收纳", "地毯", "装饰", "厨具", "餐具", "清洁", "浴室",
        "毛巾", "拖鞋", "香薰", "抱枕", "四件套", "凉席", "蚊帐", "床单",
        "被套", "枕芯", "床笠", "沙发垫", "桌布", "墙纸", "挂钟", "花盆",
        "保温杯", "水杯", "焖烧杯", "饭盒", "保鲜盒", "锅", "炒锅", "蒸锅"
    ],
    "food": [
        "零食", "坚果", "饼干", "巧克力", "糖果", "薯片", "糕点", "面包",
        "咖啡", "茶叶", "饮料", "牛奶", "酸奶", "果汁", "蜂蜜", "枸杞",
        "红枣", "燕窝", "阿胶", "冲饮", "代餐", "蛋白", "燕麦", "麦片",
        "牛肉干", "猪肉脯", "果干", "海苔", "辣条", "方便面", "螺蛳粉",
        "酸辣粉", "火锅底料", "调味料", "酱油", "醋", "食用油", "大米"
    ],
    "maternity_baby": [
        "产后", "孕妇", "婴儿", "宝宝", "儿童", "小孩", "童装", "童鞋",
        "奶粉", "纸尿裤", "奶瓶", "婴儿车", "安全座椅", "爬行垫", "积木",
        "玩具", "早教", "绘本", "安抚", "哺乳", "待产", "胎教", "新生儿",
        "幼童", "少儿", "公主鞋", "女童", "男童", "宝宝鞋", "学步鞋",
        "骨盆带", "收腹带", "犬印", "吸奶器", "温奶器", "消毒器", "辅食"
    ],
    "auto": [
        "车载", "汽车", "车用", "座垫", "行车记录仪", "凯迪拉克", "宝马",
        "奔驰", "奥迪", "丰田", "本田", "日产", "大众", "特斯拉", "比亚迪",
        "头枕", "腰靠", "脚垫", "车衣", "遮阳", "玻璃水", "机油", "轮胎",
        "方向盘套", "导航", "倒车影像", "etag", "etc", "汽车用品"
    ],
    "sports_outdoor": [
        "运动", "健身", "跑步", "瑜伽", "户外", "登山", "游泳", "骑行",
        "球类", "篮球", "足球", "羽毛球", "乒乓球", "网球", "跳绳", "哑铃",
        "手套", "护膝", "护腕", "速干", "冲锋衣", "帐篷", "睡袋", "野餐",
        "渔具", "钓鱼", "滑板", "轮滑", "露营", "徒步", "运动鞋", "跑鞋"
    ]
}

# AdvertiseGen 服装类关键词
CLOTHING_KEYWORDS = [
    "上衣", "裤", "裙", "外套", "卫衣", "衬衫", "T恤", "毛衣", "风衣",
    "大衣", "西装", "牛仔", "连衣裙", "半身裙", "阔腿裤", "短裤", "背心",
    "针织衫", "polo衫", "雪纺", "蕾丝", "棉衣", "羽绒服", "马甲", "开衫",
    "女装", "男装", "春装", "夏装", "秋装", "冬装", "新款", "韩版", "宽松",
    "显瘦", "bf", "怪味", "复古", "休闲", "气质", "时尚", "潮流", "百搭"
]


def load_advertise_gen(filepath):
    """加载 AdvertiseGen JSONL 数据"""
    if not filepath.exists():
        print(f"  [跳过] 文件不存在: {filepath}")
        return []
    
    data = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    print(f"  加载 AdvertiseGen: {len(data)} 条")
    return data


def load_tianchi(filepath):
    """
    加载天池商品描述数据集
    格式: title\tdescription (tab 分隔)
    回退: 尝试 jsonl 格式
    """
    if not filepath.exists():
        print(f"  [跳过] 文件不存在: {filepath}")
        return []
    
    data = []
    # 先尝试 tab 分隔
    with open(filepath, "r", encoding="utf-8") as f:
        first_line = f.readline()
    
    if "\t" in first_line:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    title, desc = parts
                    data.append({"title": title.strip(), "description": desc.strip()})
    else:
        # 尝试 jsonl
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    
    total = len(data)
    print(f"  加载天池数据: {total} 条")
    return data


def parse_content(content_text):
    """
    解析 AdvertiseGen 的 content 字段
    格式: "类型#裤*版型#宽松*风格#性感*图案#线条*裤型#阔腿裤"
    """
    features = {}
    pairs = content_text.split("*")
    for pair in pairs:
        if "#" in pair:
            parts = pair.split("#", 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                if key and value:
                    features[key] = value
    return features


def classify_ag(content_text, features_dict):
    """AdvertiseGen 品类分类"""
    text = content_text.lower()
    for v in features_dict.values():
        text += " " + v.lower()
    
    is_clothing = any(kw in text for kw in CLOTHING_KEYWORDS)
    if "类型" in features_dict:
        type_val = features_dict["类型"]
        if any(kw in type_val for kw in CLOTHING_KEYWORDS):
            is_clothing = True
    
    if is_clothing:
        return "clothing"
    
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[category] = score
    
    if not scores:
        return None
    
    return max(scores, key=scores.get)


def classify_tianchi(title):
    """根据天池商品标题分类"""
    title_lower = title.lower()
    
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in title_lower)
        if score > 0:
            scores[category] = score
    
    # 服装类单独判断
    clothing_score = sum(1 for kw in CLOTHING_KEYWORDS if kw.lower() in title_lower)
    if clothing_score > 0:
        scores["clothing"] = clothing_score
    
    if not scores:
        return None
    
    return max(scores, key=scores.get)


def convert_advertise_gen_to_alpaca(data, max_per_category=2000):
    """将 AdvertiseGen 数据转换为 Alpaca 格式"""
    alpaca_data = []
    category_counts = defaultdict(int)
    
    for item in data:
        content = item.get("content", "")
        summary = item.get("summary", "")
        
        if not content or not summary:
            continue
        
        features = parse_content(content)
        if not features:
            continue
        
        category = classify_ag(content, features)
        if category is None:
            category = "other"
        
        if category_counts[category] >= max_per_category:
            continue
        
        input_json = {
            "category": category,
            "attributes": features,
            "raw_content": content
        }
        
        alpaca_item = {
            "instruction": "你是一名专业的电商文案撰写师。请根据以下商品信息，生成一段吸引人的商品描述文案，要求：1) 信息准确无误；2) 突出核心卖点；3) 语言流畅有吸引力；4) 不违反广告法。",
            "input": json.dumps(input_json, ensure_ascii=False),
            "output": summary,
            "metadata": {
                "category": category,
                "source": "AdvertiseGen",
                "quality_label": "auto",
                "num_attributes": len(features)
            }
        }
        alpaca_data.append(alpaca_item)
        category_counts[category] += 1
    
    print(f"  AdvertiseGen → Alpaca: {len(alpaca_data)} 条")
    for cat, cnt in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {cnt} 条")
    
    return alpaca_data


def convert_tianchi_to_alpaca(data, max_per_category=2000, min_desc_len=30):
    """
    将天池商品描述数据转换为 Alpaca 格式
    - 按品类采样，每品类最多 max_per_category 条
    - 过滤短描述（< min_desc_len 字符）
    - 同一 title 只保留最长描述
    """
    # 先去重：同一 title 保留最长描述
    title_best = {}
    for item in data:
        title = item.get("title", "")
        desc = item.get("description", "")
        if not title or not desc:
            continue
        if len(desc) < min_desc_len:
            continue
        if title not in title_best or len(desc) > len(title_best[title][1]):
            title_best[title] = (item, desc)
    
    print(f"  去重后 (同title取最长): {len(title_best)} 条")
    
    # 分类
    categorized = defaultdict(list)
    for title, (item, desc) in title_best.items():
        category = classify_tianchi(title)
        if category is None:
            category = "other"
        categorized[category].append((title, desc))
    
    alpaca_data = []
    category_counts = defaultdict(int)
    
    for category, items in sorted(categorized.items(), key=lambda x: -len(x[1])):
        # 随机打乱
        random.shuffle(items)
        taken = 0
        for title, desc in items:
            if taken >= max_per_category:
                break
            if category_counts[category] >= max_per_category:
                break
            
            input_json = {
                "category": category,
                "title": title
            }
            
            alpaca_item = {
                "instruction": "你是一名专业的电商文案撰写师。请根据以下商品信息，生成一段吸引人的商品描述文案，要求：1) 信息准确无误；2) 突出核心卖点；3) 语言流畅有吸引力；4) 不违反广告法。",
                "input": json.dumps(input_json, ensure_ascii=False),
                "output": desc,
                "metadata": {
                    "category": category,
                    "source": "Tianchi",
                    "quality_label": "auto",
                    "desc_length": len(desc)
                }
            }
            alpaca_data.append(alpaca_item)
            category_counts[category] += 1
            taken += 1
    
    print(f"  天池数据 → Alpaca: {len(alpaca_data)} 条")
    for cat, cnt in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {cnt} 条")
    
    return alpaca_data


def deduplicate_and_filter(data):
    """去重和质量过滤"""
    seen_outputs = set()
    seen_inputs = set()
    filtered = []
    
    for item in data:
        output = item.get("output", "")
        inp = item.get("input", "")
        
        if not output or len(output) < 20:
            continue
        
        # 基于 output 前100字符去重
        key = output[:100].strip()
        if key in seen_outputs:
            continue
        
        # 基于 input 去重（同一商品不重复）
        input_key = inp[:200].strip()
        if input_key in seen_inputs:
            continue
        
        seen_outputs.add(key)
        seen_inputs.add(input_key)
        filtered.append(item)
    
    print(f"  去重后: {len(filtered)} 条 (移除 {len(data) - len(filtered)} 条)")
    return filtered


def split_train_val_test(data, train_ratio=0.8, val_ratio=0.1):
    """划分训练集/验证集/测试集"""
    random.shuffle(data)
    
    n = len(data)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    
    train = data[:n_train]
    val = data[n_train:n_train + n_val]
    test = data[n_train + n_val:]
    
    return train, val, test


def save_alpaca_json(data, filepath):
    """保存为 JSON 文件"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  已保存: {filepath} ({len(data)} 条)")


def main():
    print("=" * 60)
    print("数据预处理开始")
    print("=" * 60)
    
    all_alpaca_data = []
    
    # 1. 处理 AdvertiseGen 真实数据（服装类结构化属性）
    print("\n[1/3] 处理 AdvertiseGen 真实数据...")
    ag_file = RAW_DIR / "AdvertiseGen" / "train.json"
    if ag_file.exists():
        ag_data = load_advertise_gen(ag_file)
        ag_alpaca = convert_advertise_gen_to_alpaca(ag_data, max_per_category=2000)
        all_alpaca_data.extend(ag_alpaca)
    else:
        print("  AdvertiseGen 数据未找到，跳过")
    
    # 2. 处理天池商品描述数据（全品类真实数据）
    print("\n[2/3] 处理天池商品描述数据...")
    tianchi_file = RAW_DIR / "tianchi" / "item_desc_dataset.txt"
    if tianchi_file.exists():
        tianchi_data = load_tianchi(tianchi_file)
        tianchi_alpaca = convert_tianchi_to_alpaca(tianchi_data, max_per_category=2000)
        all_alpaca_data.extend(tianchi_alpaca)
    else:
        print("  天池数据未找到，跳过")
    
    # 3. 去重和质量过滤
    print("\n[3/3] 去重和数据集划分...")
    all_alpaca_data = deduplicate_and_filter(all_alpaca_data)
    
    if len(all_alpaca_data) == 0:
        print("\n警告: 没有可用数据！")
        return
    
    # 划分数据集
    train, val, test = split_train_val_test(all_alpaca_data)
    
    # 保存
    save_alpaca_json(train, LABELED_DIR / "train.json")
    save_alpaca_json(val, LABELED_DIR / "val.json")
    save_alpaca_json(test, LABELED_DIR / "test.json")
    
    # 统计报告
    print("\n" + "=" * 60)
    print("数据预处理完成！")
    print("=" * 60)
    print(f"  训练集: {len(train)} 条")
    print(f"  验证集: {len(val)} 条")
    print(f"  测试集: {len(test)} 条")
    print(f"  总计: {len(all_alpaca_data)} 条")
    
    # 品类分布
    print("\n品类分布:")
    category_dist = defaultdict(int)
    for item in all_alpaca_data:
        cat = item.get("metadata", {}).get("category", "unknown")
        category_dist[cat] += 1
    for cat, cnt in sorted(category_dist.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt} 条 ({cnt/len(all_alpaca_data)*100:.1f}%)")
    
    # 来源分布
    print("\n来源分布:")
    source_dist = defaultdict(int)
    for item in all_alpaca_data:
        src = item.get("metadata", {}).get("source", "unknown")
        source_dist[src] += 1
    for src, cnt in sorted(source_dist.items(), key=lambda x: -x[1]):
        print(f"  {src}: {cnt} 条 ({cnt/len(all_alpaca_data)*100:.1f}%)")


if __name__ == "__main__":
    main()