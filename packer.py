#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path
import re
import struct
from typing import Dict, List
from utils_tools.libs import translate_lib
from utils_tools.libs.ops_lib import flat, h, parse_data, u16, u8


OPCODES_MAP = flat({
    # 应该就是起始标志
    h("00 00 00 00 0E 00 00 00 06 00 00"): [],
    h("FE"): {
        # 跳转？**需要修第二个u16**
        h("01"): [u16, u16],
        # 跳转？**需要修第二个u16**
        h("03"): [u16, u16],
        # 文本偏移，**需要修**
        h("06"): [u16],
        "default": []
    },
    # 空指令
    h("00"): [],
    # 可能是赋值操作？目标变量ID，要赋的值
    h("01"): [u16, u16],
    # 大概也是某种变量操作
    h("02"): [u16, u16],
    # 不清楚干嘛的
    h("03"): [u16, u16],
    # 大概也是某种变量操作
    h("04"): [u16, u16],
    # 变量声明？目标变量ID，初始值，标志
    h("05"): [u16, u16, u8],
    # 函数调用？[索引] [类型] [子类型] [参数1] [参数2] [文本偏移]
    # **需要修最后一个u16**
    h("09"): [u16, u8, u8, u16, u8, u16],
    # 跳转？**需要修第二个u16**
    h("08 01"): [u16, u16],

    # --------------------
    h("FF"): {
        # 跳转？**需要修第二个u16**
        h("01"): [u16, u16],
        # 跳转？**需要修第二个u16**
        h("03"): [u16, u16],
        "default": []
    },
    h("1B 01"): [],
})


def split_text(text: str):
    result = []
    for line in text.split('\n'):
        line_parts = []
        for part in line.split(';'):
            tokens = re.split(r'(?i)(%[kowe])', part)
            line_parts.append(tokens)
        result.append(line_parts)
    return result


def read_mpx_file(mpx_path: Path) -> Dict:
    with open(mpx_path, "rb") as f:
        data = bytearray(f.read())

    if len(data) < 8 or not data.startswith(b"Mp17"):
        print(f"非法 MPX 文件: {mpx_path}")
        exit(1)

    mpx = {}
    mpx["sig"] = data[:4].decode("ascii")
    mpx["text_offset"], mpx["text_size"] = struct.unpack_from("<HH", data, 4)

    # 解析 index_data
    mpx["index_data"], _ = parse_data({
        "file_name": str(mpx_path),
        "offset": 8,
    }, data[8:mpx["text_offset"]], OPCODES_MAP)

    # ===============================
    # ★ 修偏移（记录第几个换行）
    # ===============================
    raw_text_bytes = data[mpx["text_offset"]:mpx["text_offset"] + mpx["text_size"]]

    # 找到所有 (b ^ 0x24) == 0x00 的位置
    newline_pos = []
    for i, b in enumerate(raw_text_bytes):
        if (b ^ 0x24) == 0x00:
            newline_pos.append(i)

    def byte_offset_to_line_index(off: int):
        for idx, p in enumerate(newline_pos):
            if p == off:
                return idx
        raise ValueError(f"{mpx_path}: 无法在 {off} 找到对应的line index")

    # 遍历所有 OP，找到需要修复的 u16 偏移字段
    for op in mpx["index_data"]:
        fix_info = {}

        if op["op"] == "FE 01":
            num, _ = translate_lib.de(op["value"][1])
            line_idx = byte_offset_to_line_index(num - 1)
            fix_info["1"] = line_idx
        elif op["op"] == "FE 03":
            num, _ = translate_lib.de(op["value"][1])
            line_idx = byte_offset_to_line_index(num - 1)
            fix_info["1"] = line_idx
        elif op["op"] == "FE 06":
            num, _ = translate_lib.de(op["value"][0])
            line_idx = byte_offset_to_line_index(num - 1)
            fix_info["0"] = line_idx
        elif op["op"] == "09":
            num, _ = translate_lib.de(op["value"][5])
            line_idx = byte_offset_to_line_index(num - 1)
            fix_info["5"] = line_idx
        elif op["op"] == "FF 03":
            num, _ = translate_lib.de(op["value"][1])
            line_idx = byte_offset_to_line_index(num - 1)
            fix_info["1"] = line_idx
        elif op["op"] == "08 01":
            num, _ = translate_lib.de(op["value"][1])
            line_idx = byte_offset_to_line_index(num - 1)
            fix_info["1"] = line_idx
        elif op["op"] == "FF 01":
            num, _ = translate_lib.de(op["value"][1])
            line_idx = byte_offset_to_line_index(num - 1)
            fix_info["1"] = line_idx

        if fix_info:
            op["fix_offset"] = fix_info

        continue

    # ===============================
    # 解密文本
    # ===============================
    text_data = bytearray([0x0A if (b ^ 0x24) == 0 else (b ^ 0x24)
                           for b in raw_text_bytes]).decode("CP932")

    mpx["text_data"] = split_text(text_data)

    # 提取rest_data部分，将其分割为以null结尾的字符串列表
    rest_bytes = data[mpx["text_offset"] + mpx["text_size"]:]
    rest_strings = []
    cur = bytearray()
    for b in rest_bytes:
        if b == 0x00:
            if cur:
                rest_strings.append(cur.decode("ascii"))
                cur = bytearray()
        else:
            cur.append(b)

    assert not cur

    mpx["rest_strings"] = rest_strings
    return mpx


