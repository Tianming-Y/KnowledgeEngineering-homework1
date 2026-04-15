"""批量处理 data/processed 中的 JSON 文档，执行 spaCy NER 并保存至 output/entities。

用法示例：
  python src/ner/batch_process.py --link False
  python src/ner/batch_process.py --link True --max-docs 5 --model en_core_web_trf

默认会从 `config/settings.yaml` 读取 `paths.processed_data`，若不存在则使用 `data/processed`。
"""

import os
import sys
import json
import argparse
import glob
from typing import Optional

import yaml
import gzip
import uuid
import time
from tqdm import tqdm

# Ensure project root is on sys.path so the script can be run directly
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.ner import load_model
from src.ner.ner_pipeline import process_text
from src.ner.spacy_ner import predict
from src.ner.entity_linker import link_mentions, search_wikidata
import logging


def extract_text_from_doc(doc: dict) -> str:
    parts = []
    if not isinstance(doc, dict):
        return str(doc)
    if "summary" in doc and isinstance(doc.get("summary"), str):
        parts.append(doc.get("summary"))
    # sections: list of {heading, text}
    secs = doc.get("sections") or doc.get("body") or []
    if isinstance(secs, list):
        for s in secs:
            if isinstance(s, dict):
                t = s.get("text") or s.get("content")
                if isinstance(t, str) and t:
                    parts.append(t)
    # fallback: some files may have 'text' or 'content' at top level
    if "text" in doc and isinstance(doc.get("text"), str):
        parts.append(doc.get("text"))
    if "content" in doc and isinstance(doc.get("content"), str):
        parts.append(doc.get("content"))

    if parts:
        return "\n\n".join(parts)
    # last resort: join all string values
    strings = []
    for v in doc.values():
        if isinstance(v, str):
            strings.append(v)
    if strings:
        return "\n\n".join(strings)
    return json.dumps(doc, ensure_ascii=False)


def load_config_processed_dir() -> str:
    cfg_path = os.path.join(os.getcwd(), "config", "settings.yaml")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh)
            return cfg.get("paths", {}).get("processed_data", "data/processed")
        except Exception:
            return "data/processed"
    return "data/processed"


