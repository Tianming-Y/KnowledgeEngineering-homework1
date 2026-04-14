"""
run_pipeline.py
一键运行关系抽取 -> 知识图谱构建 -> 可视化全流程。
仅处理 entities_all.jsonl 覆盖的前5个文档。

关系抽取策略：
  1. Infobox 三元组直接生成（confidence=1.0）
  2. 候选对生成 + 银标构建
  3. REBEL 模型对候选句子做三元组抽取，与候选对对齐
  4. 谓词归一化（字面 + embedding 映射）
  5. 合并三来源三元组（Infobox > Silver > REBEL）
"""

import subprocess
import sys
import os

# 禁用 user-site packages（避免 base 环境的包污染 conda 子环境）
os.environ["PYTHONNOUSERSITE"] = "1"


def run(cmd: str, desc: str):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"  CMD: {cmd}")
    print(f"{'='*60}")
    # 使用当前 Python 解释器而非 PATH 中的 python
    cmd = cmd.replace("python ", f'"{sys.executable}" ', 1)
    result = subprocess.run(
        cmd, shell=True, cwd=os.path.dirname(os.path.dirname(__file__))
    )
    if result.returncode != 0:
        print(f"[ERROR] {desc} 失败 (returncode={result.returncode})")
        sys.exit(result.returncode)
    print(f"[OK] {desc} 完成")


def main():
    # 限定的5个文档
    docs = [
        "Alan Turing Year.json",
        "Alan Turing law.json",
        "Alan Turing.json",
        "Alan Turing_ The Enigma.json",
        "Algorithm.json",
    ]
    doc_list_arg = " ".join(f'"{d}"' for d in docs)

    # Step 1: Infobox 三元组抽取
    run(
        f"python src/relation_extraction/extract_infobox_triples.py "
        f"--docs data/processed --out output/graphs/infobox_triples.jsonl "
        f"--mapping config/relation_mapping.yaml "
        f"--doc-list {doc_list_arg}",
        "Step 1: Infobox 三元组抽取",
    )

    # Step 2: 候选对生成
    run(
        "python src/relation_extraction/generate_candidates.py "
        "--entities output/entities_all.jsonl "
        "--docs data/processed "
        "--out data/relation/candidates.jsonl",
        "Step 2: 候选对生成",
    )

    # Step 3: 银标构建（远程监督）
    run(
        "python src/relation_extraction/build_silver_labels.py "
        "--candidates data/relation/candidates.jsonl "
        "--infobox output/graphs/infobox_triples.jsonl "
        "--out data/relation/silver.jsonl",
        "Step 3: 银标构建（Distant Supervision）",
    )

    # Step 4: REBEL 三元组抽取
    run(
        "python src/relation_extraction/rebel_extract.py "
        "--candidates data/relation/candidates.jsonl "
        "--out output/graphs/rebel_triples.jsonl "
        "--model-name Babelscape/rebel-large "
        "--batch-size 8 "
        "--log output/logs/rebel_run.log "
        f"--doc-ids {doc_list_arg}",
        "Step 4: REBEL 三元组抽取",
    )

    # Step 5: 谓词归一化 + 合并三元组
    run(
        "python src/relation_extraction/merge_triples.py "
        "--rebel output/graphs/rebel_triples.jsonl "
        "--infobox output/graphs/infobox_triples.jsonl "
        "--silver data/relation/silver.jsonl "
        "--mapping config/relation_mapping.yaml "
        "--out output/graphs/relation_triples.jsonl "
        "--st-model all-MiniLM-L6-v2 "
        "--log output/logs/rebel_run.log "
        "--qc-out output/logs/rebel_sample_qc.jsonl",
        "Step 5: 谓词归一化 & 三元组合并",
    )

    # Step 5.5: 对合并三元组应用别名替换（最小化去重策略）
    run(
        "python src/relation_extraction/apply_aliases.py "
        "--in output/graphs/relation_triples.jsonl "
        "--out output/graphs/relation_triples_aliased.jsonl "
        "--backup",
        "Step 5.5: 对合并三元组应用别名映射",
    )

    # Step 6: 知识图谱构建
    run(
        "python src/kg_construction/build_graph.py "
        "--triples output/graphs/relation_triples_aliased.jsonl "
        "--entities output/entities_all.jsonl "
        "--output-dir output/graphs",
        "Step 6: 知识图谱构建",
    )

    # Step 7: 可视化
    run(
        "python src/visualization/visualize.py "
        "--graph output/graphs/knowledge_graph.json "
        "--output-dir output/visualizations "
        '--ego-center "Alan Turing" --ego-radius 2',
        "Step 7: 可视化",
    )

    print(f"\n{'='*60}")
    print("  全流程完成！")
    print(f"{'='*60}")
    print("输出文件：")
    print("  - output/graphs/infobox_triples.jsonl    (Infobox 三元组)")
    print("  - data/relation/candidates.jsonl         (候选对)")
    print("  - data/relation/silver.jsonl             (银标数据)")
    print("  - output/graphs/rebel_triples.jsonl      (REBEL 原始三元组)")
    print("  - output/graphs/relation_triples.jsonl   (最终合并三元组)")
    print(
        "  - output/graphs/relation_triples_aliased.jsonl (别名替换后用于构建的三元组)"
    )
    print("  - output/graphs/knowledge_graph.*        (图谱文件)")
    print("  - output/visualizations/full_graph.png   (全图静态)")
    print("  - output/visualizations/full_graph.html  (全图交互)")
    print("  - output/visualizations/ego_*.png/.html  (Ego 子图)")
    print("  - output/logs/rebel_run.log              (REBEL 运行日志)")
    print("  - output/logs/rebel_sample_qc.jsonl      (REBEL 抽样质检)")
    print("  - output/logs/rebel_ambiguous_predicates.jsonl (模糊谓词)")


if __name__ == "__main__":
    main()
