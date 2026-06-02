import yaml

# ======================
# 配置与工具
# ======================
ALLOWED_PROTOCOLS = ('vless://', 'hy2://', 'hysteria2://', 'hysteria://', 'tuic://')

def to_uri(node):
    """将结构化节点转换为通用 URI，排除 vmess/trojan"""
    # 1. 如果已经是 URI 格式，进行协议过滤
    if node.get('type') == 'uri':
        uri = node.get('uri', '')
        if uri.startswith(ALLOWED_PROTOCOLS):
            return uri
        return None
    
    # 2. 如果是 YAML 结构，处理并拼装
    ptype = node.get('type', '').lower()
    # 协议映射与过滤
    protocol_map = {
        'vless': 'vless://',
        'hy2': 'hy2://',
        'hysteria2': 'hysteria2://',
        'hysteria': 'hysteria://',
        'tuic': 'tuic://'
    }
    
    if ptype in protocol_map:
        server = node.get('server', '127.0.0.1')
        port = node.get('port', 443)
        # 这里仅展示基础拼接，后续可根据需要增加 uuid, sni 等参数
        return f"{protocol_map[ptype]}{server}:{port}"
    
    return None

def main():
    try:
        with open('all_nodes.yaml', 'r', encoding="utf-8") as f:
            nodes = yaml.safe_load(f)
        
        if not isinstance(nodes, list):
            nodes = []

        uris = []
        for n in nodes:
            uri = to_uri(n)
            if uri:
                uris.append(uri)
        
        # 写入结果
        with open('all_nodes.txt', 'w', encoding="utf-8") as f:
            f.write('\n'.join(sorted(set(uris))))
        
        print(f"转换完成，共生成 {len(set(uris))} 条符合协议要求的 URI")
    except Exception as e:
        print(f"转换失败: {e}")

if __name__ == '__main__':
    main()
