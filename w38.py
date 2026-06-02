import re
import yaml
import threading
import base64
import requests
import csv
from loguru import logger
from tqdm import tqdm
from retry import retry
from urllib.parse import unquote
from datetime import datetime
from collections import defaultdict

# ======================
# 全局数据
# ======================
new_sub_list = []
new_clash_list = []
new_v2_list = []
# 存储频道统计：{channel_url: [url_count, node_count, total_score]}
channel_stats_map = defaultdict(lambda: [0, 0, 0])
url_source = {}         # 存储 URL 来源：{url: set([channel_url, ...])}
valid_url_set = set()   # 确保有效订阅只计数一次

lock = threading.Lock()
max_concurrency = threading.Semaphore(64)

# ⚡ session + 连接池优化
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=100,
    pool_maxsize=100,
    max_retries=0
)
session.mount('http://', adapter)
session.mount('https://', adapter)


# ======================
# 工具函数
# ======================
def is_future(timestamp):
    if len(str(timestamp)) >= 13:
        timestamp = timestamp / 1000
    return timestamp > datetime.now().timestamp()


def filter_base64(text):
    return any(x in text for x in [
        'vless://', 'hy2://', 'hysteria2://', 'hysteria://', 'tuic://'
    ])


def safe_b64_decode(data):
    try:
        data = data.strip()
        pad = '=' * (-len(data) % 4)
        return base64.b64decode(data + pad, validate=False)
    except:
        return b''

def convert_github_url(url):
    """优化后的 GitHub 链接转换逻辑"""
    if "github.com" not in url or "raw.githubusercontent.com" in url:
        return url
    if "/blob/" in url:
        return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return url


# ======================
# 配置读取
# ======================
@logger.catch
def get_config():
    with open('./config.yaml', encoding="UTF-8") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    new_list = []
    for url in data['tgchannel']:
        a = url.split("/")[-1]
        channel_full_url = 'https://t.me/s/' + a
        new_list.append(channel_full_url)
        _ = channel_stats_map[channel_full_url]
    return new_list


# ======================
# 抓取频道内容
# ======================
@logger.catch
def get_channel_http(channel_url):
    try:
        res = session.get(channel_url, timeout=10)
        data = res.text

        url_list = re.findall(
            r"https?://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|]",
            data
        )

        text_list = re.findall(
            r"vless://[^\s<]+|hy2://[^\s<]+|hysteria2://[^\s<]+|hysteria://[^\s<]+|tuic://[^\s<]+",
            data
        )

        logger.info(f"{channel_url} | URL: {len(url_list)} | 节点: {len(text_list)} | 获取成功")
        
        with lock:
            channel_stats_map[channel_url][0] = len(url_list)
            channel_stats_map[channel_url][1] = len(text_list)
            
        return url_list, text_list

    except Exception as e:
        logger.warning(channel_url + '\t获取失败')
        logger.error(str(e))
        return [], []


# ======================
# 节点检测（核心）
# ======================
@logger.catch
def sub_check(url, bar):
    headers = {'User-Agent': 'clash-verge/v2.0.2'}

    with max_concurrency:
        @retry(tries=2)
        def start_check(url):
            try:
                res = session.get(url, headers=headers, timeout=5)
            except:
                return

            if res.status_code != 200:
                return

            score = 0
            is_valid = False
            try:
                # 累积证据模型：检查订阅信息 (Sub权重: 5)
                info = res.headers.get('subscription-userinfo')
                if info:
                    match = re.search(r"expire=(\d+)", info)
                    traffic = re.search(r"upload=(\d+); download=(\d+); total=(\d+)", info)
                    upload = download = total = 0
                    if traffic:
                        upload, download, total = map(int, traffic.groups())
                    remain = total - (upload + download)
                    if remain > 1073741824:
                        score += 5
                        is_valid = True
                        with lock: new_sub_list.append(url)
                    
                # 累积证据模型：检查 Clash 配置 (Clash权重: 3)
                if 'proxies:' in res.text:
                    score += 3
                    is_valid = True
                    with lock: new_clash_list.append(url)

                # 累积证据模型：检查节点内容 (V2/节点权重: 2)
                decoded = safe_b64_decode(res.text[:80])
                if decoded:
                    text = decoded.decode(errors='ignore')
                    if filter_base64(text):
                        score += 2
                        is_valid = True
                        with lock: new_v2_list.append(url)
                
                # 统计有效订阅，确保去重并累加总质量分
                if is_valid:
                    with lock:
                        if url not in valid_url_set:
                            valid_url_set.add(url)
                            for source_channel in url_source.get(url, []):
                                channel_stats_map[source_channel][2] += score
            except:
                pass

        start_check(url)

    with lock:
        bar.update(1)


# ======================
# 主程序
# ======================
if __name__ == '__main__':
    dict_url = {"机场订阅": [], "clash订阅": [], "v2订阅": []}
    list_tg = get_config()
    logger.info('读取config成功')

    url_list = []
    proxy_list = []
    allow_list = ['sub', 'clash', 'paste', 'tt.vg', 'shz.al', 'proxies', 'raw.githubusercontent.com', 'github.com']
    deny_list = ['https://t.me/']

    for channel_url in list_tg:
        temp_url_list, temp_text_list = get_channel_http(channel_url)
        for url in temp_url_list:
            if any(x in url for x in allow_list) and all(x not in url for x in deny_list):
                clean_url = convert_github_url(url)
                url_list.append(clean_url)
                with lock:
                    if clean_url not in url_source:
                        url_source[clean_url] = set()
                    url_source[clean_url].add(channel_url)
        proxy_list.extend(temp_text_list)

    url_list = list(set(url_list))
    logger.info('开始筛选---')

    bar = tqdm(total=len(url_list), desc='订阅筛选：', mininterval=0.2)
    threads = []
    for url in url_list:
        t = threading.Thread(target=sub_check, args=(url, bar))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    bar.close()
    logger.info('筛选完成')

    # 导出统计CSV
    with open('channel_stats.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['频道URL', 'URL数量', '节点数量', '有效资源质量分'])
        for chan, stats in channel_stats_map.items():
            writer.writerow([chan] + stats)
    logger.info('统计表 channel_stats.csv 已生成')

    dict_url.update({
        '机场订阅': sorted(set(new_sub_list)),
        'clash订阅': sorted(set(new_clash_list)),
        'v2订阅': sorted(set(new_v2_list))
    })

    with open('latest.yaml', 'w', encoding="utf-8") as f:
        yaml.dump(dict_url, f, allow_unicode=True)
    with open('url.txt', 'w', encoding="utf-8") as f:
        f.writelines([u + '\n' for u in url_list])
    with open('v2ray.txt', 'w', encoding="utf-8") as f:
        f.writelines([unquote(u) + '\n' for u in proxy_list])