def process_all(
    processed_dir: str,
    output_dir: str,
    model_name: str = "en_core_web_sm",
    link: bool = False,
    top_k: int = 5,
    max_docs: Optional[int] = None,
    link_verbose: bool = False,
):
    """处理 `processed_dir` 中的 JSON 文件。

    如果 `output_dir` 以 `.jsonl` 或 `.jsonl.gz` 结尾，则合并为单个 JSONL(/gz) 文件；
    否则按文件写入目标目录（兼容原行为）。
    使用临时文件写入并通过 `os.replace` 原子替换目标文件以避免中间不完整写入。
    """
    single_file = str(output_dir).endswith(".jsonl") or str(output_dir).endswith(
        ".jsonl.gz"
    )
    if single_file:
        parent = os.path.dirname(output_dir) or "."
        os.makedirs(parent, exist_ok=True)
        tmp = output_dir + ".tmp." + uuid.uuid4().hex
        if str(output_dir).endswith(".jsonl.gz"):
            writer = gzip.open(tmp, "wt", encoding="utf-8")
        else:
            writer = open(tmp, "w", encoding="utf-8")
    else:
        os.makedirs(output_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(processed_dir, "*.json")))
    if max_docs:
        files = files[:max_docs]

    nlp = load_model(model_name)
    # logger for more detailed status output
    logger = logging.getLogger("batch_process")
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
    logger.setLevel(logging.INFO)
    start_time = time.time()
    processed = 0
    skipped = 0
    total_entities = 0
    total_linked = 0
    try:
        total_files = len(files)
        print(f"Found {total_files} documents in '{processed_dir}'")
        with tqdm(total=total_files, unit="file", desc="Processing", ncols=100) as pbar:
            for idx, fp in enumerate(files, start=1):
                name = os.path.basename(fp)
                pbar.set_description(
                    f"Processing {idx}/{total_files}: {name} (link={'ON' if link else 'OFF'})"
                )
                try:
                    with open(fp, "r", encoding="utf-8") as fh:
                        doc = json.load(fh)
                except Exception:
                    skipped += 1
                    pbar.write(f"  - Skipping unreadable file: {name}")
                    pbar.update(1)
                    continue

                text = extract_text_from_doc(doc)
                logger.info(f"Start processing document: {name}")
                logger.debug(f"  Extracted text length: {len(text)}")
                doc_start = time.time()

                # Run NER first so we know entity count for streaming display
                pbar.write(f"  - Step: NER (running spaCy model: {model_name})")
                ents = predict(text, nlp=nlp)
                ent_count = len(ents)
                pbar.write(f"  - NER done: {ent_count} entities detected")

                # prepare entity-level progress display
                entity_pbar = None
                if link and ent_count:
                    entity_pbar = tqdm(
                        total=ent_count,
                        unit="ent",
                        desc=f"Linking {name}",
                        ncols=80,
                        leave=False,
                        position=1,
                    )

                # Define on_link callback to stream per-entity status and update inner progress
                linked_count_acc = {"v": 0}

                def _on_link(out):
                    # increment counter
                    linked_count_acc["v"] += 1
                    i = linked_count_acc["v"]
                    mention = out.get("mention")
                    s = out.get("start")
                    t = out.get("end")
                    used_emb = out.get("used_embedding", False)
                    cand_count = out.get("link_candidates_count")
                    if cand_count is None:
                        cand_count = len(out.get("link_candidates") or [])
                    qid = out.get("wikidata_qid")
                    conf = out.get("link_confidence")
                    # try to show top candidate label when available
                    top_label = None
                    cands = out.get("link_candidates") or []
                    if cands:
                        try:
                            top_label = cands[0].get("label")
                        except Exception:
                            top_label = None

                    # update inner progress bar if present
                    if entity_pbar is not None:
                        try:
                            entity_pbar.update(1)
                            # keep postfix concise
                            pf = {
                                "i": f"{i}/{ent_count}",
                                "qid": qid or "-",
                                "conf": f"{(conf or 0):.2f}",
                            }
                            entity_pbar.set_postfix(pf)
                        except Exception:
                            pass

                    # always write a short line for visibility; full verbose only when requested
                    if link_verbose:
                        pbar.write(
                            f"    - Entity {i}/{ent_count}: '{mention}' [{s}:{t}] candidates={cand_count} top_candidate={top_label} qid={qid} confidence={conf} used_embedding={used_emb}"
                        )

                if link:
                    # Before linking, perform a quick connectivity check to Wikidata API
                    try:
                        test_res = search_wikidata("Alan Turing", limit=1)
                        reachable = bool(test_res)
                        if reachable:
                            pbar.write(
                                f"  - Wikidata API check: reachable (sample: {test_res[0].get('label')} / {test_res[0].get('id')})"
                            )
                        else:
                            pbar.write(
                                "  - Wikidata API check: reachable but returned no results for 'Alan Turing' (possible rate-limit or API change)"
                            )
                    except Exception as e:
                        pbar.write(
                            f"  - Wikidata API check failed: {type(e).__name__}: {str(e)[:200]}"
                        )

                    pbar.write("  - Step: Linking (Wikidata) ..")
                    try:
                        linked_ents = link_mentions(
                            ents,
                            text,
                            top_k=top_k,
                            verbose=link_verbose,
                            on_link=_on_link,
                        )
                    except Exception as e:
                        # Defensive: link_mentions should normally not raise, but capture any runtime error
                        pbar.write(
                            f"  - Linking failed for document {name}: {type(e).__name__}: {str(e)[:200]}"
                        )
                        linked_ents = ents
                    finally:
                        if entity_pbar is not None:
                            try:
                                entity_pbar.close()
                            except Exception:
                                pass
                    pbar.write(
                        f"  - Linking step finished: processed {linked_count_acc['v']} mentions"
                    )
                else:
                    linked_ents = ents

                ents = linked_ents
                ent_count = len(ents)
                linked_count = sum(
                    1 for e in ents if isinstance(e, dict) and e.get("wikidata_qid")
                )
                total_entities += ent_count
                total_linked += linked_count

                # 仅输出识别到的实体（不包含全文），并移除候选列表，只保留消歧后选中项
                reduced_ents = []
                for e in ents:
                    if isinstance(e, dict):
                        out_ent = {
                            "mention": e.get("mention"),
                            "type": e.get("type"),
                            "start": e.get("start"),
                            "end": e.get("end"),
                            "source": e.get("source"),
                        }
                        # 若启用消歧且存在选中项，则保留选中候选信息（不保留所有候选列表）
                        if link and e.get("wikidata_qid"):
                            out_ent.update(
                                {
                                    "wikidata_qid": e.get("wikidata_qid"),
                                    "wikidata_label": e.get("wikidata_label"),
                                    "wikidata_description": e.get(
                                        "wikidata_description"
                                    ),
                                    "link_confidence": e.get("link_confidence"),
                                }
                            )
                    else:
                        out_ent = {"mention": str(e)}
                    reduced_ents.append(out_ent)

                entity_output = {"doc": name, "entities": reduced_ents}
                if single_file:
                    writer.write(json.dumps(entity_output, ensure_ascii=False))
                    writer.write("\n")
                else:
                    out_path = os.path.join(output_dir, name)
                    with open(out_path, "w", encoding="utf-8") as oh:
                        json.dump(entity_output, oh, ensure_ascii=False, indent=2)

                processed += 1
                pbar.set_postfix({"ents": ent_count, "linked": linked_count})
                pbar.update(1)
    finally:
        if single_file:
            writer.close()
            os.replace(tmp, output_dir)
        elapsed = time.time() - start_time
        print(
            f"Processed {processed} documents, skipped {skipped}, total entities {total_entities}, linked entities {total_linked} in {elapsed:.1f}s"
        )

    print(f"Wrote {processed} documents -> {output_dir}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-dir", default=None)
    # 默认输出为单个 JSONL 文件，便于后续关系抽取与合并处理
    parser.add_argument("--output-dir", default="output/entities_all.jsonl")
    parser.add_argument("--model", default="en_core_web_sm")
    parser.add_argument(
        "--link", default=False, type=lambda v: v.lower() in ("1", "true", "yes")
    )
    parser.add_argument("--top-k", default=3, type=int)
    parser.add_argument(
        "--link-verbose",
        default=False,
        type=lambda v: v.lower() in ("1", "true", "yes"),
        help="Print per-entity linking details to console",
    )
    parser.add_argument("--max-docs", default=None, type=int)
    args = parser.parse_args()

    processed_dir = args.processed_dir or load_config_processed_dir()
    if not os.path.isdir(processed_dir):
        print("Processed dir not found:", processed_dir)
        return
    process_all(
        processed_dir,
        args.output_dir,
        model_name=args.model,
        link=args.link,
        top_k=args.top_k,
        max_docs=args.max_docs,
        link_verbose=args.link_verbose,
    )


if __name__ == "__main__":
    main()
