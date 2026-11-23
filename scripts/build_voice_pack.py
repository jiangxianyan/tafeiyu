#!/usr/bin/env python3
"""Build a one-file .tafeivoice.zip from an installed GPT-SoVITS voice."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE = ROOT / "voice" / "GPT-SoVITS-run"
DEFAULT_VOICE = DEFAULT_ENGINE / "voices" / "tafei_v2"
DEFAULT_OUTPUT = ROOT / "dist-voice" / "tafei-v2.tafeivoice.zip"


def resolve_model(engine: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (engine / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(engine: Path, voice_dir: Path, output: Path) -> Path:
    source_manifest_path = voice_dir / "manifest.json"
    source_manifest = json.loads(
        source_manifest_path.read_text(encoding="utf-8-sig")
    )
    gpt = resolve_model(engine, str(source_manifest["gpt_model"]))
    sovits = resolve_model(engine, str(source_manifest["sovits_model"]))
    if not gpt.is_file() or not sovits.is_file():
        raise FileNotFoundError("GPT-SoVITS model weights are missing")

    references = []
    for reference in source_manifest.get("references") or []:
        path = voice_dir / str(reference["file"]).replace("/", os.sep)
        if not path.is_file():
            raise FileNotFoundError(f"Reference audio is missing: {path}")
        references.append(
            {
                "id": str(reference["id"]),
                "file": f"references/{path.name}",
                "text": str(reference["text"]),
            }
        )
    style_refs = {
        "normal": "ref_01",
        "cute": "ref_01",
        "happy": "ref_09",
        "annoyed": "ref_10",
        "soft": "ref_15",
    }
    available = {row["id"] for row in references}
    style_refs = {
        key: value if value in available else "ref_01"
        for key, value in style_refs.items()
    }
    pack = {
        "format": "tafeiyu.voice_pack",
        "format_version": 1,
        "id": "tafei-v2",
        "persona_id": "tafei",
        "display_name": "小菲 GPT-SoVITS V2",
        "engine": "gpt-sovits",
        "model_version": str(source_manifest.get("model_version") or "v2"),
        "gpt_model": "models/xiaofei_gpt_v2.ckpt",
        "sovits_model": "models/xiaofei_sovits_v2.pth",
        "reference_sample_rate": int(
            source_manifest.get("reference_sample_rate") or 32000
        ),
        "references": references,
        "style_refs": style_refs,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tafeiyu-voice-pack-") as temp:
        stage = Path(temp)
        models = stage / "models"
        refs = stage / "references"
        models.mkdir()
        refs.mkdir()
        (stage / "pack.json").write_text(
            json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (stage / "README.txt").write_text(
            "塔菲鱼语音包\n\n"
            "安装：打开塔菲鱼客户端 -> 声音中心 -> 导入语音包，"
            "选择本 .tafeivoice.zip 文件。\n\n"
            "本包包含 GPT-SoVITS V2 训练权重和 20 条参考音频。"
            "模型文件仅在用户本机加载，不会上传到塔菲鱼服务器。\n",
            encoding="utf-8",
        )
        (stage / "权利说明.txt").write_text(
            "本项目不声明拥有角色形象或声线的权利。"
            "下载、使用、再分发本语音包前，请自行确认已取得适用授权。"
            "因无权使用或传播产生的责任由使用者承担。\n",
            encoding="utf-8",
        )
        files = {
            "models/xiaofei_gpt_v2.ckpt": gpt,
            "models/xiaofei_sovits_v2.pth": sovits,
        }
        for index, row in enumerate(references, 1):
            source = voice_dir / str(
                source_manifest["references"][index - 1]["file"]
            ).replace("/", os.sep)
            files[f"references/{source.name}"] = source
        for name, source in files.items():
            destination = stage / Path(name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as reader, destination.open("wb") as writer:
                while chunk := reader.read(4 * 1024 * 1024):
                    writer.write(chunk)
        checksums = {
            name: {"size": path.stat().st_size, "sha256": sha256(path)}
            for name, path in sorted(files.items())
        }
        (stage / "SHA256SUMS.json").write_text(
            json.dumps(checksums, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(
            output,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage).as_posix())
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Voice pack ZIP is damaged: {bad}")
    print(output)
    print(f"size={output.stat().st_size}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", default=str(DEFAULT_ENGINE))
    parser.add_argument("--voice-dir", default=str(DEFAULT_VOICE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    build(
        Path(args.engine).resolve(),
        Path(args.voice_dir).resolve(),
        Path(args.output).resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
