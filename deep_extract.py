import re
import yaml
import base64
import requests
import threading
import queue
from loguru import logger
from urllib.parse import urlsplit, urlunsplit

# ======================
# 配置与数据
# ======================
MAX_URLS = 10000
WORKER_THREADS = 32
url_queue = queue.Queue()
processed_urls = set()
all_nodes_dict = {}
lock = threading.Lock()

session = requests.Session()
session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=64))

NODE_URI_REGEX = re.compile(r'(?:vless|hy2|hysteria2|hysteria|tuic)://[^\s"\'<>]+')
LINK_REGEX = re.compile(r'https?://[^\s"\'<>]+')

# ======================
# 工具函数
# ======================
def normalize_url(url):
    """去除 Query 参数防止重复抓取"""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, '', ''))

def safe_b64_decode(data):
    if len(data) < 16: return ""
    clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data)
    try:
        return base64.b64decode(clean_data).decode('utf-8', errors='ignore')
    except: return ""

# ======================
# 核心工作线程
# ======================
def worker():
    while True:
        try:
            url = url_queue.get(timeout=3)
        except queue.Empty: break
            
        try:
            res = session.get(url, timeout=10, headers={'User-Agent': 'clash-verge/v2.0.2'}, allow_redirects=True)
            content = res.text
            real_url = res.url
            
            # 1. 解析逻辑：结构化处理
            found_nodes = []
            is_b64 = re.fullmatch(r'[A-Za-z0-9+/=\r\n]+', content.strip())
            
            # YAML 处理
            if "proxies:" in content:
                try:
                    data = yaml.safe_load(content)
                    if isinstance(data, dict) and isinstance(data.get('proxies'), list):
                        for p in data['proxies']:
                            if isinstance(p, dict):
                                p['source_url'] = real_url
                                found_nodes.append(p)
                except: pass
            
            # URI 处理 (Base64 或 纯文本)
            uris = NODE_URI_REGEX.findall(safe_b64_decode(content)) if is_b64 else NODE_URI_REGEX.findall(content)
            found_nodes.extend([{'type': 'uri', 'uri': u, 'source_url': real_url} for u in uris])
            
            # 2. 去重与存储
            if found_nodes:
                with lock:
                    for n in found_nodes:
                        key = n.get('uuid') or n.get('uri') or str(n)
                        if key not in all_nodes_dict: all_nodes_dict[key] = n
            
            # 3. 递归发现 (URL 归一化)
            if len(processed_urls) < MAX_URLS:
                new_links = [normalize_url(l) for l in LINK_REGEX.findall(content)]
                new_links.append(normalize_url(real_url))
                with lock:
                    for link in set(new_links):
                        if any(k in link for k in ['sub', 'subscribe', 'proxy', 'raw.githubusercontent.com']) and link not in processed_urls:
                            processed_urls.add(link)
                            url_queue.put(link)
        except: pass
        finally: url_queue.task_done()

# ======================
# 主程序
# ======================
if __name__ == '__main__':
    with open('latest.yaml', 'r', encoding="utf-8") as f:
        for urls in yaml.safe_load(f).values():
            for url in urls:
                norm_url = normalize_url(url)
                if norm_url not in processed_urls:
                    processed_urls.add(norm_url)
                    url_queue.put(norm_url)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(WORKER_THREADS)]
    for t in threads: t.start()
    url_queue.join()
    
    with open('all_nodes.yaml', 'w', encoding="utf-8") as f:
        yaml.dump(list(all_nodes_dict.values()), f, allow_unicode=True)
    logger.info(f"挖掘完成。共提取唯一节点对象: {len(all_nodes_dict)}")
