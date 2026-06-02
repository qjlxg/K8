import yaml

def to_uri(node):
    """将结构化节点转换为通用 URI"""
    # 1. 如果已经是 URI 格式
    if node.get('type') == 'uri':
        return node.get('uri')
    
    # 2. 如果是 YAML 结构，手动拼装
    ptype = node.get('type', '').lower()
    # 目前仅处理常见协议，防止导出无效配置
    if ptype in ['vless', 'hysteria', 'hysteria2', 'tuic']:
        server = node.get('server', '127.0.0.1')
        port = node.get('port', 443)
        # 这里仅展示基础拼接，若需完整参数(uuid, sni等)可在此扩展
        return f"{ptype}://{server}:{port}"
    return None

def main():
    try:
        with open('all_nodes.yaml', 'r', encoding="utf-8") as f:
            nodes = yaml.safe_load(f)
        
        uris = []
        for n in nodes:
            uri = to_uri(n)
            if uri:
                uris.append(uri)
        
        with open('all_nodes.txt', 'w', encoding="utf-8") as f:
            f.write('\n'.join(set(uris)))
        print(f"转换完成，共生成 {len(set(uris))} 条有效 URI")
    except Exception as e:
        print(f"转换失败: {e}")

if __name__ == '__main__':
    main()