def unpack(input_path: Path, out_dir: Path):
    files = translate_lib.collect_files(str(input_path))

    for mpx_file in files:
        relative = Path(mpx_file).relative_to(input_path)
        json_path = out_dir / relative.with_suffix(".json")
        mpx = read_mpx_file(mpx_file)

        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(mpx, f, indent=2, ensure_ascii=False)


def pack(input_dir: Path, out_path: Path):
    files = translate_lib.collect_files(str(input_dir))

    for json_file in files:
        relative = Path(json_file).relative_to(input_dir)
        mpx_output_path = out_path / relative.with_suffix(".mpx")

        with open(json_file, "r", encoding="utf-8") as f:
            mpx = json.load(f)

        # ===============================
        # 重组 text_data
        # ===============================
        text_lines = []
        for line in mpx["text_data"]:
            parts = []
            for tokens in line:
                parts.append("".join(tokens))
            text_lines.append(";".join(parts))

        text_data_str = "\n".join(text_lines)
        text_data_bytes = text_data_str.encode("CP932")

        # ===============================
        # 新的换行位置
        # ===============================
        newline_pos = [i for i, b in enumerate(text_data_bytes) if b == 0x0A]

        # ===============================
        # 加密
        # ===============================
        encrypted_text_data = bytearray([
            0x24 if b == 0x0A else (b ^ 0x24)
            for b in text_data_bytes
        ])

        # ===============================
        # 重组 index_data，修复偏移
        # ===============================
        out_index_bytes = bytearray()

        for op in mpx["index_data"]:
            op_bytes = bytearray.fromhex(op["op"])
            fix_map = op.get("fix_offset", {})

            for idx, v in enumerate(op["value"]):
                if v.startswith("u16:"):
                    num, _ = translate_lib.de(v)
                    idx_str = str(idx)

                    if idx_str in fix_map:
                        line_idx = fix_map[idx_str]
                        if line_idx >= len(newline_pos):
                            raise ValueError(f"文本换行数量不足：需要 {line_idx}")
                        num = newline_pos[line_idx] + 1

                    op_bytes += struct.pack("<H", num)

                elif v.startswith("u8:"):
                    num, _ = translate_lib.de(v)
                    op_bytes += struct.pack("<B", num)

                else:
                    raise ValueError(f"未知类型字段: {v}")

            out_index_bytes += op_bytes

        index_data_bytes = out_index_bytes

        # ===============================
        # rest_strings
        # ===============================
        rest_data_bytes = bytearray()
        for s in mpx["rest_strings"]:
            rest_data_bytes.extend(s.encode("ascii"))
            rest_data_bytes.append(0)

        # ===============================
        # 写入文件
        # ===============================
        new_text_offset = 8 + len(index_data_bytes)
        new_text_size = len(encrypted_text_data)

        header = bytearray()
        header.extend(mpx["sig"].encode("ascii"))
        header.extend(struct.pack("<HH", new_text_offset, new_text_size))

        output_data = bytearray()
        output_data.extend(header)
        output_data.extend(index_data_bytes)
        output_data.extend(encrypted_text_data)
        output_data.extend(rest_data_bytes)

        mpx_output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(mpx_output_path, "wb") as f:
            f.write(output_data)


def main():
    ap = argparse.ArgumentParser(
        description="packer 解包/打包工具")
    sub = ap.add_subparsers(dest='cmd', required=True)
    ap_unpack = sub.add_parser('unpack', help='解包')
    ap_unpack.add_argument('-i', '--input', required=True, help='输入')
    ap_unpack.add_argument('-o', '--out', required=True, help='输出')
    ap_pack = sub.add_parser('pack', help='打包')
    ap_pack.add_argument('-i', '--input', required=True, help='输入')
    ap_pack.add_argument('-o', '--out', required=True, help='输出')
    args = ap.parse_args()
    if args.cmd == 'unpack':
        unpack(Path(args.input), Path(args.out))
    elif args.cmd == 'pack':
        pack(Path(args.input), Path(args.out))


if __name__ == '__main__':
    main()
