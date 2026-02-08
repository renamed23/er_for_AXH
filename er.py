#!/usr/bin/env python3

import os
import json
import argparse
import re
from typing import List, Dict, Optional, Tuple
from utils_tools.libs import translate_lib


def should_ignore(s: str) -> bool:
    if s is None:
        return True
    s = s.strip()
    if s == "":
        return True
    if s.isascii():
        return True
    return False


# ========== 提取 ==========


def extract_strings_from_file(file_path: str) -> List[Dict]:
    """
    扫描单文件，根据第一个匹配到的 marker 决定类型并提取字符串。
    返回的 results: 每项至少包含 'message' 和 'path'；若该对话有角色名则包含 'name'。
    """
    results: List[Dict] = []
    with open(file_path, 'rb') as f:
        data = f.read()

    # 解析JSON数据
    json_data = json.loads(data.decode('utf-8'))

    # 深度优先遍历text_data
    def dfs_traverse(node):
        if isinstance(node, list):
            for item in node:
                dfs_traverse(item)
        elif isinstance(node, str):
            if should_ignore(node):
                return

            # 检查是否满足【名字】文本结构
            pattern = r'^【(.+?)】(.*)$'
            match = re.match(pattern, node)

            if match:
                # 有角色名的情况
                name = match.group(1)
                message = match.group(2)
                if message:  # 确保消息不为空
                    results.append({
                        "name": name,
                        "message": message,
                        "path": file_path,
                    })
            else:
                # 没有角色名的情况
                results.append({
                    "message": node,
                    "path": file_path,
                })

    # 开始遍历text_data
    dfs_traverse(json_data['text_data'])

    return results


def extract_strings(path: str, output_file: str):
    files = translate_lib.collect_files(path)
    results = []
    for file in files:
        results.extend(extract_strings_from_file(file))
    print(f"提取了 {len(results)} 项")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

# ========== 替换 ==========


def replace_in_file(file_path: str, text: List[Dict[str, str]], output_dir: str, trans_index: int, base_root: str) -> int:
    """
    替换单文件中的字符串。返回更新后的 trans_index。
    text: 全局译文列表（每项至少有 'message'，可能还含 'name'）
    """
    with open(file_path, 'rb') as f:
        data = f.read()

    # 解析JSON数据
    json_data = json.loads(data.decode('utf-8'))

    # 深度优先遍历并替换text_data
    def dfs_replace(node):
        nonlocal trans_index
        if isinstance(node, list):
            new_list = []
            for item in node:
                if isinstance(item, list):
                    new_list.append(dfs_replace(item))
                elif isinstance(item, str):
                    if should_ignore(item):
                        new_list.append(item)
                    else:
                        # 检查是否还有剩余的译文
                        if trans_index >= len(text):
                            new_list.append(item)
                            continue

                        # 检查原始字符串是否有角色名
                        pattern = r'^【(.+?)】(.*)$'
                        match = re.match(pattern, item)

                        if match:
                            # 原始有角色名
                            translation = text[trans_index]
                            trans_index += 1

                            new_item = f"【{translation['name']}】{translation['message']}"
                            new_list.append(new_item)
                        else:
                            # 原始没有角色名
                            translation = text[trans_index]
                            trans_index += 1
                            new_list.append(translation['message'])
                else:
                    raise ValueError(f"未知的item {item}")
            return new_list
        return node

    # 替换text_data
    if 'text_data' in json_data:
        json_data['text_data'] = dfs_replace(json_data['text_data'])

    # 将修改后的数据转换回字节
    new_data = json.dumps(json_data, indent=2,
                          ensure_ascii=False).encode('utf-8')

    rel = os.path.relpath(file_path, start=base_root)
    out_path = os.path.join(output_dir, rel)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as out_f:
        out_f.write(new_data)

    return trans_index


def replace_strings(path: str, text_file: str, output_dir: str):
    with open(text_file, 'r', encoding='utf-8') as f:
        text = json.load(f)
    files = translate_lib.collect_files(path)
    trans_index = 0
    for file in files:
        trans_index = replace_in_file(
            file, text, output_dir, trans_index, base_root=path)
        print(f"已处理: {file}")
    if trans_index != len(text):
        print(f"错误: 有 {len(text)} 项译文，但只消耗了 {trans_index}。")
        exit(1)

# ---------------- main ----------------


def main():
    parser = argparse.ArgumentParser(description='文件提取和替换工具')
    subparsers = parser.add_subparsers(
        dest='command', help='功能选择', required=True)

    ep = subparsers.add_parser('extract', help='解包文件提取文本')
    ep.add_argument('--path', required=True, help='文件夹路径')
    ep.add_argument('--output', default='raw.json', help='输出JSON文件路径')

    rp = subparsers.add_parser('replace', help='替换解包文件中的文本')
    rp.add_argument('--path', required=True, help='文件夹路径')
    rp.add_argument('--text', default='translated.json', help='译文JSON文件路径')
    rp.add_argument('--output-dir', default='translated',
                    help='输出目录(默认: translated)')

    args = parser.parse_args()
    if args.command == 'extract':
        extract_strings(args.path, args.output)
        print(f"提取完成! 结果保存到 {args.output}")
    elif args.command == 'replace':
        replace_strings(args.path, args.text, args.output_dir)
        print(f"替换完成! 结果保存到 {args.output_dir} 目录")


if __name__ == '__main__':
    main()
