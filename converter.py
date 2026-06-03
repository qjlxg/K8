import yaml
import re
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
import os
from collections import defaultdict

# ======================
# 配置
# ======================
DEBUG = True
ALLOWED_PROTOCOLS = ('vless', 'hy2', 'hysteria2', 'hysteria', 'tuic')

# 支持的查询参数白名单
ALLOWED_PARAMS = {
    "vless": ["security", "flow", "type", "encryption", "sni", "pbk", "sid", "fp"],
    "hysteria2": ["sni", "insecure", "obfs", "alpn", "auth", "ca", "udp"],
    "hysteria": ["peer", "insecure"],
    "tuic": ["mode", "insecure"]
}

# ======================
# 工具函数
# ======================
def normalize_uri(uri: str):
    """标准化 URI：协议头小写，主机名小写，查询参数排序"""
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_PROTOCOLS:
        return None
    
    # 强制主机名小写
    netloc = parsed.netloc.lower()
    
    query_params = sorted(parse_qsl(parsed.query))
    new_query = urlencode(query_params) if query_params else ""
    return urlunparse((scheme, netloc, parsed.path, parsed.params, new_query, parsed.fragment))

def extract_channels(nodes):
    """从节点名称或备注中提取 @频道名称（使用负向先行断言优化）"""
    channels = set()
    # 匹配 @ 前面不是字母数字下划线，防止匹配到邮箱
    pattern = re.compile(r'(?<![a-zA-Z0-9_])@([a-zA-Z0-9_]{5,32})')
    for node in nodes:
        name = node.get('name', '')
        remark = node.get('remark', '')
        found = pattern.findall(str(name)) + pattern.findall(str(remark))
        for channel in found:
            channels.add(f"https://t.me/{channel}")
    return channels

def update_config_yaml(new_channels, config_file='config.yaml'):
    """读取 config.yaml 并与新频道合并去重后保存"""
    if not os.path.exists(config_file):
        data = {'tgchannel': []}
    else:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {'tgchannel': []}
    
    if 'tgchannel' not in data:
        data['tgchannel'] = []
    
    existing = set(data['tgchannel'])
    updated = existing.union(new_channels)
    data['tgchannel'] = sorted(list(updated))
    
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    print(f"频道处理完成，当前总计 {len(data['tgchannel'])} 个频道")

# ======================
# 协议解析插件
# ======================
def parse_vless(node):
    uuid = node.get('uuid', '')
    server = node.get('server', '')
    port = int(node.get('port', 443))
    params = {k: node.get(k) for k in ALLOWED_PARAMS["vless"] if node.get(k)}
    query = urlencode(sorted(params.items())) if params else ""
    return urlunparse(('vless', f'{uuid}@{server}:{port}', '', '', query, ''))

def parse_hysteria2(node):
    server = node.get('server', '')
    port = int(node.get('port', 443))
    password = node.get('password', node.get('uuid', ''))
    params = {k: node.get(k) for k in ALLOWED_PARAMS["hysteria2"] if node.get(k)}
    query = urlencode(sorted(params.items())) if params else ""
    base = f"hysteria2://{password}@{server}:{port}"
    return f"{base}?{query}" if query else base

def parse_hysteria(node):
    server = node.get('server', '')
    port = int(node.get('port', 443))
    params = {k: node.get(k) for k in ALLOWED_PARAMS["hysteria"] if node.get(k)}
    query = urlencode(params) if params else ""
    base = f"hysteria://{server}:{port}"
    return f"{base}?{query}" if query else base

def parse_tuic(node):
    server = node.get('server', '')
    port = int(node.get('port', 443))
    params = {k: node.get(k) for k in ALLOWED_PARAMS["tuic"] if node.get(k)}
    query = urlencode(params) if params else ""
    base = f"tuic://{server}:{port}"
    return f"{base}?{query}" if query else base

PARSERS = {
    "vless": parse_vless,
    "hysteria2": parse_hysteria2,
    "hy2": parse_hysteria2,
    "hysteria": parse_hysteria,
    "tuic": parse_tuic
}

# ======================
# 核心处理函数
# ======================
def to_uri(node):
    node_type = node.get('type', '').lower()
    if node_type == 'uri':
        return normalize_uri(node.get('uri', ''))
    parser = PARSERS.get(node_type)
    if parser:
        return normalize_uri(parser(node))
    return None

# ======================
# 节点处理框架
# ======================
def process_nodes(input_file='all_nodes.txt', output_file='all_nodes.txt'):
    try:
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"未找到文件: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as f:
            nodes = yaml.safe_load(f)
        
        if not nodes or not isinstance(nodes, list):
            raise ValueError("YAML 文件为空或根结构不是 list")
        
        # 1. 频道发现
        found_channels = extract_channels(nodes)
        if found_channels:
            update_config_yaml(found_channels)
        
        # 2. 节点与指纹处理
        seen_uris = set()
        final_uris = []
        fingerprints = defaultdict(list)
        
        for n in nodes:
            uri = to_uri(n)
            if uri:
                if uri in seen_uris:
                    continue
                seen_uris.add(uri)
                final_uris.append(uri)
                
                # 统一指纹统计逻辑
                if n.get('type', '').lower() == 'vless':
                    # 避免 None 干扰统计
                    fp = tuple(str(n.get(k) or '') for k in ('uuid', 'pbk', 'sni'))
                    fingerprints[fp].append(uri)
                
        # 3. 输出标准化节点
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(final_uris))
        
        # 4. 指纹深度报告
        print(f"--- 报告 ---")
        print(f"总节点数: {len(nodes)}")
        print(f"唯一 URI 数: {len(final_uris)}")
        print(f"唯一指纹数: {len(fingerprints)}")
        
        # 打印高频重复指纹
        for fp, uris in fingerprints.items():
            if len(uris) >= 5:
                print(f"指纹 {fp} 出现 {len(uris)} 次")
    
    except Exception as e:
        print(f"执行失败: {e}")

if __name__ == '__main__':
    process_nodes()
