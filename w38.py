import re
import yaml
import threading
import base64
import requests
from loguru import logger
from tqdm import tqdm
from retry import retry
from urllib.parse import unquote
from datetime import datetime

# ======================
# 全局数据
# ======================
new_sub_list = []
new_clash_list = []
new_v2_list = []

lock = threading.Lock()

# ⚡ session + 连接池优化（GitHub Actions 关键）
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
        new_list.append('https://t.me/s/' + a)
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

        logger.info(channel_url + '\t获取成功')
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

    with thread_max_num:

        @retry(tries=2)
        def start_check(url):
            try:
                res = session.get(url, headers=headers, timeout=5)
            except:
                return

            if res.status_code != 200:
                return

            try:
                info = res.headers.get('subscription-userinfo')

                # ======================
                # 流量订阅检测
                # ======================
                if info:
                    match = re.search(r"expire=(\d+)", info)
                    traffic = re.search(r"upload=(\d+); download=(\d+); total=(\d+)", info)

                    upload = download = total = 0
                    if traffic:
                        upload, download, total = map(int, traffic.groups())

                    remain = total - (upload + download)

                    if remain <= 1073741824:
                        return

                    if match:
                        if is_future(int(match.group(1))):
                            with lock:
                                new_sub_list.append(url)
                    else:
                        with lock:
                            new_sub_list.append(url)

                    return

                # ======================
                # clash 判断
                # ======================
                if 'proxies:' in res.text:
                    with lock:
                        new_clash_list.append(url)
                    return

                # ======================
                # v2 / base64 判断
                # ======================
                decoded = safe_b64_decode(res.text[:80])
                if decoded:
                    text = decoded.decode(errors='ignore')
                    if filter_base64(text):
                        with lock:
                            new_v2_list.append(url)

            except:
                pass

        start_check(url)

    with lock:
        bar.update(1)


# ======================
# 主程序
# ======================
if __name__ == '__main__':

    dict_url = {
        "机场订阅": [],
        "clash订阅": [],
        "v2订阅": []
    }

    list_tg = get_config()
    logger.info('读取config成功')

    url_list = []
    proxy_list = []

    allow_list = [
        'sub', 'clash', 'paste', 'tt.vg',
        'shz.al', 'proxies', 'raw.githubusercontent.com'
    ]
    deny_list = ['https://t.me/']

    # ======================
    # 收集链接
    # ======================
    for channel_url in list_tg:
        temp_url_list, temp_text_list = get_channel_http(channel_url)

        for url in temp_url_list:
            if any(x in url for x in allow_list) and all(x not in url for x in deny_list):
                url_list.append(url)

        proxy_list.extend(temp_text_list)

    url_list = list(set(url_list))
    logger.info('开始筛选---')

    # ======================
    # 线程控制
    # ======================
    thread_max_num = threading.Semaphore(64)
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

    # ======================
    # 合并结果
    # ======================
    new_sub_list.extend(dict_url['机场订阅'])
    new_clash_list.extend(dict_url['clash订阅'])
    new_v2_list.extend(dict_url['v2订阅'])

    dict_url.update({
        '机场订阅': sorted(set(new_sub_list)),
        'clash订阅': sorted(set(new_clash_list)),
        'v2订阅': sorted(set(new_v2_list))
    })

    # ======================
    # 输出文件
    # ======================
    with open('latest.yaml', 'w', encoding="utf-8") as f:
        yaml.dump(dict_url, f, allow_unicode=True)

    with open('url.txt', 'w', encoding="utf-8") as f:
        f.writelines([u + '\n' for u in url_list])

    with open('v2ray.txt', 'w', encoding="utf-8") as f:
        f.writelines([unquote(u) + '\n' for u in proxy_list])
