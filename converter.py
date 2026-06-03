import yaml
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
import hashlib
import os

# ======================
# 配置
# ======================
DEBUG = True
ALLOWED_PROTOCOLS = ('vless', 'hy2', 'hysteria2', 'hysteria', 'tuic')

# 支持的查询参数白名单（可扩展）
ALLOWED_PARAMS = {
    "vless": ["security", "flow", "type", "encryption", "sni"],
    "hysteria2": ["sni", "insecure", "obfs", "alpn", "auth", "ca", "udp"],
    "hysteria": ["peer", "insecure"],
    "tuic": ["mode", "insecure"]
}

# ======================
# 工具函数
# ======================
def normalize_uri(uri: str):
    """标准化 URI：协议头小写，查询参数排序"""
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_PROTOCOLS:
        return None
    query_params = sorted(parse_qsl(parsed.query))
    new_query = urlencode(query_params) if query_params else ""
    return urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

def hash_uri(uri: str):
    """生成 URI 哈希，保证去重稳定"""
    return hashlib.md5(uri.encode()).hexdigest()

# ======================
# 协议解析插件
# ======================
def parse_vless(node):
    uuid = node.get('uuid', '')
    server = node.get('server', '')
    port = int(node.get('port', 443))
    params = {k: node.get(k) for k in ALLOWED_PARAMS["vless"] if node.get(k)}
    query = urlencode(params) if params else ""
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

# 协议插件字典
PARSERS = {
    "vless": parse_vless,
    "hysteria2": parse_hysteria2,
    "hy2": parse_hysteria2,  # 兼容别名
    "hysteria": parse_hysteria,
    "tuic": parse_tuic
}

# ======================
# 核心处理函数
# ======================
def to_uri(node):
    """节点字典 → URI"""
    node_type = node.get('type', '').lower()
    
    # 原生 URI
    if node_type == 'uri':
        return normalize_uri(node.get('uri', ''))
    
    # 协议插件解析
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
        
        seen_hashes = set()
        final_uris = []
        
        for n in nodes:
            uri = to_uri(n)
            if uri:
                h = hash_uri(uri)
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                
                final_uris.append(uri)
                
                if DEBUG:
                    print(f"[DEBUG] {urlparse(uri).scheme} -> {uri}")
        
        # 直接输出到 all_nodes.txt
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(final_uris))
        
        print(f"转换完成，总计 {len(final_uris)} 条标准化 URI，已生成 {output_file}")
    
    except Exception as e:
        print(f"执行失败: {e}")

# ======================
# CLI 入口
# ======================
if __name__ == '__main__':
    process_nodes()
