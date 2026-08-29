"""M4 静态词表：user_profile.preference_tags → 软偏好关键词（D 的地盘）。

依据 data/public_set.jsonl（200 条）实测：preference_tags 是闭集 9 值
fit/material/comfort/style/durability/performance/warmth/weather/general shopping。
summary/average_prior_rating/purchase_frequency 均可由其他字段确定性推出或恒定，
没有独立信息量，不在此解析。

词表是起点，非终稿——建议后续对着 catalog.jsonl 真实商品文案词频校准。
"""

from __future__ import annotations

TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fit": ("fit", "true to size", "relaxed fit", "slim fit", "snug"),
    "material": ("material", "fabric", "cotton", "leather"),
    "comfort": ("comfortable", "comfort", "soft", "cushioned", "cozy"),
    "style": ("stylish", "fashion", "trendy", "classic", "casual"),
    "durability": ("durable", "sturdy", "heavy duty", "long lasting"),
    "performance": ("breathable", "moisture wicking", "quick dry", "athletic"),
    "warmth": ("warm", "insulated", "thermal", "fleece"),
    "weather": ("waterproof", "water resistant", "windproof"),
    # "general shopping" 及私有集可能出现的未知 tag 不在表里 → profile_soft_terms 静默返回 []
}


def profile_soft_terms(profile: dict | None, limit: int = 8) -> list[str]:
    """user_profile → 去重的软偏好关键词列表（供检索查询扩展 / 排序软加权）。"""
    tags = (profile or {}).get("preference_tags") or []
    seen: list[str] = []
    for tag in tags:
        for keyword in TAG_KEYWORDS.get(str(tag), ()):
            if keyword not in seen:
                seen.append(keyword)
    return seen[:limit]
