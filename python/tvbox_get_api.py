import os
import json
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SOURCES_FILE = "apilinks.txt"
OUTPUT_DIR = "tvbox"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "all_in_one.json")
LIST_FILE = "list.txt"

HEADERS = {
    "User-Agent": "okhttp/3.12.11"
}

def load_sources():
    """解析 apilinks.txt，返回 [(name, [url1, url2, ...]), ...]"""
    sources = []
    if not os.path.exists(SOURCES_FILE):
        return sources
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split(',') if p.strip()]
            if not parts:
                continue
            # 第一部分如果以 http 开头，说明整行都是 URL，没有名称
            if parts[0].startswith('http'):
                sources.append((parts[0], [parts[0]]))
            else:
                name = parts[0]
                urls = parts[1:]
                if urls:
                    sources.append((name, urls))
    return sources

def fetch_url(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"    [失败] {url} -> {e}")
        return None

def fetch_with_fallback(name, urls):
    """按顺序尝试多个 URL，返回第一个成功的数据"""
    for url in urls:
        print(f"  尝试: {url}")
        data = fetch_url(url)
        if data:
            print(f"  ✓ 成功: {url}")
            return data
    print(f"  ✗ [{name}] 所有镜像均失败")
    return None

def extract_data(data):
    """提取 sites/parses/lives，并递归处理多仓"""
    sites, parses, lives = [], [], []
    if not isinstance(data, dict):
        return sites, parses, lives

    # 多仓：有 urls 字段
    if isinstance(data.get("urls"), list):
        for item in data["urls"]:
            sub_url = None
            if isinstance(item, str):
                sub_url = item
            elif isinstance(item, dict):
                sub_url = item.get("url")
            if sub_url:
                print(f"    [子仓] {sub_url}")
                sub_data = fetch_url(sub_url)
                if sub_data:
                    s, p, l = extract_data(sub_data)
                    sites.extend(s)
                    parses.extend(p)
                    lives.extend(l)
        return sites, parses, lives

    # 单仓
    if isinstance(data.get("sites"), list):
        sites.extend(data["sites"])
    if isinstance(data.get("parses"), list):
        parses.extend(data["parses"])
    if isinstance(data.get("lives"), list):
        lives.extend(data["lives"])
    return sites, parses, lives

def main():
    sources = load_sources()
    if not sources:
        print(f"错误: {SOURCES_FILE} 不存在或为空。")
        return

    print(f"共读取到 {len(sources)} 个上游接口。开始抓取...")
    print("=" * 60)

    all_sites, all_parses, all_lives = [], [], []
    seen_keys, seen_parse_names, seen_live_names = set(), set(), set()

    for name, urls in sources:
        print(f"\n▶ [{name}] 共 {len(urls)} 个镜像")
        data = fetch_with_fallback(name, urls)
        if not data:
            continue

        sites, parses, lives = extract_data(data)

        for site in sites:
            if not isinstance(site, dict):
                continue
            key = site.get("key")
            site_type = site.get("type", 0)
            # 规避 type:3 蜘蛛源冲突
            if site_type == 3:
                continue
            if key and key not in seen_keys:
                seen_keys.add(key)
                all_sites.append(site)

        for parse in parses:
            if not isinstance(parse, dict):
                continue
            p_name = parse.get("name")
            if p_name and p_name not in seen_parse_names:
                seen_parse_names.add(p_name)
                all_parses.append(parse)

        for live in lives:
            if not isinstance(live, dict):
                continue
            l_name = live.get("name")
            if l_name and l_name not in seen_live_names:
                seen_live_names.add(l_name)
                all_lives.append(live)

    print("\n" + "=" * 60)
    print(f"共合并 {len(all_sites)} 个点播源，{len(all_parses)} 个解析，{len(all_lives)} 个直播源。")

    # 4K 优先排序
    def sort_key(site):
        name = site.get("name", "").lower()
        key = site.get("key", "").lower()
        if "4k" in name or "4k" in key:
            return 0
        if "蓝光" in name or "blu" in name:
            return 1
        if "高码" in name or "hd" in name:
            return 2
        return 3

    all_sites.sort(key=sort_key)

    final_config = {
        "sites": all_sites,
        "parses": all_parses,
        "lives": all_lives
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_config, f, ensure_ascii=False, indent=2)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    with open(LIST_FILE, 'w', encoding='utf-8') as f:
        f.write(f"聚合全能接口, 大小: {file_size_kb:.2f} KB, 更新时间: {now_str}\n")

    print(f"聚合完成！文件已保存至 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
