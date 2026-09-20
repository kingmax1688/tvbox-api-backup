import os
import json
import requests
import concurrent.futures
import urllib3

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置
SOURCES_FILE = "apilinks.txt"  # 你的源文件列表
OUTPUT_DIR = "tvbox"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "all_in_one.json")
LIST_FILE = "list.txt"

HEADERS = {
    "User-Agent": "okhttp/3.12.11" # TVBox 常用 UA，防止被拦截
}

def fetch_url(url):
    """抓取单个 URL 的内容并解析 JSON"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[抓取失败] {url} -> {e}")
        return None

def parse_multisingle_repo(data):
    """处理单仓或递归解析多仓"""
    sites = []
    parses = []
    lives = []
    
    if not isinstance(data, dict):
        return sites, parses, lives

    # 检查是否为多仓（包含 urls 字段）
    if "urls" in data and isinstance(data["urls"], list):
        print(f"  -> 检测到多仓接口，包含 {len(data['urls'])} 个子仓")
        # 这里我们只提取多仓里的子仓地址，由主程序并发去抓
        return data["urls"], [], []
    
    # 提取 sites
    if "sites" in data and isinstance(data["sites"], list):
        sites.extend(data["sites"])
    # 提取 parses
    if "parses" in data and isinstance(data["parses"], list):
        parses.extend(data["parses"])
    # 提取 lives
    if "lives" in data and isinstance(data["lives"], list):
        lives.extend(data["lives"])
        
    return sites, parses, lives

def main():
    if not os.path.exists(SOURCES_FILE):
        print(f"错误: 找不到 {SOURCES_FILE}，请在仓库根目录创建该文件。")
        return

    # 1. 读取接口列表
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    print(f"共读取到 {len(urls)} 个上游接口。开始抓取...")

    all_sites = []
    all_parses = []
    all_lives = []

    seen_keys = set()
    seen_parse_names = set()
    seen_live_names = set()

    # 2. 多线程并发抓取（提升速度）
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            data = future.result()
            if not data:
                continue

            sites, parses, lives = parse_multisingle_repo(data)
            
            # 如果是多仓，需要再次抓取子仓
            if isinstance(sites, list) and sites and isinstance(sites[0], str):
                # 展开多仓的子仓抓取逻辑（嵌套一层并发）
                sub_urls = sites
                for sub_url in sub_urls:
                    sub_data = fetch_url(sub_url)
                    if sub_data:
                        s, p, l = parse_multisingle_repo(sub_data)
                        if isinstance(s, list) and (not s or not isinstance(s[0], str)):
                            sites.extend(s)
                            parses.extend(p)
                            lives.extend(l)
                sites = [s for s in sites if isinstance(s, dict)] # 过滤掉多仓的 URL 字符串

            # 3. 处理 sites（核心：去重、过滤冲突、4K排序）
            for site in sites:
                if not isinstance(site, dict):
                    continue
                
                key = site.get("key")
                name = site.get("name", "")
                site_type = site.get("type", 0)

                # 【规避冲突】跳过 type:3 的蜘蛛源，防止 JAR 包冲突导致全局崩溃
                if site_type == 3:
                    continue
                
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    all_sites.append(site)

            # 4. 处理 parses（去重）
            for parse in parses:
                if not isinstance(parse, dict):
                    continue
                p_name = parse.get("name")
                if p_name and p_name not in seen_parse_names:
                    seen_parse_names.add(p_name)
                    all_parses.append(parse)

            # 5. 处理 lives（去重）
            for live in lives:
                if not isinstance(live, dict):
                    continue
                l_name = live.get("name")
                if l_name and l_name not in seen_live_names:
                    seen_live_names.add(l_name)
                    all_lives.append(live)

    print(f"共合并 {len(all_sites)} 个点播源，{len(all_parses)} 个解析，{len(all_lives)} 个直播源。")

    # 6. 4K 优先排序（核心逻辑）
    # 将包含 4K、蓝光、高码 等关键词的源排在最前面
    def sort_key(site):
        name = site.get("name", "").lower()
        if "4k" in name or "4k" in site.get("key", "").lower():
            return 0
        if "蓝光" in name or "blu" in name:
            return 1
        if "高码" in name or "hd" in name:
            return 2
        return 3

    all_sites.sort(key=sort_key)

    # 7. 组装最终配置
    final_config = {
        "sites": all_sites,
        "parses": all_parses,
        "lives": all_lives
    }

    # 8. 写入文件
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_config, f, ensure_ascii=False, indent=2)

    # 9. 更新 list.txt 供前端页面显示（如果原项目需要）
    with open(LIST_FILE, 'w', encoding='utf-8') as f:
        f.write(f"聚合全能接口, 大小: {os.path.getsize(OUTPUT_FILE) / 1024:.2f} KB, 更新时间: {os.popen('date +\"%Y-%m-%d %H:%M:%S\"').read().strip()}\n")

    print(f"聚合完成！文件已保存至 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
